#!/usr/bin/env python3
import argparse
import random
import sys
import time
import csv
from datetime import datetime, timedelta

import requests


def fmt_ts(dt: datetime) -> str:
    # Ожидаемый формат: "YYYY-MM-DD HH:MM:SS"
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def send_sensor1(base_url: str, payload: dict) -> requests.Response:
    url = f"{base_url}/api/v1/sensor/first"
    return requests.post(url, json=payload, timeout=10)


def send_sensor2(base_url: str, payload: dict) -> requests.Response:
    url = f"{base_url}/api/v1/sensor/second"
    return requests.post(url, json=payload, timeout=10)


def gen_sensor1_payload(now: datetime, mm_along_rail: int) -> dict:
    return {
        "timestamp": fmt_ts(now),
        "values": {
            "encoder1": random.randint(1000, 2000),
            "encoder2": random.randint(1000, 2000),
            "encoder3": random.randint(1000, 2000),
            "encoder4": random.randint(1000, 2000),
            "mm_along_rail": mm_along_rail,
            "laser_on_rail_left": random.choice([True, False]),
            "laser_on_rail_right": random.choice([True, False]),
            "laser_on_tie_left": random.choice([True, False]),
            "laser_on_tie_right": random.choice([True, False]),
            "mm_gauge": round(random.uniform(1520.0, 1526.0), 2),
            "mm_side_wear_left": round(random.uniform(0.0, 2.0), 2),
            "mm_side_wear_right": round(random.uniform(0.0, 2.0), 2),
            "mm_vertical_wear_left": round(random.uniform(0.0, 2.0), 2),
            "mm_vertical_wear_right": round(random.uniform(0.0, 2.0), 2),
            "rad_rail_tilt_left": round(random.uniform(0.0, 0.01), 4),
            "rad_rail_tilt_right": round(random.uniform(0.0, 0.01), 4),
            "mm_bolt_height_left_inner": round(random.uniform(0.0, 5.0), 2),
            "mm_bolt_height_left_outer": round(random.uniform(0.0, 5.0), 2),
            "mm_bolt_height_right_inner": round(random.uniform(0.0, 5.0), 2),
            "mm_bolt_height_right_outer": round(random.uniform(0.0, 5.0), 2),
        },
    }


def gen_sensor2_payload(now: datetime, twisting: bool) -> dict:
    def nz(a: int, b: int) -> int:
        return random.randint(a, b)
    on = 1 if twisting else 0
    return {
        "timestamp": fmt_ts(now),
        "values": {
            "R": round(random.uniform(0.0, 100.0), 4),
            "T": round(random.uniform(0.0, 40.0), 4),
            "H": round(random.uniform(0.0, 100.0), 4),
            "ST1": on, "ST2": on, "ST3": on, "ST4": on,
            "M1": nz(10, 1000) if twisting else 0,
            "M2": nz(10, 1000) if twisting else 0,
            "M3": nz(10, 1000) if twisting else 0,
            "M4": nz(10, 1000) if twisting else 0,
            "f1": nz(10, 5000) if twisting else 0,
            "f2": nz(10, 5000) if twisting else 0,
            "f3": nz(10, 5000) if twisting else 0,
            "f4": nz(10, 5000) if twisting else 0,
        },
    }


def flatten_s1(rail: int, nut: int, phase: str, payload: dict) -> dict:
    v = payload["values"]
    return {
        "rail": rail,
        "nut": nut,
        "phase": phase,
        "timestamp": payload["timestamp"],
        "mmAlongRail": v["mm_along_rail"],
        "encoder1": v["encoder1"],
        "encoder2": v["encoder2"],
        "encoder3": v["encoder3"],
        "encoder4": v["encoder4"],
        "laserOnRailLeft": v["laser_on_rail_left"],
        "laserOnRailRight": v["laser_on_rail_right"],
        "laserOnTieLeft": v["laser_on_tie_left"],
        "laserOnTieRight": v["laser_on_tie_right"],
        "mmGauge": v["mm_gauge"],
        "mmSideWearLeft": v["mm_side_wear_left"],
        "mmSideWearRight": v["mm_side_wear_right"],
        "mmVerticalWearLeft": v["mm_vertical_wear_left"],
        "mmVerticalWearRight": v["mm_vertical_wear_right"],
        "radRailTiltLeft": v["rad_rail_tilt_left"],
        "radRailTiltRight": v["rad_rail_tilt_right"],
        "mmBoltHeightLeftInner": v["mm_bolt_height_left_inner"],
        "mmBoltHeightLeftOuter": v["mm_bolt_height_left_outer"],
        "mmBoltHeightRightInner": v["mm_bolt_height_right_inner"],
        "mmBoltHeightRightOuter": v["mm_bolt_height_right_outer"],
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
    parser.add_argument("--base-url", default="http://localhost:8000", help="Base URL, e.g. http://localhost:8000")
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between ticks")
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
        for nut_idx in range(args.nuts_per_rail):
            # Twist phase: mm doesn't grow, torques/frequencies > 0
            for _ in range(args.twist_ticks):
                s1_payload = gen_sensor1_payload(now, mm)
                r1 = send_sensor1(args.base_url, s1_payload)
                if r1.status_code >= 300:
                    print(r1.text, file=sys.stderr)
                w1.writerow(flatten_s1(rail_idx + 1, nut_idx + 1, "twist", s1_payload))

                s2_payload = gen_sensor2_payload(now, twisting=True)
                r2 = send_sensor2(args.base_url, s2_payload)
                if r2.status_code >= 300:
                    print(r2.text, file=sys.stderr)
                w2.writerow(flatten_s2(rail_idx + 1, nut_idx + 1, "twist", True, s2_payload))
                now = now + timedelta(seconds=args.interval)
                time.sleep(args.interval)
            # Move phase: mm grows, torques zero
            for _ in range(args.move_ticks):
                s1_payload = gen_sensor1_payload(now, mm)
                r1 = send_sensor1(args.base_url, s1_payload)
                if r1.status_code >= 300:
                    print(r1.text, file=sys.stderr)
                w1.writerow(flatten_s1(rail_idx + 1, nut_idx + 1, "move", s1_payload))

                s2_payload = gen_sensor2_payload(now, twisting=False)
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
            s1_payload = gen_sensor1_payload(now, 0)
            r1 = send_sensor1(args.base_url, s1_payload)
            if r1.status_code >= 300:
                print(r1.text, file=sys.stderr)
            w1.writerow(flatten_s1(rail_idx + 1, args.nuts_per_rail, "close", s1_payload))

            s2_payload = gen_sensor2_payload(now, twisting=False)
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


