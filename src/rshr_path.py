"""Ensure workspace libs/rshr_core is on sys.path for local and Docker runs."""

from __future__ import annotations

import sys
from pathlib import Path


def bootstrap() -> None:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "libs",
        here.parents[1] / "libs",
        Path("/app/libs"),
    ]
    for base in candidates:
        if (base / "rshr_core").is_dir():
            s = str(base)
            if s not in sys.path:
                sys.path.insert(0, s)
            return


bootstrap()
