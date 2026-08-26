#!/usr/bin/env python3
"""Добавляет в капчу Sensor1 поля забега — проверка нового пути без объекта.

Старые капчи сняты прошивкой сборщика до 08.2026, полей mmRailStart*/mmRailEnd*
в них нет. Скрипт подмешивает их, чтобы прогнать реплей по новому пути.

    python3 scripts/inject_rail_edges.py in.jsonl out.jsonl
    python3 scripts/inject_rail_edges.py in.jsonl out.jsonl --start 80 --end -8
    python3 scripts/inject_rail_edges.py in.jsonl out.jsonl --stage-after-mm 12000

--stage-after-mm: до этого mmAlongRail поля End остаются нулями (как у реальной
прошивки, которая заполняет End только после прохода торца). Проверяет правило
«берём последний пакет прохода».
"""

from __future__ import annotations

import argparse
import json


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--start", type=int, default=12, help="забег в начале, мм (Л − П)")
    ap.add_argument("--end", type=int, default=-8, help="забег в конце, мм (Л − П)")
    ap.add_argument("--start-base", type=int, default=100, help="позиция правого торца начала, мм")
    ap.add_argument("--end-base", type=int, default=24000, help="позиция правого торца конца, мм")
    ap.add_argument(
        "--stage-after-mm",
        type=int,
        default=0,
        help="до этого mmAlongRail поля End = 0 (0 = заполнять всегда)",
    )
    args = ap.parse_args()

    written = skipped = 0
    with open(args.src, encoding="utf-8") as fin, open(args.dst, "w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            try:
                packet = json.loads(line)
            except json.JSONDecodeError:
                # В капчах встречаются порванные строки — переносим как есть,
                # чтобы реплей видел ровно тот же мусор, что и без инжекта.
                fout.write(line + "\n")
                skipped += 1
                continue
            values = packet.get("values")
            if isinstance(values, dict):
                mm = int(values.get("mmAlongRail", 0) or 0)
                values["mmRailStartRight"] = args.start_base
                values["mmRailStartLeft"] = args.start_base + args.start
                if mm >= args.stage_after_mm:
                    values["mmRailEndRight"] = args.end_base
                    values["mmRailEndLeft"] = args.end_base + args.end
                else:
                    values["mmRailEndRight"] = 0
                    values["mmRailEndLeft"] = 0
            fout.write(json.dumps(packet, ensure_ascii=False) + "\n")
            written += 1
    print(f"{written} пакетов записано в {args.dst} (порванных строк перенесено без правки: {skipped})")


if __name__ == "__main__":
    main()
