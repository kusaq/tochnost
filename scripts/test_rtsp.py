#!/usr/bin/env python3
"""Проверка RTSP-камеры с теми же настройками, что и worker дашборда."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.config import settings  # noqa: E402
from api.v1.camera.service import build_rtsp_url, _capture_rtsp_frame  # noqa: E402


def main() -> int:
    print(f"CAMERA_ENABLED={settings.camera_enabled} CAMERA_MOCK={settings.camera_mock}")
    if not settings.hikvision_front_ip:
        print("ERROR: HIKVISION_FRONT_IP пустой")
        return 1

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

    try:
        jpeg, motion, score = _capture_rtsp_frame()
        print(f"OK: frame {len(jpeg)} bytes, motion={motion}, score={score}")
        return 0
    except Exception as exc:
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
