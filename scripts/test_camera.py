#!/usr/bin/env python3
"""Проверка камеры с теми же настройками, что и worker дашборда."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.config import settings  # noqa: E402
from api.v1.camera.service import (  # noqa: E402
    build_http_snapshot_urls,
    build_rtsp_url,
    _capture_http_frame,
    _capture_rtsp_frame,
)


def main() -> int:
    print(
        f"CAMERA_ENABLED={settings.camera_enabled} "
        f"CAMERA_MOCK={settings.camera_mock} "
        f"CAMERA_CAPTURE_MODE={settings.camera_capture_mode}"
    )
    if not settings.hikvision_front_ip:
        print("ERROR: HIKVISION_FRONT_IP пустой")
        return 1

    if settings.camera_capture_mode == "http":
        urls = build_http_snapshot_urls()
        print("HTTP snapshot URLs:")
        for url in urls:
            print(f"  - {url}")
        capture = _capture_http_frame
    else:
        url = build_rtsp_url(
            settings.hikvision_front_ip,
            settings.hikvision_user,
            settings.hikvision_pass,
            settings.hikvision_front_channel,
            settings.hikvision_rtsp_port,
            settings.hikvision_rtsp_transport,
        )
        safe = url.replace(settings.hikvision_pass, "***")
        print(f"RTSP URL: {safe}")
        capture = _capture_rtsp_frame

    try:
        jpeg, motion, score = capture()
        print(f"OK: frame {len(jpeg)} bytes, motion={motion}, score={score}")
        return 0
    except Exception as exc:
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
