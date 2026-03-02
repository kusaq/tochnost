#!/usr/bin/env python3
import argparse
import random
import sys
import time
import csv
from datetime import datetime, timedelta

import requests


def fmt_ts(dt: datetime) -> str:
    # ISO с миллисекундами (совместимо с fromisoformat)
    return dt.isoformat(timespec="milliseconds")


def send_sensor1(base_url: str, payload: dict) -> requests.Response:
    url = f"{base_url}/api/v1/sensor/first"
    resp = requests.post(url, json=payload, timeout=10)
    print(
        f"[S1] POST {url} "
        f"ts={payload.get('timestamp')} "
        f"status={resp.status_code}"
    )
    return resp


def send_sensor2(base_url: str, payload: dict) -> requests.Response:
    url = f"{base_url}/api/v1/sensor/second"
    resp = requests.post(url, json=payload, timeout=10)
    print(
        f"[S2] POST {url} "
        f"ts={payload.get('timestamp')} "
        f"status={resp.status_code}"
    )
    return resp


S1_RANGE_KEYS = (
    "mm_gauge",
    "mm_side_wear_left",
    "mm_side_wear_right",
    "mm_vertical_wear_left",
    "mm_vertical_wear_right",
    "rad_rail_tilt_left",
    "rad_rail_tilt_right",
)


def gen_sensor1_payload(
    now: datetime,
    mm_along_rail: int,
    s1_cache: dict[int, dict],
    *,
    sensor_id: int = 1,
    laser_on_rail_left: bool | None = None,
    laser_on_rail_right: bool | None = None,
    laser_on_tie_left: bool | None = None,
    laser_on_tie_right: bool | None = None,
    use_camel_case: bool = True,
) -> dict:
    # значения диапазонных метрик по одному и тому же мм должны быть одинаковы между тиками
    if mm_along_rail not in s1_cache:
        s1_cache[mm_along_rail] = {
            "mm_gauge": round(random.uniform(1520.0, 1526.0), 2),
            "mm_side_wear_left": round(random.uniform(0.0, 2.0), 2),
            "mm_side_wear_right": round(random.uniform(0.0, 2.0), 2),
            "mm_vertical_wear_left": round(random.uniform(0.0, 2.0), 2),
            "mm_vertical_wear_right": round(random.uniform(0.0, 2.0), 2),
            "rad_rail_tilt_left": round(random.uniform(0.0, 0.01), 4),
            "rad_rail_tilt_right": round(random.uniform(0.0, 0.01), 4),
        }
    s1r = s1_cache[mm_along_rail]
    left_on = random.choice([True, False]) if laser_on_rail_left is None else bool(laser_on_rail_left)
    right_on = random.choice([True, False]) if laser_on_rail_right is None else bool(laser_on_rail_right)
    tie_left = random.choice([True, False]) if laser_on_tie_left is None else bool(laser_on_tie_left)
    tie_right = random.choice([True, False]) if laser_on_tie_right is None else bool(laser_on_tie_right)
    values_snake = {
        "encoder1": random.randint(1000, 2000),
        "encoder2": random.randint(1000, 2000),
        "encoder3": random.randint(1000, 2000),
        "encoder4": random.randint(1000, 2000),
        "mm_along_rail": mm_along_rail,
        "laser_on_rail_left": left_on,
        "laser_on_rail_right": right_on,
        "laser_on_tie_left": tie_left,
        "laser_on_tie_right": tie_right,
        # диапазонные метрики — из кеша по текущему мм
        "mm_gauge": s1r["mm_gauge"],
        "mm_side_wear_left": s1r["mm_side_wear_left"],
        "mm_side_wear_right": s1r["mm_side_wear_right"],
        "mm_vertical_wear_left": s1r["mm_vertical_wear_left"],
        "mm_vertical_wear_right": s1r["mm_vertical_wear_right"],
        "rad_rail_tilt_left": s1r["rad_rail_tilt_left"],
        "rad_rail_tilt_right": s1r["rad_rail_tilt_right"],
        "mm_bolt_height_left_inner": round(random.uniform(0.0, 5.0), 2),
        "mm_bolt_height_left_outer": round(random.uniform(0.0, 5.0), 2),
        "mm_bolt_height_right_inner": round(random.uniform(0.0, 5.0), 2),
        "mm_bolt_height_right_outer": round(random.uniform(0.0, 5.0), 2),
    }
    if use_camel_case:
        values = {
            "encoder1": values_snake["encoder1"],
            "encoder2": values_snake["encoder2"],
            "encoder3": values_snake["encoder3"],
            "encoder4": values_snake["encoder4"],
            "mmAlongRail": values_snake["mm_along_rail"],
            "laserOnRailLeft": values_snake["laser_on_rail_left"],
            "laserOnRailRight": values_snake["laser_on_rail_right"],
            "laserOnTieLeft": values_snake["laser_on_tie_left"],
            "laserOnTieRight": values_snake["laser_on_tie_right"],
            "mmGauge": values_snake["mm_gauge"],
            "mmSideWearLeft": values_snake["mm_side_wear_left"],
            "mmSideWearRight": values_snake["mm_side_wear_right"],
            "mmVerticalWearLeft": values_snake["mm_vertical_wear_left"],
            "mmVerticalWearRight": values_snake["mm_vertical_wear_right"],
            "radRailTiltLeft": values_snake["rad_rail_tilt_left"],
            "radRailTiltRight": values_snake["rad_rail_tilt_right"],
            "mmBoltHeightLeftInner": values_snake["mm_bolt_height_left_inner"],
            "mmBoltHeightLeftOuter": values_snake["mm_bolt_height_left_outer"],
            "mmBoltHeightRightInner": values_snake["mm_bolt_height_right_inner"],
            "mmBoltHeightRightOuter": values_snake["mm_bolt_height_right_outer"],
        }
    else:
        values = values_snake
    return {
        "sensor_id": sensor_id,
        "timestamp": fmt_ts(now),
        "values": values,
    }


