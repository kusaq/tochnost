---
name: Deploy watermark fix
overview: Задеплоить уже запушенный фикс per-stream watermark (коммит 8862625) на объекте и проверить, что РШР снова открываются и закрутка пишется. Кода не меняем.
todos: []
isProject: false
---

# Деплой и проверка per-stream watermark фикса

## Контекст (без изменений кода)

Открытие РШР зависит только от Sensor1 на посту 1. Часы Sensor2/modbus (на ~11.6 сек впереди) ломали открытие только через общий watermark в объединённой очереди. Это уже исправлено коммитом `8862625` (раздельный watermark `s1:1`, `s1:2`, `s2`) в [src/api/v1/sensor/state.py](tochnost/src/api/v1/sensor/state.py) и [src/api/v1/sensor/service.py](tochnost/src/api/v1/sensor/service.py). Синхронизация Sensor2 для открытия РШР не требуется.

Доказательство достаточности: прогон сырого `rshr_data.jsonl` через FSM открывает 3 РШР; per-stream классификация даёт `NORMAL` вместо `STALE`.

## Шаги деплоя (на объекте, по AnyDesk)

Сервис поднят через docker-compose ([docker-compose.yml](tochnost/docker-compose.yml), контейнер `tochnost_app`, `pull_policy: build`).

- Забрать фикс на ветке `dev`:
  - `cd <путь>/tochnost && git fetch origin && git checkout dev && git pull --ff-only`
  - убедиться, что HEAD = `8862625` (`git log -1 --oneline`)
- Пересобрать и перезапустить только app:
  - `docker compose up -d --build app`
- Сбросить in-memory FSM (чтобы убрать «залипший» watermark и пустой post2 FIFO):
  - `curl -fsS -X POST http://127.0.0.1:8000/api/v1/sensor/state/reset -H 'Content-Type: application/json' -d '{"confirm": true}'`

## Проверка результата

- Снимок FSM: `curl -fsS http://127.0.0.1:8000/api/v1/sensor/debug/state`
  - в `watermarks` должны появиться раздельные ключи (`s1:1`, `s1:2`, `s2`) с разным временем;
  - `packet_counters.packets_stale` не должен лавинообразно расти;
  - при проходе рельса появляется `active_rail` (не null).
- Статистика монитора: `curl -fsS http://127.0.0.1:8000/api/v1/stream-monitor/stats`
  - в `by_event_type` должен появиться `rshr_opened` (и далее `rshr_closed`), а доля `modbus_skipped` упасть.
- Признак успеха: при заходе рельса на пост 1 в мониторе сразу `rshr_opened`, при закрутке — `tightening_started/completed`, при уходе с поста 2 — `rshr_departed_post2` + `rshr_closed`.

## Если проблема осталась

- Собрать инцидент: [scripts/collect_incident.sh](tochnost/scripts/collect_incident.sh) `http://127.0.0.1:8000` и прислать `incident_*.zip`.
- В `packet_stale` теперь есть поле `stream_key` — оно сразу покажет, какой именно поток отбрасывается.