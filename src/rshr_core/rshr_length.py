"""RSHR length rules by mmAlongRail segment (post 1)."""

from __future__ import annotations

from typing import Literal

RSHR_LENGTH_NOMINAL_M = 25
RSHR_LENGTH_MIN_OK_M = 20
RSHR_LENGTH_DISCARD_BELOW_M = 15

RSHR_LENGTH_NOMINAL_MM = RSHR_LENGTH_NOMINAL_M * 1000
RSHR_LENGTH_MIN_OK_MM = RSHR_LENGTH_MIN_OK_M * 1000
RSHR_LENGTH_DISCARD_BELOW_MM = RSHR_LENGTH_DISCARD_BELOW_M * 1000

LengthClass = Literal["ok", "short", "discard"]


def segment_length_mm(start_mm: int, max_mm: int) -> int:
    return max(0, int(max_mm) - int(start_mm))


def classify_length_mm(length_mm: int) -> LengthClass:
    if length_mm < RSHR_LENGTH_DISCARD_BELOW_MM:
        return "discard"
    if length_mm < RSHR_LENGTH_MIN_OK_MM:
        return "short"
    return "ok"


def should_discard_rshr(length_mm: int) -> bool:
    return length_mm < RSHR_LENGTH_DISCARD_BELOW_MM


def is_length_ok(length_mm: int) -> bool:
    return length_mm >= RSHR_LENGTH_MIN_OK_MM