def gen_sensor2_payload(
    now: datetime,
    twisting: bool,
    mm_along_rail: int,
    res_cache: dict[int, float],
    twist_idx: int | None = None,
    twist_total: int | None = None,
    torque_peak_cache: dict[int, int] | None = None,
) -> dict:
    def nz(a: int, b: int) -> int:
        return random.randint(a, b)
    on = 1 if twisting else 0
    # сопротивление также фиксируем по текущему мм
    if mm_along_rail not in res_cache:
        # чаще в норме (100..500), иногда вне норм (0..80 или 520..600)
        if random.random() < 0.8:
            res_cache[mm_along_rail] = round(random.uniform(150.0, 450.0), 2)
        else:
            res_cache[mm_along_rail] = round(random.choice([random.uniform(0.0, 80.0), random.uniform(520.0, 600.0)]), 2)

    # профиль момента: при закручивании растёт до пика и затем резко падает (на move он 0)
    if twisting and twist_idx is not None and twist_total and twist_total > 0:
        if torque_peak_cache is not None and mm_along_rail not in torque_peak_cache:
            torque_peak_cache[mm_along_rail] = nz(300, 700)
        peak = (torque_peak_cache or {}).get(mm_along_rail, nz(300, 700))
        frac = max(0.0, min(1.0, (twist_idx + 1) / float(twist_total)))
        base_torque = max(10, int(peak * frac))
        # небольшая разбежка по каналам ±5%
        def jitter(val: int) -> int:
            return max(0, int(val * (1.0 + random.uniform(-0.05, 0.05))))
        m1 = jitter(base_torque)
        m2 = jitter(base_torque)
        m3 = jitter(base_torque)
        m4 = jitter(base_torque)
    else:
        m1 = m2 = m3 = m4 = 0

    return {
        "timestamp": fmt_ts(now),
        "values": {
            "R": res_cache[mm_along_rail],
            "T": round(random.uniform(0.0, 40.0), 4),
            "H": round(random.uniform(0.0, 100.0), 4),
            "ST1": on, "ST2": on, "ST3": on, "ST4": on,
            "M1": m1,
            "M2": m2,
            "M3": m3,
            "M4": m4,
            "f1": nz(10, 5000) if twisting else 0,
            "f2": nz(10, 5000) if twisting else 0,
            "f3": nz(10, 5000) if twisting else 0,
            "f4": nz(10, 5000) if twisting else 0,
        },
    }


