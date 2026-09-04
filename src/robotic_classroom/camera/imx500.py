from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

from robotic_classroom.camera.models import (
    BoundingBox,
    CameraSnapshot,
    CameraStatus,
    PersonDetection,
)


class IMX500Camera:
    """Single-owner Raspberry Pi AI Camera backend.

    Picamera2/IMX500 imports are lazy so this module can exist on Windows and CI.
    The backend owns the camera for its entire lifetime and exposes only snapshots
    and JPEGs to the rest of the application.
    """

    def __init__(
        self,
        *,
        model_path: Path,
        width: int,
        height: int,
        frame_rate: int,
        confidence_threshold: float,
        jpeg_quality: int,
        person_label: str,
    ) -> None:
        self.model_path = Path(model_path)
        self.width = width
        self.height = height
        self.frame_rate = frame_rate
        self.confidence_threshold = confidence_threshold
        self.jpeg_quality = jpeg_quality
        self.person_label = person_label

        self._imx500: Any | None = None
        self._picam2: Any | None = None
        self._intrinsics: Any | None = None
        self._cv2: Any | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._latest_jpeg: bytes | None = None
        self._latest_snapshot = CameraSnapshot(
            backend="imx500",
            connected=False,
            frame_width=width,
            frame_height=height,
            sequence=0,
            message="IMX500 camera not started",
        )
        self._last_error = ""

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        if not self.model_path.exists():
            raise RuntimeError(f"IMX500 model not found: {self.model_path}")

        import cv2
        from picamera2 import Picamera2
        from picamera2.devices.imx500 import IMX500

        self._cv2 = cv2
        self._imx500 = IMX500(str(self.model_path))
        self._intrinsics = self._imx500.network_intrinsics
        self._picam2 = Picamera2(self._imx500.camera_num)

        config = self._picam2.create_video_configuration(
            main={"size": (self.width, self.height), "format": "RGB888"},
            controls={"FrameRate": self.frame_rate},
            buffer_count=6,
        )
        self._picam2.configure(config)
        self._picam2.start()

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._capture_loop, daemon=True, name="imx500-camera")
        self._thread.start()

    def _labels(self) -> list[str]:
        labels = getattr(self._intrinsics, "labels", None) or []
        if getattr(self._intrinsics, "ignore_dash_labels", False):
            labels = [label for label in labels if label and label != "-"]
        return list(labels)

    def _parse_people(self, metadata: dict[str, Any]) -> tuple[PersonDetection, ...]:
        assert self._imx500 is not None
        assert self._picam2 is not None

        outputs = self._imx500.get_outputs(metadata, add_batch=True)
        if outputs is None or len(outputs) < 3:
            return ()

        boxes, scores, classes = outputs[0][0], outputs[1][0], outputs[2][0]
        _, input_h = self._imx500.get_input_size()

        if getattr(self._intrinsics, "bbox_normalization", False):
            boxes = boxes / input_h
        if getattr(self._intrinsics, "bbox_order", None) == "xy":
            boxes = boxes[:, [1, 0, 3, 2]]

        labels = self._labels()
        people: list[PersonDetection] = []
        for box, score, category in zip(boxes, scores, classes):
            confidence = float(score)
            category_index = int(category)
            label = labels[category_index] if 0 <= category_index < len(labels) else str(category_index)
            if confidence < self.confidence_threshold or label != self.person_label:
                continue

            coords = tuple(float(v) for v in box)
            converted = self._imx500.convert_inference_coords(coords, metadata, self._picam2)
            people.append(
                PersonDetection(
                    confidence=confidence,
                    box=BoundingBox(
                        x=int(converted.x),
                        y=int(converted.y),
                        width=int(converted.width),
                        height=int(converted.height),
                    ),
                    label=label,
                )
            )
        return tuple(people)

    def _capture_loop(self) -> None:
        assert self._picam2 is not None
        assert self._cv2 is not None
        sequence = 0

        while not self._stop_event.is_set():
            try:
                request = self._picam2.capture_request()
                try:
                    metadata = request.get_metadata()
                    frame = request.make_array("main")
                    people = self._parse_people(metadata)
                    ok, encoded = self._cv2.imencode(
                        ".jpg",
                        frame,
                        [int(self._cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality],
                    )
                finally:
                    request.release()

                if not ok:
                    raise RuntimeError("OpenCV failed to encode camera frame")

                sequence += 1
                snapshot = CameraSnapshot(
                    backend="imx500",
                    connected=True,
                    frame_width=self.width,
                    frame_height=self.height,
                    sequence=sequence,
                    people=people,
                    message="IMX500 camera running",
                )
                with self._lock:
                    self._latest_jpeg = encoded.tobytes()
                    self._latest_snapshot = snapshot
                    self._last_error = ""
            except Exception as exc:  # noqa: BLE001 - worker must surface arbitrary camera faults
                with self._lock:
                    self._last_error = str(exc)
                    self._latest_snapshot = CameraSnapshot(
                        backend="imx500",
                        connected=False,
                        frame_width=self.width,
                        frame_height=self.height,
                        sequence=sequence,
                        message=f"IMX500 error: {exc}",
                    )
                time.sleep(0.25)

    def snapshot(self) -> CameraSnapshot:
        with self._lock:
            return self._latest_snapshot

    def jpeg(self) -> bytes | None:
        with self._lock:
            return self._latest_jpeg

    def status(self) -> CameraStatus:
        snapshot = self.snapshot()
        return CameraStatus(
            backend=snapshot.backend,
            connected=snapshot.connected,
            running=self._thread is not None and self._thread.is_alive(),
            sequence=snapshot.sequence,
            people_count=len(snapshot.people),
            message=snapshot.message,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if self._picam2 is not None:
            try:
                self._picam2.stop()
            finally:
                self._picam2.close()
        self._thread = None
        self._picam2 = None
        self._imx500 = None
