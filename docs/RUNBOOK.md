# RUNBOOK — деплой, диагностика, инциденты

> Операционка. Поведение системы — [SPEC.md](../SPEC.md). ENV-тайминги — `tochnost/src/rshr_core/config.py` + `.env.example`.

## 1. Деплой на прод

```bash
# Backend (tochnost, ветка dev): app:8000, postgres:5432, redis:6379
cd tochnost && git pull origin dev && docker compose up -d --build

# Frontend (rzd, ветка main): nginx:3003
cd rzd && git pull origin main && docker compose build --no-cache && docker compose up -d
```

**Автозапуск после перезагрузки:**
```bash
docker update --restart unless-stopped tochnost_postgres tochnost_redis tochnost_app
```

**Live-сбор Modbus** (Windows/Linux на объекте): `test toch/modbus_read_test.py` читает Modbus TCP `10.10.1.2:502` и шлёт на API. На проде — systemd unit `modbus-read.service` (symlink без пробела: `/home/to4nost/modbus` → `test toch`).

### ⚠️ NTP — обязателен

На РШР-сканере **и** ПЛК Modbus обязателен NTP. Иначе дрейф часов → рассинхрон Sensor1 vs Modbus (на объекте наблюдалось ~11 с) и ложные stale. Per-stream watermark (INV-4) дрейф-инвариантен, но расхождение времён всё равно портит хронологию `merged_queue`.

## 2. Конфигурация (ENV)

### Backend `tochnost/.env` — тайминги FSM (критично)

| ENV | Дефолт | Смысл |
|-----|--------|-------|
| `LASER_CONFIRM_ADVANCE_MM` | 200 | Подтверждение открытия РШР движением (рука под лазером) |
| `POST1_MIN_LASER_OFF_SEC` | 1.5 | Мин. OFF лазера пост1 для «новой РШР» (отсечь мигание) |
| `POST1_MAX_PASS_SEC` | 2400 | Макс. проезд поста 1 |
| `POST2_MIN_SEGMENT_SEC` | 3 | Мин. сегмент пост2 (ложный depart) |
| `POST2_DEPART_SETTLE_SEC` | 15 | Досчитать «хвост» закрутки после OFF |
| `POST2_DEPART_GRACE_SEC` | 120 | Фолбэк ухода, если чистого OFF не было |
| `MIN_INTER_CYCLE_SEC` | 7 | Пауза между циклами (двойные циклы) |
| `CYCLE_END_ZERO_PACKETS` | 2 | Нулевых пакетов = конец цикла |
| `MIN_SLEEPER_SPACING_MM` | 250 | Порог «та же шпала» |
| `REORDER_BUFFER_MS` | 500 | Буфер слияния S1+S2 |
| `MAX_LATE_PACKET_SEC` | 300 | Порог опоздавшего пакета |
| `LATE_APPEND_GRACE_SEC` | 180 | Дозапись опоздавших |
| `DROP_STALE_BY_RECEIVED_AT` | false | НЕ дропать по возрасту (дрейф ПЛК) |
| `TAIL_GRACE_SEC` | 120 | Хвост при закрытии |
| `MAX_RAIL_OPEN_SEC` | 3600 | Макс. время открытой РШР |
| `SCREWS_COUNT_MIN_OK` / `MAX_OK` | 160 / 220 | OK-диапазон гаек |
| `STREAM_MONITOR_MAX_EVENTS` | 5000 | Сырой firehose |
| `STREAM_MONITOR_MAX_PIPELINE_EVENTS` | 20000 | Durable-буфер только pipeline |
| `STREAM_MONITOR_REJECT_WINDOW_SEC` | 10 | Окно дедупа отклонённых (422) по сигнатуре |
| `STREAM_MONITOR_REJECT_BODY_LIMIT` | 4096 | Обрезка сырого тела отклонённого запроса |
| `STREAM_MONITOR_REJECT_MAX_SIGNATURES` | 200 | Потолок словаря сигнатур отклонений |