def _s1_get(values: dict, snake: str, camel: str):
    if snake in values:
        return values[snake]
    return values.get(camel)


def flatten_s1(rail: int, nut: int, phase: str, payload: dict) -> dict:
    v = payload["values"]
    return {
        "rail": rail,
        "nut": nut,
        "phase": phase,
        "sensor_id": payload.get("sensor_id"),
        "timestamp": payload["timestamp"],
        "mmAlongRail": _s1_get(v, "mm_along_rail", "mmAlongRail"),
        "encoder1": v["encoder1"],
        "encoder2": v["encoder2"],
        "encoder3": v["encoder3"],
        "encoder4": v["encoder4"],
        "laserOnRailLeft": _s1_get(v, "laser_on_rail_left", "laserOnRailLeft"),
        "laserOnRailRight": _s1_get(v, "laser_on_rail_right", "laserOnRailRight"),
        "laserOnTieLeft": _s1_get(v, "laser_on_tie_left", "laserOnTieLeft"),
        "laserOnTieRight": _s1_get(v, "laser_on_tie_right", "laserOnTieRight"),
        "mmGauge": _s1_get(v, "mm_gauge", "mmGauge"),
        "mmSideWearLeft": _s1_get(v, "mm_side_wear_left", "mmSideWearLeft"),
        "mmSideWearRight": _s1_get(v, "mm_side_wear_right", "mmSideWearRight"),
        "mmVerticalWearLeft": _s1_get(v, "mm_vertical_wear_left", "mmVerticalWearLeft"),
        "mmVerticalWearRight": _s1_get(v, "mm_vertical_wear_right", "mmVerticalWearRight"),
        "radRailTiltLeft": _s1_get(v, "rad_rail_tilt_left", "radRailTiltLeft"),
        "radRailTiltRight": _s1_get(v, "rad_rail_tilt_right", "radRailTiltRight"),
        "mmBoltHeightLeftInner": _s1_get(v, "mm_bolt_height_left_inner", "mmBoltHeightLeftInner"),
        "mmBoltHeightLeftOuter": _s1_get(v, "mm_bolt_height_left_outer", "mmBoltHeightLeftOuter"),
        "mmBoltHeightRightInner": _s1_get(v, "mm_bolt_height_right_inner", "mmBoltHeightRightInner"),
        "mmBoltHeightRightOuter": _s1_get(v, "mm_bolt_height_right_outer", "mmBoltHeightRightOuter"),
    }


def flatten_s2(rail: int, nut: int, phase: str, twisting: bool, payload: dict) -> dict:
    v = payload["values"]
    return {
        "rail": rail,
        "nut": nut,
        "phase": phase,
        "timestamp": payload["timestamp"],
        "twisting": twisting,
        "R": v["R"],
        "T": v["T"],
        "H": v["H"],
        "ST1": v["ST1"],
        "ST2": v["ST2"],
        "ST3": v["ST3"],
        "ST4": v["ST4"],
        "M1": v["M1"],
        "M2": v["M2"],
        "M3": v["M3"],
        "M4": v["M4"],
        "f1": v["f1"],
        "f2": v["f2"],
        "f3": v["f3"],
        "f4": v["f4"],
    }


