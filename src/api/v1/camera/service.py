import asyncio
import base64
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import quote

import cv2
import numpy as np
import requests
from requests.auth import HTTPBasicAuth, HTTPDigestAuth

from api.v1.camera.schemas import CameraSnapshotRead
from core.config import settings
from core.config.constants import ROOT_DIR

logger = logging.getLogger(__name__)

IP_BUFFER_FLUSH_FRAMES = 3
CAPTURE_API = cv2.CAP_FFMPEG
JPEG_MAGIC = b"\xff\xd8\xff"


def _resolve_mock_image_path() -> Path:
    here = Path(__file__).resolve()
    candidates = (
        here.parents[4] / "static" / "camera-mock.jpg",  # local: tochnost/static
        here.parents[3] / "static" / "camera-mock.jpg",  # docker: /app/static
        ROOT_DIR / "static" / "camera-mock.jpg",
    )
    for path in candidates:
        if path.is_file():
            return path
    return candidates[0]

_workers_started = False
_worker_task: asyncio.Task | None = None
_stop_event: asyncio.Event | None = None


def build_http_snapshot_urls() -> list[str]:
    scheme = "https" if settings.hikvision_http_use_https else "http"
    port = settings.hikvision_http_port
    default_port = 443 if settings.hikvision_http_use_https else 80
    port_suffix = "" if port == default_port else f":{port}"
    base = f"{scheme}://{settings.hikvision_front_ip}{port_suffix}"
    channel = settings.hikvision_front_channel

    if settings.hikvision_http_snapshot_path:
        path = settings.hikvision_http_snapshot_path
        if not path.startswith("/"):
            path = f"/{path}"
        return [f"{base}{path}"]

    return [
        f"{base}/ISAPI/Streaming/channels/{channel}/picture",
        f"{base}/Streaming/channels/{channel}/picture",
    ]


def build_rtsp_url(
    ip: str,
    username: str,
    password: str,
    channel: str = "101",
    port: int | str = 554,
    transport: str = "udp",
) -> str:
    safe_user = quote(username, safe="")
    safe_pass = quote(password, safe="")
    base = f"rtsp://{safe_user}:{safe_pass}@{ip}:{port}/Streaming/Channels/{channel}"
    if transport.lower() == "tcp":
        base = f"{base}{'&' if '?' in base else '?'}tcp"
    return base


def is_ip_camera(source: str) -> bool:
    return any(proto in source for proto in ("http://", "rtsp://", "rtmp://"))


def configure_camera(cap: cv2.VideoCapture, src: str) -> None:
    if is_ip_camera(src):
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        cap.set(cv2.CAP_PROP_FPS, 15)


def flush_camera_buffer(cap: cv2.VideoCapture, is_ip: bool) -> None:
    flush_count = IP_BUFFER_FLUSH_FRAMES if is_ip else 2
    for _ in range(flush_count):
        cap.read()


def crop_frame(
    frame: np.ndarray,
    *,
    crop_top: int,
    crop_bottom: int,
    crop_left: int,
    crop_right: int,
) -> np.ndarray:
    h, w = frame.shape[:2]
    top = min(crop_top, h - 1)
    bottom = min(crop_bottom, h - top - 1)
    left = min(crop_left, w - 1)
    right = min(crop_right, w - left - 1)

    if top or bottom or left or right:
        return frame[top : h - bottom if bottom else h, left : w - right if right else w]
    return frame


def detect_motion(
    prev_gray: np.ndarray | None,
    curr_gray: np.ndarray,
    threshold: float,
) -> tuple[bool, float, np.ndarray]:
    if prev_gray is None or prev_gray.shape != curr_gray.shape:
        return False, 0.0, curr_gray

    score = float(np.mean(cv2.absdiff(prev_gray, curr_gray)))
    return score > threshold, score, curr_gray


def encode_jpeg(frame: np.ndarray, quality: int) -> bytes:
    ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise RuntimeError("Failed to encode JPEG frame")
    return encoded.tobytes()


def _needs_frame_processing() -> bool:
    return any(
        (
            settings.hikvision_crop_top,
            settings.hikvision_crop_bottom,
            settings.hikvision_crop_left,
            settings.hikvision_crop_right,
        )
    )


