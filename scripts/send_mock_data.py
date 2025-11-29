#!/usr/bin/env python3
import argparse
import random
import sys
import time
from datetime import datetime

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


def gen_sensor2_payload(now: datetime, zeros: bool) -> dict:
    def v(val: int) -> int:
        return 0 if zeros else val

    return {
        "timestamp": fmt_ts(now),
        "values": {
            "resistance_1": 0.0 if zeros else round(random.uniform(0.0, 4.0), 2),
            "resistance_2": 0.0 if zeros else round(random.uniform(0.0, 4.0), 2),
            "moment_pc": v(random.randint(0, 1000)),
            "moment_percent": v(random.randint(0, 100)),
            "moment_amperage_percent": v(random.randint(0, 100)),
            "turnover": v(random.randint(0, 5000)),
            "amperage": v(random.randint(0, 500)),
            "phase_amperage": v(random.randint(0, 500)),
            "revolutions_pc_alt": v(random.randint(0, 5000)),
            "status_pc": v(random.randint(0, 10)),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Send mock sensor data to API")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Base URL, e.g. http://localhost:8000")
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between ticks")
    parser.add_argument("--step-mm", type=int, default=1, help="mmAlongRail increment per tick")
    parser.add_argument("--rails", type=int, default=3, help="How many rails to simulate")
    parser.add_argument("--ticks-per-rail", type=int, default=20, help="Ticks per rail (length in ticks)")
    parser.add_argument("--gap-seconds", type=float, default=3.0, help="Idle gap between rails in seconds")
    args = parser.parse_args()

    from datetime import timedelta
    now = datetime.now()
    mm = 0

    for rail_idx in range(args.rails):

        # Тики рельса: растём по mmAlongRail
        for _ in range(args.ticks_per_rail):
            s1 = gen_sensor1_payload(now, mm)
            r1 = send_sensor1(args.base_url, s1)
            print(f"[{fmt_ts(now)}] rail#{rail_idx+1} S1 -> {r1.status_code}")
            if r1.status_code >= 300:
                print(r1.text, file=sys.stderr)

            mm += args.step_mm
            s2 = gen_sensor2_payload(now, zeros=False)
            r2 = send_sensor2(args.base_url, s2)
            print(f"[{fmt_ts(now)}] rail#{rail_idx+1} S2 -> {r2.status_code}")
            if r2.status_code >= 300:
                print(r2.text, file=sys.stderr)

            now = now + timedelta(seconds=args.interval)
            time.sleep(args.interval)

        # Промежуток между рельсами (если не последний)
        if rail_idx < args.rails - 1:
            gap_ticks = max(1, int(round(args.gap_seconds / args.interval)))
            for _ in range(gap_ticks):
                # Sensor1 без роста мм
                s1_idle = gen_sensor1_payload(now, mm)
                r1i = send_sensor1(args.base_url, s1_idle)
                print(f"[{fmt_ts(now)}] gap S1 -> {r1i.status_code}")
                if r1i.status_code >= 300:
                    print(r1i.text, file=sys.stderr)

                # Sensor2 нули в режиме простоя
                s2_idle = gen_sensor2_payload(now, zeros=True)
                r2i = send_sensor2(args.base_url, s2_idle)
                print(f"[{fmt_ts(now)}] gap S2 -> {r2i.status_code}")
                if r2i.status_code >= 300:
                    print(r2i.text, file=sys.stderr)

                now = now + timedelta(seconds=args.interval)
                time.sleep(args.interval)


if __name__ == "__main__":
    main()