def main():
    parser = argparse.ArgumentParser(description="Send mock sensor data to API")
    parser.add_argument("--base-url", default="https://api.rzd.ravs.pro", help="Base URL, e.g. http://localhost:8000")
    parser.add_argument("--interval", type=float, default=0.03, help="Seconds between active ticks")
    parser.add_argument("--idle-ticks", type=int, default=3, help="How many idle ticks before rail starts")
    parser.add_argument("--rail-start-ticks", type=int, default=1, help="How many start ticks with left laser on")
    parser.add_argument("--step-mm", type=int, default=1, help="mmAlongRail increment per move step")
    parser.add_argument("--rails", type=int, default=2, help="How many rails to simulate")
    parser.add_argument("--nuts-per-rail", type=int, default=20, help="How many nuts per rail")
    parser.add_argument("--twist-ticks", type=int, default=3, help="Ticks twisting at each nut")
    parser.add_argument("--move-ticks", type=int, default=1, help="Ticks moving between nuts")
    parser.add_argument("--closing-ticks", type=int, default=3, help="Trailing idle ticks with zeros to close active rails")
    parser.add_argument("--csv1", default="sensor1.csv", help="CSV file path for Sensor1 data")
    parser.add_argument("--csv2", default="sensor2.csv", help="CSV file path for Sensor2 data")
    args = parser.parse_args()

    now = datetime.now()
    # Prepare CSV writers
    s1_fields = [
        "rail", "nut", "phase", "timestamp", "mmAlongRail",
        "sensor_id",
        "encoder1", "encoder2", "encoder3", "encoder4",
        "laserOnRailLeft", "laserOnRailRight", "laserOnTieLeft", "laserOnTieRight",
        "mmGauge", "mmSideWearLeft", "mmSideWearRight",
        "mmVerticalWearLeft", "mmVerticalWearRight",
        "radRailTiltLeft", "radRailTiltRight",
        "mmBoltHeightLeftInner", "mmBoltHeightLeftOuter",
        "mmBoltHeightRightInner", "mmBoltHeightRightOuter",
    ]
    s2_fields = [
        "rail", "nut", "phase", "timestamp", "twisting",
        "R", "T", "H", "ST1", "ST2", "ST3", "ST4",
        "M1", "M2", "M3", "M4", "f1", "f2", "f3", "f4",
    ]
    f1 = open(args.csv1, "w", newline="", encoding="utf-8")
    f2 = open(args.csv2, "w", newline="", encoding="utf-8")
    w1 = csv.DictWriter(f1, fieldnames=s1_fields)
    w2 = csv.DictWriter(f2, fieldnames=s2_fields)
    w1.writeheader()
    w2.writeheader()

    for rail_idx in range(args.rails):
        mm = 0
        # кеши значений по мм для текущей рельсы
        s1_cache_by_mm: dict[int, dict] = {}
        res_cache_by_mm: dict[int, float] = {}
        torque_peak_by_mm: dict[int, int] = {}
        # Idle ticks before rail starts (лазеры выключены, mmAlongRail=0)
        for _ in range(args.idle_ticks):
            s1_payload = gen_sensor1_payload(
                now,
                0,
                s1_cache_by_mm,
                sensor_id=1,
                laser_on_rail_left=False,
                laser_on_rail_right=False,
                laser_on_tie_left=False,
                laser_on_tie_right=False,
            )
            r1 = send_sensor1(args.base_url, s1_payload)
            if r1.status_code >= 300:
                print(r1.text, file=sys.stderr)
            w1.writerow(flatten_s1(rail_idx + 1, 0, "idle", s1_payload))

            s2_payload = gen_sensor2_payload(
                now,
                twisting=False,
                mm_along_rail=0,
                res_cache=res_cache_by_mm,
            )
            r2 = send_sensor2(args.base_url, s2_payload)
            if r2.status_code >= 300:
                print(r2.text, file=sys.stderr)
            w2.writerow(flatten_s2(rail_idx + 1, 0, "idle", False, s2_payload))
            now = now + timedelta(seconds=args.interval)
            time.sleep(args.interval)

        # Rail start tick(s): левый лазер включен
        for _ in range(args.rail_start_ticks):
            s1_payload = gen_sensor1_payload(
                now,
                0,
                s1_cache_by_mm,
                sensor_id=1,
                laser_on_rail_left=True,
                laser_on_rail_right=False,
                laser_on_tie_left=False,
                laser_on_tie_right=False,
            )
            r1 = send_sensor1(args.base_url, s1_payload)
            if r1.status_code >= 300:
                print(r1.text, file=sys.stderr)
            w1.writerow(flatten_s1(rail_idx + 1, 0, "start", s1_payload))

            s2_payload = gen_sensor2_payload(
                now,
                twisting=False,
                mm_along_rail=0,
                res_cache=res_cache_by_mm,
            )
            r2 = send_sensor2(args.base_url, s2_payload)
            if r2.status_code >= 300:
                print(r2.text, file=sys.stderr)
            w2.writerow(flatten_s2(rail_idx + 1, 0, "start", False, s2_payload))
            now = now + timedelta(seconds=args.interval)
            time.sleep(args.interval)

        for nut_idx in range(args.nuts_per_rail):
            # Twist phase: mm doesn't grow, torques/frequencies > 0
            for t_idx in range(args.twist_ticks):
                s1_payload = gen_sensor1_payload(
                    now,
                    mm,
                    s1_cache_by_mm,
                    sensor_id=1,
                    laser_on_rail_left=True,
                    laser_on_rail_right=True,
                    laser_on_tie_left=False,
                    laser_on_tie_right=False,
                )
                r1 = send_sensor1(args.base_url, s1_payload)
                if r1.status_code >= 300:
                    print(r1.text, file=sys.stderr)
                w1.writerow(flatten_s1(rail_idx + 1, nut_idx + 1, "twist", s1_payload))

                s2_payload = gen_sensor2_payload(
                    now,
                    twisting=True,
                    mm_along_rail=mm,
                    res_cache=res_cache_by_mm,
                    twist_idx=t_idx,
                    twist_total=args.twist_ticks,
                    torque_peak_cache=torque_peak_by_mm,
                )
                r2 = send_sensor2(args.base_url, s2_payload)
                if r2.status_code >= 300:
                    print(r2.text, file=sys.stderr)
                w2.writerow(flatten_s2(rail_idx + 1, nut_idx + 1, "twist", True, s2_payload))
                now = now + timedelta(seconds=args.interval)
                time.sleep(args.interval)
            # Move phase: mm grows, torques zero
            for _ in range(args.move_ticks):
                s1_payload = gen_sensor1_payload(
                    now,
                    mm,
                    s1_cache_by_mm,
                    sensor_id=1,
                    laser_on_rail_left=True,
                    laser_on_rail_right=True,
                    laser_on_tie_left=False,
                    laser_on_tie_right=False,
                )
                r1 = send_sensor1(args.base_url, s1_payload)
                if r1.status_code >= 300:
                    print(r1.text, file=sys.stderr)
                w1.writerow(flatten_s1(rail_idx + 1, nut_idx + 1, "move", s1_payload))

                s2_payload = gen_sensor2_payload(
                    now,
                    twisting=False,
                    mm_along_rail=mm,
                    res_cache=res_cache_by_mm,
                )
                r2 = send_sensor2(args.base_url, s2_payload)
                if r2.status_code >= 300:
                    print(r2.text, file=sys.stderr)
                w2.writerow(flatten_s2(rail_idx + 1, nut_idx + 1, "move", False, s2_payload))
                mm += args.step_mm
                now = now + timedelta(seconds=args.interval)
                time.sleep(args.interval)

        # Closing idle ticks (zeros) to ensure active rails get closed
        for _ in range(args.closing_ticks):
            # To trigger rail close on backend, mmAlongRail must be zero during idle
            s1_payload = gen_sensor1_payload(
                now,
                0,
                s1_cache_by_mm,
                sensor_id=1,
                laser_on_rail_left=False,
                laser_on_rail_right=False,
                laser_on_tie_left=False,
                laser_on_tie_right=False,
            )
            r1 = send_sensor1(args.base_url, s1_payload)
            if r1.status_code >= 300:
                print(r1.text, file=sys.stderr)
            w1.writerow(flatten_s1(rail_idx + 1, args.nuts_per_rail, "close", s1_payload))

            s2_payload = gen_sensor2_payload(
                now,
                twisting=False,
                mm_along_rail=0,
                res_cache=res_cache_by_mm,
            )
            r2 = send_sensor2(args.base_url, s2_payload)
            if r2.status_code >= 300:
                print(r2.text, file=sys.stderr)
            w2.writerow(flatten_s2(rail_idx + 1, args.nuts_per_rail, "close", False, s2_payload))
            now = now + timedelta(seconds=args.interval)
            time.sleep(args.interval)

    f1.close()
    f2.close()


if __name__ == "__main__":
    main()


