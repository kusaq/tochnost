---
name: Fix post2 length corruption
overview: Перестать приписывать эпюру/данные поста 2 нераспознанной РШР чужой РШР, стоящей на посту 1, чтобы её длина (max mmAlongRail) не затиралась.
todos:
  - id: fix-routing
    content: В process_second_sensor1_data привязывать эпюру поста 2 только к rail_at_post2 (или is_in_closed), убрать fallback на fifo[0]/active
    status: pending
  - id: verify-replay
    content: Прогнать verify_rshr_replay.py и проверить, что длины РШР не включают чужой пост 2
    status: pending
  - id: deploy-verify
    content: "Задеплоить и проверить на объекте: длина РШР на посту 1 корректная"
    status: pending
isProject: false
---

# Фикс: длина РШР с поста 1 затирается данными РШР с поста 2

## Причина (подтверждена)

РШР B проехала пост 1, пока бек был выключен -> она не открыта и не попала в `fifo_rail_ids`. После запуска открылась РШР A на посту 1 (`fifo_rail_ids = [A]`). РШР B физически на посту 2 и шлёт Sensor1 `sensor_id=2` (эпюра поста 2) со своим `mmAlongRail` до ~25000.

В [tochnost/src/api/v1/sensor/service.py](tochnost/src/api/v1/sensor/service.py) `process_second_sensor1_data` (строки 665-672) определяет рельсу так:

```python
rail_id = self._modbus_target_rail_id(for_modbus=False)
if rail_id is None:
    rail_id = self.state.is_in_closed(data.timestamp)
if rail_id is not None:
    await self.uow.sensor1.add(Sensor1(rail_id=rail_id, timestamp=..., **values.model_dump()))
```

`_modbus_target_rail_id(for_modbus=False)` (строки 279-289) при `rail_at_post2 is None` возвращает `fifo_rail_ids[0]` (или active) = РШР A. В итоге строки Sensor1 РШР B пишутся в РШР A, и карточка A («Длина рельсы» = max `mmAlongRail` по Sensor1) показывает длину B.

## Исправление (локальное, бек)

В `process_second_sensor1_data` привязывать эпюру поста 2 ТОЛЬКО к РШР, реально стоящей на посту 2 (`rail_at_post2`), иначе к недавно закрытой по времени (`is_in_closed`), иначе не писать. Убрать fallback на `fifo[0]`/active для записи поста 2:

```python
# Эпюра поста 2 принадлежит РШР, реально стоящей на посту 2.
# fifo[0]/active может быть РШР, ещё стоящей на посту 1 (если у предыдущей
# РШР пост 1 был пропущен), и тогда её длина затирается чужими mmAlongRail.
rail_id = self.state.post2_tracker().rail_at_post2
if rail_id is None:
    rail_id = self.state.is_in_closed(data.timestamp)
if rail_id is not None:
    await self.uow.sensor1.add(Sensor1(rail_id=rail_id, timestamp=data.timestamp, **values.model_dump()))
```

Почему безопасно для нормального потока: при штатном проходе пост 1 -> пост 2 распознавание выставляет `rail_at_post2`, и эпюра привязывается верно. Теряются только ранние пакеты поста 2 до распознавания (доли секунды) — это приемлемо.

Канал modbus-закрутки (`add_sensor2_data`, `for_modbus=True`) уже не имеет fallback и корректно отдаёт `modbus_skipped` — не трогаем.

## Важное ограничение

Этот фикс ОСТАНАВЛИВАЕТ порчу длины хорошей РШР A. Данные самой РШР B (которая прошла пост 1 при выключенном беке) по-прежнему НЕ сохранятся — для их захвата нужна отдельная доработка «осиротевшая РШР на посту 2» (создание рельса по активности modbus/лазеру), которую ранее отложили. Если нужно — сделаю отдельным шагом.

## Сопутствующий риск (вне scope, только отметить)

Если у нераспознанной РШР на посту 2 всё же сработает фронт лазера при непустом `fifo` (где лежит РШР с поста 1), `on_post2_segment_start()` ([state.py](tochnost/src/api/v1/sensor/state.py):40-51) ошибочно «распознает» РШР с поста 1 как ушедшую на пост 2. В текущем инциденте это не сработало (`rail_at_post2` оставался None), но это слабое место FIFO при пропуске поста 1. Решать отдельно при необходимости.

## Проверка

- Прогнать `scripts/verify_rshr_replay.py` на сырых данных (паритет FSM) — длины открытых РШР не должны включать чужой пост 2.
- На объекте: в карточке РШР, открытой на посту 1, «Длина рельсы» = её реальная (например 16430 мм), а не длина РШР с поста 2.
- `GET /api/v1/sensor/debug/state` — убедиться, что в Sensor1 рельсы A не подмешиваются большие `mmAlongRail` от B.