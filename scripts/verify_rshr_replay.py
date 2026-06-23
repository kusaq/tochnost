#!/usr/bin/env python3
"""Replay rshr_data.jsonl through current post1/post2 FSM (parity with sensor/service.py)."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

NEW_RAIL_MM_RESET_DROP_MM = 3_000
POST1_MAX_PASS_SEC = 2400.0
POST2_MIN_SEGMENT_SEC = 3.0
TAIL_GRACE_SEC = 120.0


def parse_ts(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)


def laser_on(values: dict[str, Any]) -> bool:
    return bool(values.get("laserOnRailLeft") or values.get("laserOnRailRight"))


def mm_along(values: dict[str, Any]) -> int:
    return int(values.get("mmAlongRail") or 0)


@dataclass
class RailSession:
    rail_id: int
    start_time: datetime
    last_mm_along_rail: int
    last_timestamp: datetime
    start_mm_along_rail: int
    laser_off_at: datetime | None = None
    post2_depart_at: datetime | None = None
    end_time: datetime | None = None


@dataclass
class Post2Tracker:
    fifo_rail_ids: list[int] = field(default_factory=list)
    rail_at_post2: int | None = None
    post2_laser_on: bool = False
    last_laser_off_at: datetime | None = None
    unmatched_segments: int = 0

    def enqueue(self, rail_id: int) -> None:
        self.fifo_rail_ids.append(rail_id)

    def remove_from_fifo(self, rail_id: int) -> None:
        self.fifo_rail_ids = [x for x in self.fifo_rail_ids if x != rail_id]

    def on_post2_segment_start(self) -> int | None:
        if not self.fifo_rail_ids:
            self.unmatched_segments += 1
            self.post2_laser_on = True
            return None
        departed = self.rail_at_post2
        self.rail_at_post2 = self.fifo_rail_ids.pop(0)
        self.post2_laser_on = True
        return departed


@dataclass
class Counters:
    post1_packets: int = 0
    post2_packets: int = 0
    rails_opened: int = 0
    rails_parked: int = 0
    rails_discarded: int = 0
    rails_closed: int = 0
    sensor1_writes: int = 0
    dashboard_publishes: int = 0
    handoffs: int = 0
    skipped_no_laser: int = 0
    closed_rail_writes: int = 0
    first_open_ts: str | None = None
    first_open_mm: int | None = None
    max_mm_post1: int = 0
    open_events: list[str] = field(default_factory=list)


class Fsm:
    def __init__(self, seed: str) -> None:
        self.active: RailSession | None = None
        self.waiting: dict[int, RailSession] = {}
        self.closed: list[RailSession] = []
        self.post2 = Post2Tracker()
        self.post2_laser_was_on = False
        self._next_id = 0
        self.c = Counters()
        if seed == "stale_active_at_post2":
            self._seed_stale_active_at_post2()
        elif seed == "parked_at_post2":
            self._seed_parked_at_post2()

    def _seed_stale_active_at_post2(self) -> None:
        self._next_id = 1
        ts = parse_ts("2026-06-23T05:30:00")
        s = RailSession(1, ts, 24000, ts, 0, laser_off_at=None)
        self.active = s
        self.post2.rail_at_post2 = 1

    def _seed_parked_at_post2(self) -> None:
        self._next_id = 1
        ts = parse_ts("2026-06-23T05:30:00")
        s = RailSession(1, ts, 24000, ts, 0, laser_off_at=ts)
        self.waiting[1] = s
        self.post2.rail_at_post2 = 1
        self.active = None

    def is_in_closed(self, ts: datetime) -> int | None:
        for session in reversed(self.closed):
            if ts < session.start_time:
                continue
            end_ts = session.end_time or session.last_timestamp or session.start_time
            if ts <= end_ts:
                return session.rail_id
            if ts > end_ts:
                break
        return None

    def _transferred(self, active: RailSession) -> bool:
        if active.rail_id in self.waiting:
            return True
        return active.rail_id == self.post2.rail_at_post2

    def _mm_reset(self, active: RailSession, mm: int) -> bool:
        if mm + NEW_RAIL_MM_RESET_DROP_MM < active.last_mm_along_rail:
            return True
        return active.last_mm_along_rail >= 500 and mm < active.last_mm_along_rail - 500

    def _should_new(self, active: RailSession, values: dict[str, Any]) -> bool:
        if not laser_on(values):
            return False
        if self._transferred(active):
            return True
        if active.laser_off_at is not None:
            return True
        return self._mm_reset(active, mm_along(values))

    def _handoff(self, active: RailSession, ts: datetime) -> None:
        if self.active is None or self.active.rail_id != active.rail_id:
            return
        self.c.handoffs += 1
        if active.rail_id in self.waiting:
            self.active = None
            return
        if active.laser_off_at is None:
            active.laser_off_at = ts
        self._park_active()

    def _park_active(self) -> None:
        active = self.active
        if active is None or active.laser_off_at is None:
            return
        pass_sec = (active.laser_off_at - active.start_time).total_seconds()
        already_at_post2 = active.rail_id == self.post2.rail_at_post2
        if pass_sec > POST1_MAX_PASS_SEC and not already_at_post2:
            self.post2.remove_from_fifo(active.rail_id)
            self.c.rails_discarded += 1
            self.active = None
            return
        self.waiting[active.rail_id] = active
        self.active = None
        self.c.rails_parked += 1

    def _bind(self, ts: datetime, values: dict[str, Any]) -> None:
        prev = self.active
        if prev is not None:
            if prev.laser_off_at is not None or self._transferred(prev):
                if prev.laser_off_at is None:
                    prev.laser_off_at = ts
                self._park_active()

        self._next_id += 1
        mm = mm_along(values)
        self.active = RailSession(
            rail_id=self._next_id,
            start_time=ts,
            last_mm_along_rail=mm,
            last_timestamp=ts,
            start_mm_along_rail=mm,
        )
        self.post2.enqueue(self.active.rail_id)
        self.c.rails_opened += 1
        self.c.sensor1_writes += 1
        self.c.dashboard_publishes += 1
        if self.c.first_open_ts is None:
            self.c.first_open_ts = ts.isoformat()
            self.c.first_open_mm = mm
        self.c.open_events.append(f"rshr_opened #{self._next_id} @ {ts.isoformat()} mm={mm}")

    def process_post1(self, ts: datetime, values: dict[str, Any]) -> None:
        self.c.post1_packets += 1
        closed = self.is_in_closed(ts)
        if closed is not None:
            self.c.closed_rail_writes += 1
            self.c.sensor1_writes += 1
            return

        active = self.active
        if active is not None and self._transferred(active):
            self._handoff(active, ts)
            active = None

        if active is None:
            if not laser_on(values):
                self.c.skipped_no_laser += 1
                return
            self._bind(ts, values)
            return

        if self._should_new(active, values):
            if active.laser_off_at is None:
                active.laser_off_at = ts
            self._park_active()
            if self.active is not None:
                self._handoff(active, ts)
            self._bind(ts, values)
            return

        if ts < active.start_time:
            return

        if not laser_on(values):
            if active.laser_off_at is None:
                active.laser_off_at = ts
            self.c.sensor1_writes += 1
            return

        mm = mm_along(values)
        if mm > self.c.max_mm_post1:
            self.c.max_mm_post1 = mm
        active.last_mm_along_rail = mm
        active.last_timestamp = ts
        self.c.sensor1_writes += 1
        self.c.dashboard_publishes += 1

    def process_post2(self, ts: datetime, values: dict[str, Any]) -> None:
        self.c.post2_packets += 1
        on = laser_on(values)
        was_on = self.post2_laser_was_on

        if on and not was_on:
            if (
                self.post2.last_laser_off_at is not None
                and (ts - self.post2.last_laser_off_at) < timedelta(seconds=POST2_MIN_SEGMENT_SEC)
            ):
                pass
            elif not self.post2.fifo_rail_ids:
                self.post2.unmatched_segments += 1
                self.post2_laser_was_on = True
            else:
                departed = self.post2.on_post2_segment_start()
                self.post2_laser_was_on = True
                recognized = self.post2.rail_at_post2
                if departed is not None:
                    self._close(departed, ts)
                if recognized is not None:
                    active = self.active
                    if active is not None and active.rail_id == recognized:
                        self._handoff(active, ts)
        elif not on and was_on:
            self.post2_laser_was_on = False
            self.post2.last_laser_off_at = ts

    def _close(self, rail_id: int, ts: datetime) -> None:
        session = self.waiting.pop(rail_id, None)
        if session is None and self.active and self.active.rail_id == rail_id:
            session = self.active
            self.active = None
        if session is None:
            return
        session.end_time = ts
        self.closed.append(session)
        self.c.rails_closed += 1


def load_events(path: str) -> list[tuple[datetime, str, dict[str, Any]]]:
    events: list[tuple[datetime, str, dict[str, Any]]] = []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = parse_ts(record["timestamp"])
            sid = record.get("sensor_id")
            if sid == 1:
                events.append((ts, "post1", record["values"]))
            elif sid == 2:
                events.append((ts, "post2", record["values"]))
    events.sort(key=lambda x: x[0])
    return events


def run(path: str, seed: str) -> Counters:
    fsm = Fsm(seed)
    for ts, kind, values in load_events(path):
        if kind == "post1":
            fsm.process_post1(ts, values)
        else:
            fsm.process_post2(ts, values)
    return fsm.c


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="/Users/kusaq/Desktop/rshr_data.jsonl")
    args = parser.parse_args()

    for seed in ("fresh", "parked_at_post2", "stale_active_at_post2"):
        c = run(args.path, seed)
        print(f"=== seed={seed} ===")
        print(f"  post1 packets:        {c.post1_packets}")
        print(f"  post2 packets:        {c.post2_packets}")
        print(f"  rails opened:         {c.rails_opened}")
        print(f"  first open:           {c.first_open_ts} mm={c.first_open_mm}")
        print(f"  handoffs:             {c.handoffs}")
        print(f"  sensor1 writes:       {c.sensor1_writes}")
        print(f"  dashboard publishes:  {c.dashboard_publishes}")
        print(f"  max mm post1:         {c.max_mm_post1}")
        print(f"  skipped (no laser):   {c.skipped_no_laser}")
        print(f"  closed rail writes:   {c.closed_rail_writes}")
        print(f"  parked / discarded:   {c.rails_parked} / {c.rails_discarded}")
        for ev in c.open_events:
            print(f"  -> {ev}")
        ok = c.rails_opened >= 1 and c.sensor1_writes > 0 and c.dashboard_publishes > 0
        print(f"  RESULT: {'OK' if ok else 'FAIL'}")
        print()


if __name__ == "__main__":
    main()
