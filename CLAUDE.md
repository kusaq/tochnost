# tochnost — backend РЖД (FastAPI)

> Полный контекст проекта: `../docs/AI_ONBOARDING.md`. Планы: `../docs/plans/`.
> Этот репозиторий деплоится из ветки **`dev`** (порт 8000). Фронтенд — отдельный репо `../rzd` (ветка `main`).

## Где что
- `src/server/server.py` — FastAPI app, `lifespan` (запускает worker'ы)
- `src/api/v1/sensor/service.py` — ★ поведение FSM конвейера РШР
- `src/api/v1/sensor/state.py` — `SensorState` / `SENSOR_STATE` (in-memory истина)
- `src/rshr_core/` — общая логика закрутки/таймингов/длины (используется и в offline-симуляторе)
  - `tightening.py` — детекция циклов (4 гайки/цикл), `detect_cycles_in_window`
  - `config.py` — `RshrTimingConfig` (все ENV-тайминги)
- `src/infra/timescale_db/` — модели, storage, миграции (Rail, Screw, Sensor1/2, Error)
- `scripts/` — `verify_rshr_replay.py`, `send_mock_data.py`, `test_camera.py`, `collect_incident.sh`

## Критичные инварианты FSM (подробно — в онбординге, разделы 6–8)
1. Пост 1 — только `park_active_for_post2()`, никогда `close_active_rail`. `finalize_rail` только на посту 2.
2. Гайки — только на `rail_at_post2` (`_modbus_target_rail_id`), не на `get_active_rail()`.
3. Эпюра = `ceil(гайки/4)` при finalize; для `IN_PROGRESS` UI показывает «—».
4. Per-stream watermark (`s1:1`, `s1:2`, `s2`) — не общий.
5. Старт цикла: M1–M4 + пауза `MIN_INTER_CYCLE_SEC=7`; конец: `CYCLE_END_ZERO_PACKETS=2`.
6. Открытие РШР: подтверждение движением `LASER_CONFIRM_ADVANCE_MM=200`.

## Запуск/диагностика
```bash
docker compose up -d --build                                    # app:8000, postgres:5432, redis:6379
curl -s localhost:8000/api/v1/sensor/debug/state | python3 -m json.tool
curl -s localhost:8000/api/v1/stream-monitor/stats | python3 -m json.tool
```
Не коммить `.env` с секретами. ENV-тайминги — в `.env.example` и `rshr_core/config.py`.
