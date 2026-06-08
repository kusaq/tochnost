#!/usr/bin/env python3
"""Deprecated: используйте scripts/test_camera.py."""
import subprocess
import sys
from pathlib import Path

raise SystemExit(
    subprocess.call([sys.executable, str(Path(__file__).resolve().parent / "test_camera.py"), *sys.argv[1:]])
)