def decode_jpeg(jpeg_bytes: bytes) -> np.ndarray:
    frame = cv2.imdecode(np.frombuffer(jpeg_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise RuntimeError("Failed to decode JPEG frame from camera")
    return frame


def is_jpeg_payload(payload: bytes) -> bool:
    return len(payload) >= 3 and payload[:3] == JPEG_MAGIC


@dataclass(slots=True)
class CameraState:
    captured_at: datetime | None = None
    image_base64: str | None = None
    motion_detected: bool = False
    motion_score: float | None = None
    status: Literal["ok", "error", "mock", "disabled", "waiting"] = "waiting"
    error_message: str | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def update(
        self,
        *,
        captured_at: datetime,
        image_base64: str | None,
        motion_detected: bool,
        motion_score: float | None,
        status: Literal["ok", "error", "mock", "disabled", "waiting"],
        error_message: str | None = None,
    ) -> None:
        with self._lock:
            self.captured_at = captured_at
            self.image_base64 = image_base64
            self.motion_detected = motion_detected
            self.motion_score = motion_score
            self.status = status
            self.error_message = error_message

    def to_read(self) -> CameraSnapshotRead:
        with self._lock:
            return CameraSnapshotRead(
                captured_at=self.captured_at,
                image_base64=self.image_base64,
                motion_detected=self.motion_detected,
                motion_score=self.motion_score,
                status=self.status,
                error_message=self.error_message,
            )


CAMERA_STATE = CameraState()


@dataclass
class _CaptureSession:
    cap: cv2.VideoCapture | None = None
    prev_gray: np.ndarray | None = None
    rtsp_url: str | None = None

    def release(self) -> None:
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        self.prev_gray = None
        self.rtsp_url = None


@dataclass
class _HttpCaptureSession:
    session: requests.Session | None = None
    prev_gray: np.ndarray | None = None
    auth_key: str | None = None

    def release(self) -> None:
        if self.session is not None:
            self.session.close()
            self.session = None
        self.prev_gray = None
        self.auth_key = None


_capture_session = _CaptureSession()
_capture_session_lock = threading.Lock()
_http_session = _HttpCaptureSession()
_http_session_lock = threading.Lock()


def _load_mock_jpeg() -> bytes:
    mock_path = _resolve_mock_image_path()
    if not mock_path.is_file():
        raise FileNotFoundError(f"Mock camera image not found: {mock_path}")
    return mock_path.read_bytes()


def _open_camera(rtsp_url: str) -> cv2.VideoCapture | None:
    for attempt in range(1, 4):
        cap = cv2.VideoCapture(rtsp_url, CAPTURE_API)
        if cap.isOpened():
            configure_camera(cap, rtsp_url)
            return cap
        cap.release()
        if attempt < 3:
            logger.warning("Camera reconnect attempt %s/3", attempt)
    return None


def _get_http_session() -> requests.Session:
    auth_key = (
        f"{settings.hikvision_user}:{settings.hikvision_pass}:"
        f"{settings.hikvision_http_use_https}:{settings.hikvision_http_port}"
    )
    with _http_session_lock:
        if _http_session.session is None or _http_session.auth_key != auth_key:
            if _http_session.session is not None:
                _http_session.session.close()
            session = requests.Session()
            session.auth = HTTPDigestAuth(settings.hikvision_user, settings.hikvision_pass)
            _http_session.session = session
            _http_session.auth_key = auth_key
            _http_session.prev_gray = None
        return _http_session.session


def _fetch_http_snapshot(url: str, session: requests.Session) -> bytes:
    timeout = settings.hikvision_http_timeout_sec
    response = session.get(url, timeout=timeout)

    if response.status_code == 401:
        response = requests.get(
            url,
            auth=HTTPBasicAuth(settings.hikvision_user, settings.hikvision_pass),
            timeout=timeout,
        )

    if response.status_code != 200:
        raise RuntimeError(
            f"HTTP snapshot failed ({response.status_code}) for {url.split('//', 1)[-1]}"
        )

    payload = response.content
    if not is_jpeg_payload(payload):
        raise RuntimeError(f"HTTP snapshot returned non-JPEG payload from {url.split('//', 1)[-1]}")

    return payload


def _process_jpeg_frame(jpeg_bytes: bytes, prev_gray: np.ndarray | None) -> tuple[bytes, bool, float, np.ndarray]:
    frame = decode_jpeg(jpeg_bytes)
    frame = crop_frame(
        frame,
        crop_top=settings.hikvision_crop_top,
        crop_bottom=settings.hikvision_crop_bottom,
        crop_left=settings.hikvision_crop_left,
        crop_right=settings.hikvision_crop_right,
    )

    curr_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    motion_detected, motion_score, next_gray = detect_motion(
        prev_gray,
        curr_gray,
        settings.camera_motion_threshold,
    )

    if _needs_frame_processing():
        jpeg_bytes = encode_jpeg(frame, settings.hikvision_jpeg_quality)

    return jpeg_bytes, motion_detected, motion_score, next_gray


def _capture_http_frame() -> tuple[bytes, bool, float]:
    urls = build_http_snapshot_urls()
    session = _get_http_session()
    errors: list[str] = []

    for url in urls:
        try:
            jpeg_bytes = _fetch_http_snapshot(url, session)
            with _http_session_lock:
                processed = _process_jpeg_frame(jpeg_bytes, _http_session.prev_gray)
                _http_session.prev_gray = processed[3]
            return processed[0], processed[1], processed[2]
        except Exception as exc:
            errors.append(f"{url.split('//', 1)[-1]}: {exc}")
            logger.warning("HTTP snapshot attempt failed for %s: %s", url, exc)

    raise RuntimeError("Failed to fetch HTTP camera snapshot. " + "; ".join(errors))


def _capture_rtsp_frame() -> tuple[bytes, bool, float]:
    rtsp_url = build_rtsp_url(
        ip=settings.hikvision_front_ip,
        username=settings.hikvision_user,
        password=settings.hikvision_pass,
        channel=settings.hikvision_front_channel,
        port=settings.hikvision_rtsp_port,
        transport=settings.hikvision_rtsp_transport,
    )

    with _capture_session_lock:
        if _capture_session.cap is None or not _capture_session.cap.isOpened() or _capture_session.rtsp_url != rtsp_url:
            if _capture_session.cap is not None:
                _capture_session.release()
            cap = _open_camera(rtsp_url)
            if cap is None:
                raise RuntimeError("Failed to open RTSP camera stream")
            _capture_session.cap = cap
            _capture_session.rtsp_url = rtsp_url
            _capture_session.prev_gray = None

        cap = _capture_session.cap
        flush_camera_buffer(cap, is_ip=True)
        ret, frame = cap.read()
        if not ret or frame is None:
            _capture_session.release()
            raise RuntimeError("Failed to read frame from RTSP camera")

        frame = crop_frame(
            frame,
            crop_top=settings.hikvision_crop_top,
            crop_bottom=settings.hikvision_crop_bottom,
            crop_left=settings.hikvision_crop_left,
            crop_right=settings.hikvision_crop_right,
        )

        curr_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        motion_detected, motion_score, prev_gray = detect_motion(
            _capture_session.prev_gray,
            curr_gray,
            settings.camera_motion_threshold,
        )
        _capture_session.prev_gray = prev_gray

        jpeg_bytes = encode_jpeg(frame, settings.hikvision_jpeg_quality)
        return jpeg_bytes, motion_detected, motion_score


def _capture_mock_frame() -> tuple[bytes, bool, float]:
    jpeg_bytes = _load_mock_jpeg()
    return jpeg_bytes, False, 0.0


def _capture_once() -> None:
    captured_at = datetime.now(timezone.utc).astimezone()
    try:
        if settings.camera_mock:
            jpeg_bytes, motion_detected, motion_score = _capture_mock_frame()
            status: Literal["ok", "error", "mock", "disabled", "waiting"] = "mock"
        else:
            if not settings.hikvision_front_ip:
                raise RuntimeError("HIKVISION_FRONT_IP is not configured")
            if settings.camera_capture_mode == "http":
                jpeg_bytes, motion_detected, motion_score = _capture_http_frame()
            else:
                jpeg_bytes, motion_detected, motion_score = _capture_rtsp_frame()
            status = "ok"

        CAMERA_STATE.update(
            captured_at=captured_at,
            image_base64=base64.b64encode(jpeg_bytes).decode("ascii"),
            motion_detected=motion_detected,
            motion_score=round(motion_score, 2) if motion_score else motion_score,
            status=status,
            error_message=None,
        )
    except Exception as exc:
        logger.exception("Camera capture failed")
        previous = CAMERA_STATE.to_read()
        CAMERA_STATE.update(
            captured_at=captured_at,
            image_base64=previous.image_base64,
            motion_detected=False,
            motion_score=None,
            status="error",
            error_message=str(exc),
        )


async def _camera_worker(stop_event: asyncio.Event) -> None:
    interval = settings.camera_capture_interval_sec
    if settings.camera_capture_mode == "http":
        logger.info(
            "Camera worker started (mode=http, mock=%s, interval=%ss, target=%s:%s ch=%s)",
            settings.camera_mock,
            interval,
            settings.hikvision_front_ip or "(empty)",
            settings.hikvision_http_port,
            settings.hikvision_front_channel,
        )
    else:
        logger.info(
            "Camera worker started (mode=rtsp, mock=%s, interval=%ss, target=%s:%s ch=%s transport=%s)",
            settings.camera_mock,
            interval,
            settings.hikvision_front_ip or "(empty)",
            settings.hikvision_rtsp_port,
            settings.hikvision_front_channel,
            settings.hikvision_rtsp_transport,
        )
    try:
        while not stop_event.is_set():
            await asyncio.to_thread(_capture_once)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue
    except asyncio.CancelledError:
        raise
    finally:
        with _capture_session_lock:
            _capture_session.release()
        with _http_session_lock:
            _http_session.release()
        logger.info("Camera worker stopped")


async def start_camera_worker() -> asyncio.Task | None:
    global _workers_started, _worker_task, _stop_event

    if not settings.camera_enabled:
        CAMERA_STATE.update(
            captured_at=None,
            image_base64=None,
            motion_detected=False,
            motion_score=None,
            status="disabled",
            error_message="Camera worker is disabled (CAMERA_ENABLED=false)",
        )
        return None

    if not settings.camera_mock and not settings.hikvision_front_ip:
        logger.error(
            "Camera enabled but HIKVISION_FRONT_IP is empty — copy HIKVISION_* vars into tochnost/.env"
        )
        CAMERA_STATE.update(
            captured_at=None,
            image_base64=None,
            motion_detected=False,
            motion_score=None,
            status="error",
            error_message="HIKVISION_FRONT_IP не задан в tochnost/.env",
        )
        return None

    if _workers_started:
        return _worker_task

    _stop_event = asyncio.Event()
    _worker_task = asyncio.create_task(_camera_worker(_stop_event))
    _workers_started = True
    return _worker_task


async def stop_camera_worker() -> None:
    global _workers_started, _worker_task, _stop_event

    if not _workers_started:
        return

    if _stop_event is not None:
        _stop_event.set()

    if _worker_task is not None:
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass

    with _capture_session_lock:
        _capture_session.release()
    with _http_session_lock:
        _http_session.release()

    _workers_started = False
    _worker_task = None
    _stop_event = None


def get_snapshot() -> CameraSnapshotRead:
    return CAMERA_STATE.to_read()


def capture_rail_jpeg_once() -> bytes:
    """Однократный снимок с той же камеры, что на дашборде (HIKVISION_FRONT_*)."""
    if settings.camera_mock:
        jpeg_bytes, _, _ = _capture_mock_frame()
        return jpeg_bytes
    if not settings.hikvision_front_ip:
        raise RuntimeError("HIKVISION_FRONT_IP is not configured")
    if settings.camera_capture_mode == "http":
        jpeg_bytes, _, _ = _capture_http_frame()
    else:
        jpeg_bytes, _, _ = _capture_rtsp_frame()
    return jpeg_bytes
