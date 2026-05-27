"""Modbus tightening cycles: 4 screws (M1–M4) per sleeper."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

MOMENT_KEYS = ("M1", "M2", "M3", "M4")
FREQ_KEYS = ("f1", "f2", "f3", "f4")

# Pydantic / API field names
_MOMENT_ALIASES = {
    "M1": ("frequency_torque_1",),
    "M2": ("frequency_torque_2",),
    "M3": ("frequency_torque_3",),
    "M4": ("frequency_torque_4",),
}
_FREQ_ALIASES = {
    "f1": ("converter_frequency_1",),
    "f2": ("converter_frequency_2",),
    "f3": ("converter_frequency_3",),
    "f4": ("converter_frequency_4",),
}


def _as_dict(values: Any) -> dict[str, Any]:
    if hasattr(values, "model_dump"):
        return values.model_dump()
    if isinstance(values, dict):
        return values
    return {}


def _f(values: dict[str, Any], key: str) -> float:
    v = values.get(key, 0)
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _moment(values: dict[str, Any], m_key: str) -> float:
    v = _f(values, m_key)
    if v > 0:
        return v
    for alias in _MOMENT_ALIASES.get(m_key, ()):
        v = _f(values, alias)
        if v > 0:
            return v
    return 0.0


def _freq(values: dict[str, Any], f_key: str) -> float:
    v = _f(values, f_key)
    if v > 0:
        return v
    for alias in _FREQ_ALIASES.get(f_key, ()):
        v = _f(values, alias)
        if v > 0:
            return v
    return 0.0


def has_moment_activity(values: Any) -> bool:
    """Cycle start: moments M1–M4 only (not frequency alone)."""
    d = _as_dict(values)
    return any(_moment(d, k) > 0 for k in MOMENT_KEYS)


def has_torque_activity(values: Any) -> bool:
    """Any moment or frequency activity (legacy name; prefer has_moment_activity for start)."""
    d = _as_dict(values)
    if has_moment_activity(d):
        return True
    return any(_freq(d, k) > 0 for k in FREQ_KEYS)


def all_torque_zero(values: Any) -> bool:
    d = _as_dict(values)
    return not has_moment_activity(d) and not any(_freq(d, k) > 0 for k in FREQ_KEYS)


def bump_peaks(
    max_moment: dict[str, float],
    max_freq: dict[str, float],
    values: Any,
) -> None:
    d = _as_dict(values)
    for k in MOMENT_KEYS:
        max_moment[k] = max(max_moment[k], _moment(d, k))
    for k in FREQ_KEYS:
        max_freq[k] = max(max_freq[k], _freq(d, k))


@dataclass
class CyclePeaks:
    max_moment: dict[str, float] = field(default_factory=lambda: {k: 0.0 for k in MOMENT_KEYS})
    max_freq: dict[str, float] = field(default_factory=lambda: {k: 0.0 for k in FREQ_KEYS})
    last_values: dict[str, Any] = field(default_factory=dict)

    def bump(self, values: Any) -> None:
        self.last_values = _as_dict(values)
        bump_peaks(self.max_moment, self.max_freq, values)


@dataclass
class CompletedCycle:
    start_ts: Any
    end_ts: Any
    mm_along_rail: int
    peaks: CyclePeaks
    resistance_samples: list[float] = field(default_factory=list)
    temperature_samples: list[float] = field(default_factory=list)

    @property
    def resistance_avg(self) -> float | None:
        if not self.resistance_samples:
            return None
        return sum(self.resistance_samples) / len(self.resistance_samples)

    @property
    def resistance_min(self) -> float | None:
        return min(self.resistance_samples) if self.resistance_samples else None

    @property
    def resistance_max(self) -> float | None:
        return max(self.resistance_samples) if self.resistance_samples else None

    @property
    def temperature_avg(self) -> float | None:
        if not self.temperature_samples:
            return None
        return sum(self.temperature_samples) / len(self.temperature_samples)

    def nut_peaks(self, channel: int) -> dict[str, float]:
        m_key = f"M{channel}"
        f_key = f"f{channel}"
        return {
            "max_moment_nm": round(self.peaks.max_moment[m_key], 4),
            "max_frequency_hz": round(self.peaks.max_freq[f_key], 4),
        }

    def sleeper_dict(self, index: int) -> dict[str, Any]:
        return {
            "sleeper_index": index,
            "mm_along_rail": self.mm_along_rail,
            "start_ts": str(self.start_ts),
            "end_ts": str(self.end_ts),
            "nuts": [{"channel": ch, **self.nut_peaks(int(ch[-1]))} for ch in MOMENT_KEYS],
            "resistance_avg": round(self.resistance_avg, 4) if self.resistance_avg is not None else None,
            "resistance_min": round(self.resistance_min, 4) if self.resistance_min is not None else None,
            "resistance_max": round(self.resistance_max, 4) if self.resistance_max is not None else None,
            "temperature_avg": round(self.temperature_avg, 4) if self.temperature_avg is not None else None,
        }

    def screws_for_sleeper(self, sleeper_index: int, screw_index_start: int) -> list[dict[str, Any]]:
        env = {
            "mm_along_rail": self.mm_along_rail,
            "sleeper_index": sleeper_index,
            "start_ts": str(self.start_ts),
            "end_ts": str(self.end_ts),
            "resistance_avg": round(self.resistance_avg, 4) if self.resistance_avg is not None else None,
            "resistance_min": round(self.resistance_min, 4) if self.resistance_min is not None else None,
            "resistance_max": round(self.resistance_max, 4) if self.resistance_max is not None else None,
            "temperature_avg": round(self.temperature_avg, 4) if self.temperature_avg is not None else None,
        }
        out = []
        for ch in range(1, 5):
            peaks = self.nut_peaks(ch)
            out.append(
                {
                    "screw_index": screw_index_start + ch - 1,
                    "channel": ch,
                    "max_moment_nm": peaks["max_moment_nm"],
                    "max_frequency_hz": peaks["max_frequency_hz"],
                    **env,
                }
            )
        return out


def detect_cycles_in_window(
    modbus_events: list[tuple[Any, dict[str, Any]]],
    t0: Any,
    t1: Any,
    mm_at,
    *,
    collect_env_during_cycle: bool = True,
    cycle_end_zero_packets: int = 1,
    finish_incomplete_at_end: bool = False,
    min_peak_moment_nm: float = 15.0,
    min_inter_cycle_sec: float | None = None,
) -> list[CompletedCycle]:
    """Find completed tightening cycles in [t0, t1]. Cycle start on M1–M4 only."""
    completed: list[CompletedCycle] = []
    active = False
    peaks = CyclePeaks()
    start_ts = None
    start_mm = 0
    r_samples: list[float] = []
    t_samples: list[float] = []
    zero_streak = 0
    last_cycle_end: Any = None

    def finish(end_ts):
        nonlocal active, peaks, start_ts, start_mm, r_samples, t_samples, zero_streak, last_cycle_end
        completed.append(
            CompletedCycle(
                start_ts=start_ts,
                end_ts=end_ts,
                mm_along_rail=start_mm,
                peaks=peaks,
                resistance_samples=list(r_samples),
                temperature_samples=list(t_samples),
            )
        )
        last_cycle_end = end_ts
        active = False
        peaks = CyclePeaks()
        r_samples = []
        t_samples = []
        zero_streak = 0

    for ts, v in modbus_events:
        if ts < t0:
            continue
        if ts > t1:
            break
        d = v if isinstance(v, dict) else _as_dict(v)
        if collect_env_during_cycle and active:
            r_samples.append(_f(d, "R") or _f(d, "resistance"))
            t_samples.append(_f(d, "T") or _f(d, "temperature"))

        if not active:
            if has_moment_activity(d):
                if (
                    min_inter_cycle_sec is not None
                    and last_cycle_end is not None
                    and (ts - last_cycle_end).total_seconds() < min_inter_cycle_sec
                ):
                    continue
                active = True
                start_ts = ts
                start_mm = mm_at(ts)
                peaks = CyclePeaks()
                peaks.bump(d)
                r_samples = [_f(d, "R") or _f(d, "resistance")]
                t_samples = [_f(d, "T") or _f(d, "temperature")]
                zero_streak = 0
        else:
            peaks.bump(d)
            if all_torque_zero(d):
                zero_streak += 1
                if zero_streak >= cycle_end_zero_packets:
                    finish(ts)
            else:
                zero_streak = 0

    if active and start_ts is not None and finish_incomplete_at_end:
        finish(modbus_events[-1][0] if modbus_events else start_ts)

    filtered: list[CompletedCycle] = []
    for c in completed:
        peak = max(c.peaks.max_moment.values()) if c.peaks.max_moment else 0.0
        if peak >= min_peak_moment_nm:
            filtered.append(c)
    return filtered
