# AGENTS.md — tochnost (backend РЖД)

> Точка входа для ИИ-агента в backend-репозитории. Для Claude Code эквивалент — [CLAUDE.md](CLAUDE.md). Источник правды по поведению — [SPEC.md](SPEC.md).

## О репозитории
Backend системы мониторинга сборки **рельсошпальных решёток (РШР)** на заводе РЖД. FastAPI (Python 3.12, `uv`), ветка `dev`, порт 8000. Принимает два контура датчиков (Sensor1 — геометрия/лазеры; Sensor2 — Modbus M1–M4/R/T/H), ведёт FSM конвейера, пишет в TimescaleDB, публикует live в Redis. Фронтенд — отдельный репо `rzd`.

## Прежде чем писать код
1. [SPEC.md](SPEC.md) — FR, **инварианты INV-1…8**, контракты, критерии приёмки.
2. [docs/adr/](docs/adr/) — почему инвариант такой (не «упрощать»).
3. [docs/AI_ONBOARDING.md](docs/AI_ONBOARDING.md) — контекст + FAQ по инцидентам.

## Сердце логики — FSM
- `src/api/v1/sensor/service.py` — поведение FSM конвейера РШР.
- `src/api/v1/sensor/state.py` — `SensorState` / `SENSOR_STATE` (in-memory истина).
- `src/rshr_core/` — общая логика: `tightening.py` (циклы, 4 гайки/цикл, `detect_cycles_in_window`), `config.py` (`RshrTimingConfig` — все ENV-тайминги), `late_packets.py` (per-stream watermark).
- `src/infra/timescale_db/` — модели `Rail`/`Screw`/`Sensor1`/`Sensor2`/`Error`.
- FSM **не** в `rail/fsm.py` (там только отвязка при удалении).

## Золотые правила
1. Пост 1 — только `park_active_for_post2()`, никогда `close_active_rail`. Финализация — только на посту 2. → INV-1
2. Гайки — только на `rail_at_post2` (`_modbus_target_rail_id`), не на `get_active_rail()`. → INV-2
3. Число шпал = `ceil(гайки/4)` при finalize; для `IN_PROGRESS` UI — «—». → INV-3
4. Per-stream watermark (`s1:1`, `s1:2`, `s2`), не общий. → INV-4
5. Старт цикла — M1–M4 + пауза `MIN_INTER_CYCLE_SEC=7`; конец — `CYCLE_END_ZERO_PACKETS=2`. → INV-5
6. Открытие РШР — подтверждение движением `LASER_CONFIRM_ADVANCE_MM=200`; новая РШР по сбросу mm ≥ 3000. → INV-6
7. Тайминги/пороги — только через `RshrTimingConfig` (ENV), не хардкодить в `service.py`.

## Терминология
**Число шпал** (`sleepers`) — то, что считает система. **Эпюра** — расстояние между шпалами, ⚠️ не количество (UI-колонка «Эпюра» = число шпал, историческое имя).

## Проверка изменений
```bash
docker compose up -d --build                                   # app:8000, postgres, redis
curl -s localhost:8000/api/v1/sensor/debug/state | python3 -m json.tool | head -50
# офлайн-реплей (эталон: rails_opened=13, screws≈1164):
cd "../test toch" && python simulate_capture.py --rshr "../test data/rshr_data.jsonl" --modbus "../test data/modbus_data.jsonl"
# настоящий FSM по логам (инцидент): нет зависших IN_PROGRESS, «ПОТЕРЯНО всплесков»=0
uv run --python 3.12 --with pydantic python scripts/replay_logs.py --rshr … --modbus …
```
Менял поведение → обнови [SPEC.md](SPEC.md) и ADR, прогони эталон. Коммитить только по просьбе; не коммить `.env`. Подробнее — [docs/CONVENTIONS.md](docs/CONVENTIONS.md), [docs/TESTING.md](docs/TESTING.md).
