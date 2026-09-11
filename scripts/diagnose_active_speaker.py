from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
INTERVAL = 0.5
REQUEST_TIMEOUT = 2.0
REQUEST_RETRIES = 5
RETRY_DELAY = 0.25

# Current real-hardware fusion geometry from config.pi.yaml.
CAMERA_HORIZONTAL_FOV_DEGREES = 70.0
OUTSIDE_FOV_MARGIN_DEGREES = 5.0
DOA_INVERTED = True
MAX_MATCH_ERROR_DEGREES = 18.0


def get_json(path: str) -> dict:
    url = BASE + path
    last_error: Exception | None = None

    for attempt in range(1, REQUEST_RETRIES + 1):
        try:
            with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT) as response:
                payload = response.read().decode("utf-8")
                return json.loads(payload)
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            ConnectionError,
            OSError,
            json.JSONDecodeError,
        ) as exc:
            last_error = exc
            if attempt < REQUEST_RETRIES:
                time.sleep(RETRY_DELAY)

    raise RuntimeError(
        f"GET {path} failed after {REQUEST_RETRIES} attempts: {last_error}"
    ) from last_error


def signed_angle(degrees: float) -> float:
    return ((degrees + 180.0) % 360.0) - 180.0


def fusion_angle(doa: float | None) -> float | None:
    if doa is None:
        return None
    value = signed_angle(doa)
    return -value if DOA_INVERTED else value


def main() -> None:
    print("ZeeAIBotWebCam active-speaker fusion diagnostic")
    print("Keep ./scripts/run_pi.sh running. Stand in view and speak.")
    print("Transient local HTTP failures are retried automatically.")
    print("Ctrl+C to stop.\n")

    half_fov = CAMERA_HORIZONTAL_FOV_DEGREES / 2.0
    fov_limit = half_fov + OUTSIDE_FOV_MARGIN_DEGREES
    consecutive_failures = 0

    try:
        while True:
            try:
                audio = get_json("/api/audio/status")
                camera = get_json("/api/camera/detections")
                fusion = get_json("/api/active-speaker/status")
                consecutive_failures = 0
            except RuntimeError as exc:
                consecutive_failures += 1
                print("=" * 72)
                print(f"temporary API error ({consecutive_failures}): {exc}")
                print("The diagnostic will keep running and retry automatically.")
                if consecutive_failures >= 6:
                    print(
                        "Main API has been unreachable for several cycles. "
                        "Check that ./scripts/run_pi.sh is still running."
                    )
                time.sleep(INTERVAL)
                continue

            doa = audio.get("doa_degrees")
            doa_value = float(doa) if isinstance(doa, (int, float)) else None
            signed = signed_angle(doa_value) if doa_value is not None else None
            effective = fusion_angle(doa_value)

            people = camera.get("people") or []
            frame = camera.get("frame") or {}
            width = max(int(frame.get("width") or 1), 1)

            candidates = []
            best_error: float | None = None
            for index, person in enumerate(people):
                box = person.get("box") or {}
                center_x = (
                    float(box.get("x", 0)) + float(box.get("width", 0)) / 2.0
                ) / width
                camera_angle = (center_x - 0.5) * CAMERA_HORIZONTAL_FOV_DEGREES
                angular_error = (
                    abs(camera_angle - effective) if effective is not None else None
                )
                if angular_error is not None:
                    best_error = angular_error if best_error is None else min(best_error, angular_error)
                candidates.append(
                    {
                        "index": index,
                        "confidence": round(float(person.get("confidence") or 0), 3),
                        "center_x": round(center_x, 3),
                        "camera_angle": round(camera_angle, 2),
                        "error_to_audio": (
                            None if angular_error is None else round(angular_error, 2)
                        ),
                    }
                )

            print("=" * 72)
            print(
                f"audio: speech={audio.get('speech_state')} "
                f"raw={audio.get('doa_degrees_raw')} calibrated={doa_value}"
            )
            print(
                "geometry: "
                f"pre_inversion_signed={None if signed is None else round(signed, 2)} "
                f"doa_inverted={DOA_INVERTED} "
                f"effective_fusion_angle={None if effective is None else round(effective, 2)} "
                f"allowed_fov=+/-{fov_limit:.1f}deg"
            )
            print(f"camera: people={len(people)} candidates={candidates}")
            print(
                "fusion: "
                f"state={fusion.get('state')} speaker={fusion.get('speaker_id')} "
                f"confidence={fusion.get('confidence')} "
                f"candidate={fusion.get('candidate_index')} "
                f"camera_angle={fusion.get('camera_angle_degrees')} "
                f"doa={fusion.get('doa_degrees')} "
                f"error={fusion.get('angular_error_degrees')}"
            )
            print(f"reason: {fusion.get('message')}")

            if effective is not None and abs(effective) > fov_limit:
                print(
                    "DIAGNOSIS: audio direction is outside the camera FOV gate; "
                    "candidate scoring is skipped."
                )
            elif best_error is not None and best_error > MAX_MATCH_ERROR_DEGREES:
                print(
                    "DIAGNOSIS: audio direction is inside the FOV, but the nearest "
                    f"visible candidate differs by {best_error:.1f}deg, above the "
                    f"{MAX_MATCH_ERROR_DEGREES:.1f}deg match target."
                )
            elif people and audio.get("speech_active"):
                print("DIAGNOSIS: geometry is eligible for candidate scoring.")

            time.sleep(INTERVAL)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
