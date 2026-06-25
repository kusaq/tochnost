#!/usr/bin/env python3
"""Диагностика «РШР проехала пост 2, но не закрылась» (зависла «В процессе»).

Воспроизводит логику финализации поста 2 из live-FSM
(`api/v1/sensor/service.py`: `process_second_sensor1_data` + `_confirm_post2_segment`
+ `_maybe_close_departed_post2_rail`) на паре JSONL-логов и показывает, какие РШР
закрываются штатно (приход следующего сегмента), а какие остались бы висеть без
страховки `POST2_DEPART_GRACE_SEC`.

Зачем: рельс на посту 2 штатно финализируется ТОЛЬКО приходом следующего рельса.
Последний рельс смены/партии преемника не имеет → без grace висит «В процессе»,
хотя физически уже уехал (лазер поста 2 погас). Скрипт подтверждает, что фикс
закрывает такой рельс через POST2_DEPART_GRACE_SEC секунд после гашения лазера.

Запуск:
    cd tochnost
    python scripts/diagnose_post2_stuck_rail.py \
        --rshr   /path/to/rshr_data.jsonl \
        --modbus /path/to/modbus_data.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta

# Те же дефолты, что в rshr_core/config.py (держим скрипт самодостаточным).
LASER_CONFIRM_ADVANCE_MM = int(os.environ.get("LASER_CONFIRM_ADVANCE_MM", 200))
POST2_MIN_SEGMENT_SEC = float(os.environ.get("POST2_MIN_SEGMENT_SEC", 3.0))
POST2_DEPART_GRACE_SEC = float(os.environ.get("POST2_DEPART_GRACE_SEC", 120.0))


def _parse_ts(s: str) -> datetime:
    s = s.replace("Z", "")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def _load(path: str, src: str) -> list[tuple[datetime, str, dict]]:
    out: list[tuple[datetime, str, dict]] = []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)  # рваные строки лога пропускаем
            except json.JSONDecodeError:
                continue
            ts = rec.get("timestamp")
            if not ts:
                continue
            out.append((_parse_ts(ts), src, rec))
    return out


def run(events: list[tuple[datetime, str, dict]], *, apply_grace: bool) -> dict:
    fifo: list[int] = []
    rail_at_post2: int | None = 100          # рельс уже на посту 2 на старте захвата
    laser_was_on = True
    last_laser_off_at: datetime | None = None
    pending = False
    p_mm: int | None = None
    p_ts: datetime | None = None
    sessions = {100: {"depart_at": None}}
    next_id = 101
    closed: list[tuple[int, str, str]] = []

    p1_on = False
    p1_pending = False
    p1_mm: int | None = None

    def finalize(rid: int, ts: datetime, reason: str) -> None:
        s = sessions.get(rid)
        if s is None or s["depart_at"] is not None:
            return
        s["depart_at"] = ts
        closed.append((rid, ts.strftime("%H:%M:%S"), reason))

    for ts, src, rec in events:
        v = rec.get("values", {})

        if src == "rshr" and rec.get("sensor_id") == 1:
            on = bool(v.get("laserOnRailLeft") or v.get("laserOnRailRight"))
            mm = int(v.get("mmAlongRail", 0) or 0)
            if on and not p1_on:
                p1_pending, p1_mm = True, mm
            elif on and p1_on and p1_pending and mm - (p1_mm or 0) >= LASER_CONFIRM_ADVANCE_MM:
                p1_pending = False
                sessions[next_id] = {"depart_at": None}
                fifo.append(next_id)             # enqueue_opened_rail
                next_id += 1
            p1_on = on

        elif src == "rshr" and rec.get("sensor_id") == 2:
            on = bool(v.get("laserOnRailLeft") or v.get("laserOnRailRight"))
            mm = int(v.get("mmAlongRail", 0) or 0)
            if on and not laser_was_on:
                laser_was_on, pending, p_mm, p_ts = True, True, mm, ts
            elif on and laser_was_on and pending:
                adv = p_mm is not None and (mm - p_mm) >= LASER_CONFIRM_ADVANCE_MM
                held = p_ts is not None and (ts - p_ts) >= timedelta(seconds=POST2_MIN_SEGMENT_SEC)
                if adv or held:
                    pending = False
                    if fifo:                      # on_post2_segment_start
                        departed = rail_at_post2
                        rail_at_post2 = fifo.pop(0)
                        if departed is not None:
                            finalize(departed, ts, "next_segment")
            elif not on and laser_was_on:
                laser_was_on = False
                last_laser_off_at = ts
                pending = False

        # _maybe_close_departed_post2_rail — страховка на каждом событии
        if apply_grace and rail_at_post2 is not None and not laser_was_on \
                and last_laser_off_at is not None \
                and ts >= last_laser_off_at + timedelta(seconds=POST2_DEPART_GRACE_SEC):
            s = sessions.get(rail_at_post2)
            if s is not None and s["depart_at"] is None:
                finalize(rail_at_post2, ts, "grace_no_successor")
            rail_at_post2 = None
            last_laser_off_at = None

    stuck = rail_at_post2 if rail_at_post2 is not None and sessions.get(rail_at_post2, {}).get("depart_at") is None else None
    return {"closed": closed, "stuck_rail_at_post2": stuck}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rshr", required=True)
    ap.add_argument("--modbus", required=True)
    args = ap.parse_args()

    events = _load(args.rshr, "rshr") + _load(args.modbus, "modbus")
    events.sort(key=lambda x: x[0])
    print(f"events={len(events)}  grace={POST2_DEPART_GRACE_SEC:.0f}s\n")

    for apply_grace in (False, True):
        res = run(events, apply_grace=apply_grace)
        tag = "С ФИКСОМ (grace)" if apply_grace else "БЕЗ ФИКСА"
        print(f"=== {tag} ===")
        for rid, t, reason in res["closed"]:
            print(f"  закрыт РШР #{rid} в {t} ({reason})")
        if res["stuck_rail_at_post2"] is not None:
            print(f"  ✗ ЗАВИС «В процессе»: РШР #{res['stuck_rail_at_post2']} (уехал, но не финализирован)")
        else:
            print("  ✓ зависших РШР на посту 2 нет")
        print()


if __name__ == "__main__":
    main()