Плюс: `POSTGRES_*`, `REDIS_*`, `SECRET_KEY`, `JWT_SECRET_KEY`, `PUBLIC_URL`, камера `HIKVISION_*` / `CAMERA_*`, `TELEGRAM_*`. Полный список — `.env.example`.

### Frontend `rzd`

```env
VITE_API_BASE_URL=     # на проде ПУСТО: браузер → nginx :3003/api
```
**Не** ставить `host.docker.internal` — это адрес Docker-сборки, не браузера оператора. → [ADR-0009](adr/0009-frontend-api-base-url.md)

## 3. Диагностика за 5 минут

```bash
# 1. FSM жив? Снимок состояния конвейера
curl -s localhost:8000/api/v1/sensor/debug/state | python3 -m json.tool | head -50

# 2. Пакеты приходят? Счётчики потока
curl -s localhost:8000/api/v1/stream-monitor/stats | python3 -m json.tool

# 3. Реплей на тестовых данных (эталон: rails_opened=13, screws≈1164)
cd "test toch" && python simulate_capture.py \
  --rshr "../test data/rshr_data.jsonl" --modbus "../test data/modbus_data.jsonl"
```

Stream Monitor UI: `http://localhost:3003/monitor` (без логина). Здоровая цепочка:
`rshr_opened → post2_recognized → tightening_started → tightening_completed → rshr_departed_post2 → rshr_closed`.

## 4. Разбор инцидента

1. **Собрать данные:** `bash tochnost/scripts/collect_incident.sh` или экспорт из монитора:
   ```bash
   curl "http://localhost:8000/api/v1/stream-monitor/export?mode=incident" -o incident.jsonl
   ```
2. **Прогнать реплей настоящего FSM** по логам:
   ```bash
   cd tochnost && uv run --python 3.12 --with pydantic python scripts/replay_logs.py \
     --rshr … --modbus …
   # Проверять: нет зависших IN_PROGRESS, «ПОТЕРЯНО всплесков» = 0
   ```
3. **Смотреть:** был ли `park` vs ошибочный `close`; `modbus_skipped` при активной закрутке; `packet_stale` на Sensor1; пустой FIFO при лазере поста 2.

## 5. Типовые инциденты → см. FAQ онбординга

Полный FAQ с коммитами — [AI_ONBOARDING.md §15](AI_ONBOARDING.md). Кратко:

| Симптом | Вероятная причина | Куда смотреть |
|---------|-------------------|---------------|
| Число шпал 0 / ~20 (колонка «Эпюра») | `close` на посту 1 вместо `park` | INV-1, ADR-0001 |
| ~70 гаек на чужой РШР | гайки на `active`, не `rail_at_post2` | INV-2, ADR-0002 |
| Фантомные короткие РШР (782 мм) | открытие без подтверждения движением | INV-6, ADR-0007 |
| `packet_stale` глушит Sensor1 | общий watermark вместо per-stream | INV-4, ADR-0004 |
| Двойные циклы на шпалу | нет паузы `MIN_INTER_CYCLE_SEC` | INV-5, ADR-0005 |
| Дашборд пуст, но T/H есть | 422 на `/sensor/first` (не все поля) | логи uvicorn, `debug/state` |
| РШР «уехала в молоко» | `active` не снята при РШР на посту 2 | ADR-0007 |
| Много `modbus_skipped` при закрутке | `rail_at_post2 is None`, FIFO не наполнился | цепочка `rshr_opened`→`post2_recognized` |

## 6. Сброс FSM (осторожно)

```bash
curl -X POST localhost:8000/api/v1/sensor/state/reset -H 'Content-Type: application/json' -d '{"confirm": true}'
```
Стирает in-memory состояние конвейера. Использовать только при заведомо битом состоянии; активная РШР потеряется.
