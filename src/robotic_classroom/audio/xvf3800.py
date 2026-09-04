from __future__ import annotations

import struct
from typing import Any

from robotic_classroom.audio.models import AudioObservation, SpeechState


class XVF3800USBBackend:
    """Read-only XVF3800 USB control backend for VAD and direction of arrival.

    The implementation follows Seeed's documented vendor-control protocol. It
    intentionally performs no LED/configuration writes and does not open the
    ALSA audio stream; Phase 7 uses the XVF3800 DSP metadata only.
    """

    TIMEOUT_MS = 1000
    VERSION_RESID = 48
    VERSION_CMDID = 0
    VERSION_LENGTH = 3
    DOA_RESID = 20
    DOA_CMDID = 18
    DOA_PAYLOAD_LENGTH = 4

    def __init__(self, vendor_id: int, product_id: int) -> None:
        self.vendor_id = vendor_id
        self.product_id = product_id
        self._usb_core: Any | None = None
        self._usb_util: Any | None = None
        self._device: Any | None = None
        self._running = False
        self._sequence = 0
        self._firmware_version: str | None = None

    def _read_control(self, *, resid: int, cmdid: int, payload_length: int) -> bytes:
        if self._device is None or self._usb_util is None:
            raise RuntimeError("XVF3800 USB device is not started")

        response = self._device.ctrl_transfer(
            self._usb_util.CTRL_IN
            | self._usb_util.CTRL_TYPE_VENDOR
            | self._usb_util.CTRL_RECIPIENT_DEVICE,
            0,
            0x80 | cmdid,
            resid,
            payload_length + 1,
            self.TIMEOUT_MS,
        )
        data = response.tobytes()
        if len(data) != payload_length + 1:
            raise RuntimeError(
                f"Unexpected XVF3800 response length: {len(data)}; "
                f"expected {payload_length + 1}"
            )
        status = data[0]
        if status != 0:
            raise RuntimeError(f"XVF3800 command failed with status 0x{status:02x}")
        return data[1:]

    def start(self) -> None:
        if self._running:
            return

        try:
            import usb.core
            import usb.util
        except ImportError as exc:
            raise RuntimeError(
                "PyUSB is required for AUDIO_MODE=xvf3800_usb. Install project dependencies."
            ) from exc

        self._usb_core = usb.core
        self._usb_util = usb.util
        self._device = usb.core.find(idVendor=self.vendor_id, idProduct=self.product_id)
        if self._device is None:
            raise RuntimeError(
                f"XVF3800 not found at USB {self.vendor_id:04x}:{self.product_id:04x}"
            )

        try:
            version = self._read_control(
                resid=self.VERSION_RESID,
                cmdid=self.VERSION_CMDID,
                payload_length=self.VERSION_LENGTH,
            )
            self._firmware_version = ".".join(str(value) for value in version)
        except Exception:
            self._dispose()
            raise

        self._running = True

    def observation(self) -> AudioObservation:
        if not self._running:
            return AudioObservation(
                backend="xvf3800_usb",
                connected=False,
                running=False,
                sequence=self._sequence,
                speech_state=SpeechState.UNAVAILABLE,
                speech_active=False,
                doa_degrees_raw=None,
                doa_degrees=None,
                orientation_calibrated=False,
                firmware_version=self._firmware_version,
                message="XVF3800 USB backend not started",
            )

        payload = self._read_control(
            resid=self.DOA_RESID,
            cmdid=self.DOA_CMDID,
            payload_length=self.DOA_PAYLOAD_LENGTH,
        )
        doa_angle, vad_flag = struct.unpack("<HH", payload)
        if doa_angle > 359:
            raise RuntimeError(f"XVF3800 returned invalid DoA angle: {doa_angle}")

        self._sequence += 1
        speech_active = bool(vad_flag)
        return AudioObservation(
            backend="xvf3800_usb",
            connected=True,
            running=True,
            sequence=self._sequence,
            speech_state=SpeechState.SPEAKING if speech_active else SpeechState.SILENT,
            speech_active=speech_active,
            doa_degrees_raw=float(doa_angle),
            doa_degrees=float(doa_angle),
            orientation_calibrated=False,
            firmware_version=self._firmware_version,
            message="XVF3800 VAD/DoA metadata available",
        )

    def _dispose(self) -> None:
        if self._device is not None and self._usb_util is not None:
            self._usb_util.dispose_resources(self._device)
        self._device = None

    def stop(self) -> None:
        self._running = False
        self._dispose()
