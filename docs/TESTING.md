# TESTING — реплей, валидация, приёмка

> Как проверять FSM без объекта. Критерии приёмки — [SPEC.md §10](../SPEC.md). Инструменты — `test toch/` и `tochnost/scripts/`.

## 1. Главный тест: офлайн-реплей FSM

Один и тот же код циклов (`rshr_core`) гоняется онлайн и офлайн → поведение воспроизводимо на записанных данных.

```bash
python "test toch/simulate_capture.py" --dir "test data/19-05-2026"
```

> ⚠️ У скрипта **нет** флагов `--rshr` / `--modbus`. Он принимает `--dir` и сам берёт
> оттуда `modbus_2026-05-19.jsonl` + `rshr_data.jsonl`. Пути `--dir` — относительно
> текущей папки, поэтому запускать из корня `RZD APPS/`. Флаги `--rshr` / `--modbus`
> есть у другого скрипта — `tochnost/scripts/replay_logs.py` (раздел 2).

Симулятор воспроизводит: открытие/парковку/закрытие РШР, FIFO поста 2, циклы закрутки (те же правила, что `rshr_core`), и печатает счётчики: `rails_opened`, `screws_created`, `post2_unmatched_segments`.

### Эталон для данных 19.05.2026

| Метрика | Значение | Комментарий |
|---------|----------|-------------|
| `rails_opened` | **13** | не 17 — 4 коротких артефакта от mm=0 отброшены |
| `screws_created` | **≈ 1164** | гайки |
| Сенсоры | считать **раздельно** | S1 и S2 не смешивать |

Отклонение от эталона после правки FSM = **регресс**. Разобраться до коммита.

## 2. Реплей «настоящего» FSM по логам (для инцидентов)

`simulate_capture.py` — упрощённая модель. Для точной проверки прогоняют реальный сервисный код:

```bash
cd tochnost
uv run --python 3.12 --with pydantic python scripts/replay_logs.py \
  --rshr   … \
  --modbus …
```

Проверять на выходе:
- **нет зависших `IN_PROGRESS`** (кроме одной легитимной парковки между сменами);
- **«ПОТЕРЯНО всплесков» = 0** — циклы закрутки не теряются;
- число шпал и длина в норме (~50 шпал, ~25 м).

Также: `tochnost/scripts/verify_rshr_replay.py` — реплей по pipeline-логам.

## 3. Валидация формата и подсчёт РШР

```bash
cd "test toch"
python run_validation.py            # проверка формата JSONL
python match_rshr_report.py         # сопоставление S1/S2, подсчёт реальных проездов
```

Правило подсчёта: реальный проезд = размах `mmAlongRail` ≥ 8 м и > 500 точек. Лазерные сегменты ≠ число РШР (часть — мусор при mm=0).

## 4. Синтетические данные и живой сбор

| Инструмент | Путь | Назначение |
|------------|------|------------|
| `send_mock_data.py` | `tochnost/scripts/` | синтетические пакеты → API |
| `modbus_read_test.py` | `test toch/` | живой Modbus TCP → API |
| `test_camera.py` / `test_rtsp.py` | `tochnost/scripts/` | проверка Hikvision |
| `collect_incident.sh` | `tochnost/scripts/` | bundle при инциденте |

## 5. Конфиги реплея (`RshrTimingConfig`)

| Пресет | Отличия | Когда |
|--------|---------|-------|
| `from_env()` | ENV-дефолты (прод) | обычный runtime |
| `capture_faithful()` | `reorder_buffer_ms=0`, `cycle_end_zero_packets=1`, `max_late_packet_sec=inf` | офлайн-реплей упорядоченного JSONL |
| `live_stress()` | `reorder_buffer_ms=500`, `cycle_end_zero_packets=2` | стресс-джиттер |

Онлайн (2 нулевых пакета) и офлайн (1) настроены так, чтобы **сходиться** на реальных данных.

## 6. Чек-лист приёмки перед коммитом FSM/закрутки

- [ ] Офлайн-реплей на `test data/` даёт `rails_opened=13`, `screws≈1164`.
- [ ] `replay_logs.py` не показывает зависших `IN_PROGRESS` и потерь всплесков.
- [ ] Не нарушены инварианты INV-1…INV-8 ([SPEC §6](../SPEC.md)).
- [ ] Если менялось поведение — обновлены SPEC (FR/INV/пороги) и нужный ADR.
- [ ] Backend поднимается: `curl .../sensor/debug/state` отвечает.

## 7. Frontend

```bash
cd rzd
pnpm typecheck      # tsc -b
pnpm lint           # eslint
pnpm build          # vite build (проверка сборки)
```
Дымовой тест: дашборд `/` показывает T/H и стадии; `/monitor` — цепочку событий; таблица `/list` — число шпал «—» для `IN_PROGRESS`.
