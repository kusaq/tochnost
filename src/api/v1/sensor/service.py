from datetime import datetime, timedelta, timezone
import heapq
import logging
import math
import json
import asyncio
import itertools

from fastapi import HTTPException
from starlette import status

from api.v1.sensor.schemas import ThresholdEntry, Thresholds, RailSession, Screw as ScrewDC
from api.v1.base.service import BaseService
from api.v1.sensor.schemas import Sensor1Create, Sensor2Create
from api.v1.sensor.state import SensorState, MergedSensorEvent
from infra.timescale_db.models import Rail, Sensor1, Sensor2, Screw, RailStatus, ScrewStatus, Error, RailSide
from infra.timescale_db.ts_db import get_unscoped_db
from infra.redis.redis_api import RedisAPI
from infra.timescale_db.uow import TimeScaleDBUnitOfWork
from api.v1.sensor.state import SENSOR_STATE
from api.v1.sensor.tightening import has_moment_activity, all_torque_zero, MOMENT_KEYS, FREQ_KEYS
from rshr_core.config import RshrTimingConfig
from rshr_core.rshr_length import segment_length_mm
from rshr_core.late_packets import classify_late_packet, LatePacketPolicy
from api.v1.stream_monitor.pipeline_hooks import emit_pipeline_event
from api.v1.rail.fsm import detach_rail_from_sensor_state
from api.v1.ws.service import cache_dashboard_env_stats
from infra.telegram.rail_burst import schedule_rail_departure_burst

logger = logging.getLogger(__name__)
TIMING_CONFIG = RshrTimingConfig.from_env()
_event_counter = itertools.count()


def _event_watermark_key(ev: MergedSensorEvent) -> str:
    if ev.kind == "s1":
        sensor_id = getattr(ev.payload, "sensor_id", "unknown")
        return f"s1:{sensor_id}"
    return ev.kind


class SensorService(BaseService):
    state: SensorState

    THRESHOLDS_CACHE_KEY = "thresholds:all"

    # Длина РШР по mmAlongRail (пост 1): норма ~25 м, допуск от 20 м, < 15 м — отброс
    RSHR_LENGTH_MIN_OK_MM = 20_000
    RSHR_LENGTH_DISCARD_BELOW_MM = 15_000

    # Сброс mmAlongRail к началу = граница новой РШР на посту 1.
    # Новый рельс всегда начинает отсчёт с ~0, поэтому резкое падение mmAlongRail
    # относительно активной сессии означает, что приехал следующий рельс.
    NEW_RAIL_MM_RESET_DROP_MM = 3_000

    # mmAlongRail «около нуля»: энкодер сбросился на границе рельса (последний пакет
    # ухода: laser=false, mm≈0). Отличает реальный уход от мигания лазера в середине
    # прохода (там mm высокий и не сбрасывается).
    MM_RESET_NEAR_ZERO = 1_000

    # Человекочитаемые имена метрик
    METRIC_DISPLAY: dict[str, str] = {
        "resistance": "Сопротивление между рельсами",
        "mm_gauge": "Ширина колеи",
        "mm_side_wear_left": "Боковой износ левого рельса",
        "mm_side_wear_right": "Боковой износ правого рельса",
        "mm_vertical_wear_left": "Вертикальный износ левого рельса",
        "mm_vertical_wear_right": "Вертикальный износ правого рельса",
        "rad_rail_tilt_left": "Наклон левого рельса",
        "rad_rail_tilt_right": "Наклон правого рельса",
    }

    # Метрики Sensor1 для отслеживания диапазонов
    S1_RANGE_KEYS: tuple[str, ...] = (
        "mm_gauge",
        "mm_side_wear_left",
        "mm_side_wear_right",
        "mm_vertical_wear_left",
        "mm_vertical_wear_right",
        "rad_rail_tilt_left",
        "rad_rail_tilt_right",
    )

    async def get_threshold(self, key: str) -> ThresholdEntry | None:
        cache_key = f"threshold:{key}"
        cached = await self.redis.get(cache_key)
        if cached:
            return ThresholdEntry.model_validate_json(cached)
        item = await self.uow.threshold.get_by_value(key)
        if not item:
            return None
        entry = ThresholdEntry(
            min_value=item.min_value,
            max_value=item.max_value,
            is_critical=item.is_critical,
            unit_of_measurement=item.unit_of_measurement,
        )
        await self.redis.set(cache_key, entry.model_dump_json(), expire=300)
        return entry

    async def _publish_error(self, *, timestamp: datetime, description: str, value_name: str, value: float) -> None:
        await self.redis.publish(
            "dashboard:errors",
            json.dumps(
                {
                    "timestamp": timestamp.isoformat(),
                    "description": description,
                    "value_name": value_name,
                    "value": value,
                },
                ensure_ascii=False,
            ),
        )

    async def _publish_stages_empty(self) -> None:
        await self.redis.publish(
            "dashboard:stages",
            json.dumps({}, ensure_ascii=False),
        )

    async def _publish_stages(
        self,
        *,
        errors_count: int,
        current_mm: int,
        left_val: float,
        left_ok: bool,
        right_val: float,
        right_ok: bool,
        vleft_val: float,
        vleft_ok: bool,
        vright_val: float,
        vright_ok: bool,
        screws_completed: int,
        resistance: float,
        resistance_avg: float,
        resistance_ok: bool,
        gauge: float,
        gauge_ok: bool,
        gauge_avg: float,
        nuts: list[dict] | None = None,
    ) -> None:
        await self.redis.publish(
            "dashboard:stages",
            json.dumps(
                {
                    "errors_count": errors_count,
                    "mmAlongRail": current_mm,
                    "mm_side_wear_left": left_val,
                    "mm_side_wear_left_ok": left_ok,
                    "mm_side_wear_right": right_val,
                    "mm_side_wear_right_ok": right_ok,
                    "mm_vertical_wear_left": vleft_val,
                    "mm_vertical_wear_left_ok": vleft_ok,
                    "mm_vertical_wear_right": vright_val,
                    "mm_vertical_wear_right_ok": vright_ok,
                    "screws_completed": screws_completed,
                    "resistance": resistance,
                    "resistance_avg": resistance_avg,
                    "resistance_ok": resistance_ok,
                    "mm_gauge": gauge,
                    "mm_gauge_ok": gauge_ok,
                    "mm_gauge_avg": gauge_avg,
                    "nuts": nuts if nuts is not None else [],
                },
                ensure_ascii=False,
            ),
        )

    @staticmethod
    def _build_nuts_payload(dashboard_nuts: dict[int, dict]) -> list[dict]:
        """Маппинг каналов M1..M4 -> позиции ЛН/ЛВ/ПН/ПВ (каналы 1,2 — левая сторона)."""
        positions = {1: "ЛН", 2: "ЛВ", 3: "ПН", 4: "ПВ"}
        result: list[dict] = []
        for ch in (1, 2, 3, 4):
            entry = dashboard_nuts.get(ch, {"count": 0, "torque": 0.0, "ok": True})
            result.append(
                {
                    "position": positions[ch],
                    "count": int(entry.get("count", 0)),
                    "torque": float(entry.get("torque", 0.0)),
                    "ok": bool(entry.get("ok", True)),
                }
            )
        return result

    async def _track_bad_range(
        self,
        metric_key: str,
        res_threshold: ThresholdEntry,
        res_value: float,
        current_mm: int,
        active: RailSession,
    ) -> None:
        in_range = res_threshold.min_value <= res_value <= res_threshold.max_value
        if not in_range:
            if not self.state.is_bad_range_active(metric_key):
                self.state.open_bad_range(metric_key, current_mm, res_value)
            return
        if self.state.is_bad_range_active(metric_key):
            opened = self.state.close_bad_range(metric_key)
            if opened:
                start_mm, start_value = opened
                await self.uow.error.add(
                    Error(
                        rail_id=active.rail_id,
                        screw_id=None,
                        value_name=metric_key,
                        description=f"{self.METRIC_DISPLAY.get(metric_key, metric_key)} было неприемлемым с {start_mm} мм по {current_mm} мм",
                        unit_of_measurement=res_threshold.unit_of_measurement,
                        value=start_value,
                        min_value=res_threshold.min_value,
                        max_value=res_threshold.max_value,
                        is_critical=res_threshold.is_critical,
                    )
                )
                await self._publish_error(
                    timestamp=active.last_timestamp or datetime.utcnow(),
                    description=f"{self.METRIC_DISPLAY.get(metric_key, metric_key)} было неприемлемым с {start_mm} мм по {current_mm} мм",
                    value_name=metric_key,
                    value=start_value,
                )

    async def get_threshold_data(self) -> Thresholds:
        cached = await self.redis.get(self.THRESHOLDS_CACHE_KEY)
        if cached:
            return Thresholds.model_validate_json(cached)

        items = await self.uow.threshold.list_all()
        thresholds_dict: dict[str, ThresholdEntry] = {
            t.value: ThresholdEntry(
                min_value=t.min_value,
                max_value=t.max_value,
                is_critical=t.is_critical,
                unit_of_measurement=t.unit_of_measurement,
            )
            for t in items
        }
        thresholds_model = Thresholds(thresholds=thresholds_dict)
        await self.redis.set(self.THRESHOLDS_CACHE_KEY, thresholds_model.model_dump_json(), expire=300)
        return thresholds_model

    async def _add_sensor2_data_legacy_zero_check(
        self, sensor2_data: Sensor2Create, active: RailSession
    ) -> None:
        """
        DEPRECATED: Старый алгоритм — ждём all_frequency_status_zero, потом заканчиваем batch.
        Оставлено для справки.
        """
        if sensor2_data.values.all_frequency_status_zero():
            if self.state.has_screw_session:
                errors_to_add: list[Error] = []
                ft_threshold = await self.get_threshold("frequency_torque")
                for idx, screw in enumerate(list(self.state.iter_screws()), start=1):
                    if ft_threshold:
                        ft_value = screw.frequency_torque
                        if ft_value < ft_threshold.min_value or ft_value > ft_threshold.max_value:
                            side = "левой" if idx in (1, 2) else "правой"
                            verdict = "недостаточно" if ft_value < ft_threshold.min_value else "излишне"
                            description = f"Гайка №{screw.serial_id} по {side} стороне была {verdict} закручена"
                            errors_to_add.append(
                                Error(
                                    rail_id=active.rail_id,
                                    screw_id=screw.screw_id,
                                    value_name="frequency_torque",
                                    description=description,
                                    unit_of_measurement=ft_threshold.unit_of_measurement,
                                    value=ft_value,
                                    min_value=ft_threshold.min_value,
                                    max_value=ft_threshold.max_value,
                                    is_critical=ft_threshold.is_critical,
                                )
                            )
                    await self.uow.screw.update(screw_id=screw.screw_id, status=ScrewStatus.COMPLETED)
                if errors_to_add:
                    await self.uow.error.add_many(errors_to_add)
                    for err in errors_to_add:
                        await self._publish_error(
                            timestamp=sensor2_data.timestamp,
                            description=err.description,
                            value_name=err.value_name,
                            value=err.value,
                        )
                self.state.clear_screw_session()
            return

        sensors = []
        for i in range(1, 5):
            if self.state.screw_session_len < i:
                screw_id = await self.add_screw(
                    getattr(sensor2_data.values, f"frequency_torque_{i}"),
                    sensor2_data.timestamp,
                    rail_id=active.rail_id,
                )
            else:
                screw_id = self.state.screw_session_item(i - 1).screw_id
                self.state.update_screw_max_torque(i - 1, getattr(sensor2_data.values, f"frequency_torque_{i}"))
            sensors.append(
                Sensor2(timestamp=sensor2_data.timestamp, screw_id=screw_id, **sensor2_data.values.model_dump())
            )
        await self.uow.sensor2.add_many(sensors)

    def _modbus_target_rail_id(self, *, for_modbus: bool = False) -> int | None:
        """Modbus (закрутка) — только рельса на посту 2; без fallback на fifo/active."""
        post2 = self.state.post2_tracker()
        if post2.rail_at_post2 is not None:
            return post2.rail_at_post2
        if for_modbus:
            return None
        if post2.fifo_rail_ids:
            return post2.fifo_rail_ids[0]
        active = self.state.get_active_rail()
        return active.rail_id if active else None

    def _rail_session_for_modbus(self, rail_id: int) -> RailSession | None:
        return self.state.find_rail_session(rail_id)

    async def _open_orphan_rail_at_post2(self, ts: datetime) -> int:
        """Создаёт РШР, пропустившую пост 1 (рельс положили между постами).

        На посту 1 рельса не было → РШР не открылась, FIFO пуст. На посту 2 идёт
        реальная закрутка по физически присутствующему рельсу. Запись рождается
        сразу как `rail_at_post2`, поэтому гайки и геометрия поста 2 (R/T) пишутся
        штатно. Геометрии/длины поста 1 нет: длину доберём с энкодера поста 2
        (см. process_second_sensor1_data), факт помечаем замечанием при finalize.
        """
        rail = await self.uow.rail.add(Rail(start_time=ts))
        session = RailSession(
            rail_id=rail.rail_id,
            start_time=ts,
            end_time=None,
            last_mm_along_rail=0,
            last_timestamp=ts,
            start_mm_along_rail=0,
            from_post2=True,
        )
        # Живёт как рельс на посту 2 (waiting + rail_at_post2) — тот же приём, что в
        # rehydrate_in_progress_rails. find_rail_session/_modbus_target_rail_id найдут её.
        self.state.park_at_post2(session)
        post2 = self.state.post2_tracker()
        post2.remove_from_fifo(rail.rail_id)
        post2.rail_at_post2 = rail.rail_id
        await emit_pipeline_event(
            "rshr_opened",
            rshr_id=rail.rail_id,
            event_ts=ts,
            summary=f"Открыт РШР #{rail.rail_id} на посту 2 (пропустил пост 1)",
            payload={"origin": "post2", "no_post1_geometry": True},
        )
        return rail.rail_id

    async def add_sensor2_data(self, sensor2_data: Sensor2Create) -> None:
        await cache_dashboard_env_stats(
            self.redis,
            sensor2_data.values.temperature,
            sensor2_data.values.humidity,
        )

        rail_id = self._modbus_target_rail_id(for_modbus=True)
        if rail_id is None:
            # РШР, пропустившая пост 1: рельс положили между постами, на посту 1 его
            # не было (laser_on_rail=False → не открылся, FIFO пуст). Но на посту 2 он
            # физически есть (лазер горит) и его реально закручивают (моменты M1–M4).
            # Рождаем «сироту» здесь, иначе вся закрутка молча теряется (modbus_skipped).
            # Триггер по моменту, а не по лазеру: закрутку подделать нельзя → нет
            # пустых записей от мигания. Только при ПУСТОМ FIFO: иначе рельс уже едет
            # с поста 1 и ждёт подтверждения сегмента поста 2 (rail_at_post2 ещё None
            # первые ~3 с / 200 мм) — там нельзя плодить дубль, его подхватит штатный
            # _confirm_post2_segment.
            if (
                has_moment_activity(sensor2_data.values)
                and self.state.post2_laser_was_on()
                and not self.state.post2_tracker().fifo_rail_ids
            ):
                rail_id = await self._open_orphan_rail_at_post2(sensor2_data.timestamp)
            if rail_id is None:
                self.state.mark_modbus_skipped_no_post2()
                await emit_pipeline_event(
                    "modbus_skipped",
                    event_ts=sensor2_data.timestamp,
                    summary="Modbus: нет РШР на посту 2",
                    payload={"reason": "no_post2_rail"},
                )
                return
        session = self._rail_session_for_modbus(rail_id)
        if session is None:
            return

        values = sensor2_data.values
        self.state.update_resistance(float(values.resistance))
        self.state.update_temperature(float(values.temperature))

        res_threshold = await self.get_threshold("resistance")
        if res_threshold:
            await self._track_bad_range(
                metric_key="resistance",
                res_threshold=res_threshold,
                res_value=values.resistance,
                current_mm=session.last_mm_along_rail,
                active=session,
            )

        tightening_rail = self.state.tightening_rail_id()
        if self.state.is_tightening_active() and tightening_rail is not None and tightening_rail != rail_id:
            prev_session = self.state.find_rail_session(tightening_rail)
            if prev_session is not None:
                await self._finalize_tightening_cycle(sensor2_data.timestamp, prev_session)

        if self.state.is_tightening_active():
            if all_torque_zero(values):
                streak = self.state.record_zero_torque_packet()
                if streak >= TIMING_CONFIG.cycle_end_zero_packets:
                    await self._finalize_tightening_cycle(sensor2_data.timestamp, session)
            else:
                self.state.reset_zero_torque_streak()
                self.state.bump_tightening_cycle(values)
        elif has_moment_activity(values):
            # Позиция шпалы = живой mm поста 2 (а не замороженный mm поста 1, который
            # был одинаков у всех циклов). По ней потом отличаем повтор от новой шпалы.
            sleeper_mm = self.state.get_post2_current_mm()
            if sleeper_mm is None:
                sleeper_mm = session.last_mm_along_rail
            self.state.start_tightening_cycle(rail_id, sleeper_mm, values)
            await emit_pipeline_event(
                "tightening_started",
                rshr_id=rail_id,
                event_ts=sensor2_data.timestamp,
                summary=f"Начало закрутки РШР #{rail_id}",
                payload={"mm_along_rail": sleeper_mm},
            )
        await self._publish_post2_stages(session)
        return

    async def _finalize_tightening_cycle(self, ts: datetime, session: RailSession) -> None:
        """Завершение цикла: 4 гайки (M1–M4) одной шпалы.

        Если шпала на этой позиции (по mm поста 2) уже закручивалась — это ПОВТОРНАЯ
        закрутка той же шпалы: ОБНОВЛЯЕМ значения тех же гаек, а не создаём дубль
        (иначе эпюра/количество шпал завышается). Новая позиция → новая шпала.
        """
        cycle = self.state.finish_tightening_cycle()
        base = cycle.last_values or {}
        ft_threshold = await self.get_threshold("frequency_torque")
        errors_to_add: list[Error] = []
        sensors: list[Sensor2] = []
        rail_id = session.rail_id
        pos = int(cycle.cycle_start_mm)
        existing = self.state.find_sleeper(rail_id, pos, TIMING_CONFIG.min_sleeper_spacing_mm)
        is_retighten = existing is not None
        per_channel_torque: dict[int, float] = {}
        per_channel_ok: dict[int, bool] = {}
        screw_ids: list[int] = []

        for ch in range(1, 5):
            max_m = float(cycle.max_moment.get(f"M{ch}", 0.0))
            max_f = float(cycle.max_freq.get(f"f{ch}", 0.0))
            if is_retighten:
                # Та же шпала: обновляем существующую гайку последними пиками.
                screw_id = int(existing["screw_ids"][ch - 1])
                await self.uow.screw.update(
                    screw_id=screw_id,
                    max_torque=max_m,
                    max_frequency=max_f,
                    mm_along_rail=pos,
                    status=ScrewStatus.COMPLETED,
                )
            else:
                screw_id = await self.add_screw(
                    max_m,
                    ts,
                    rail_id=rail_id,
                    max_frequency=max_f,
                    mm_along_rail=pos,
                    channel=ch,
                )
                await self.uow.screw.update(screw_id=screw_id, status=ScrewStatus.COMPLETED)
            screw_ids.append(screw_id)

            channel_ok = True
            if ft_threshold and (max_m < ft_threshold.min_value or max_m > ft_threshold.max_value):
                channel_ok = False
                side = "левой" if ch in (1, 2) else "правой"
                verdict = "недостаточно" if max_m < ft_threshold.min_value else "излишне"
                serial = self.state.get_rail_screw_count(rail_id)
                errors_to_add.append(
                    Error(
                        rail_id=rail_id,
                        screw_id=screw_id,
                        value_name="frequency_torque",
                        description=f"Гайка №{serial} по {side} стороне была {verdict} закручена",
                        unit_of_measurement=ft_threshold.unit_of_measurement,
                        value=max_m,
                        min_value=ft_threshold.min_value,
                        max_value=ft_threshold.max_value,
                        is_critical=ft_threshold.is_critical,
                    )
                )
            per_channel_torque[ch] = max_m
            per_channel_ok[ch] = channel_ok

            row = dict(base)
            row[f"frequency_torque_{ch}"] = max_m
            row[f"converter_frequency_{ch}"] = max_f
            for other in range(1, 5):
                if other != ch:
                    row[f"frequency_torque_{other}"] = 0.0
                    row[f"converter_frequency_{other}"] = 0.0
            sensors.append(Sensor2(timestamp=ts, screw_id=screw_id, **row))

        if not is_retighten:
            self.state.register_sleeper(rail_id, pos, screw_ids)

        if errors_to_add:
            await self.uow.error.add_many(errors_to_add)
            for err in errors_to_add:
                await self._publish_error(
                    timestamp=ts,
                    description=err.description,
                    value_name=err.value_name,
                    value=err.value,
                )
        if sensors:
            await self.uow.sensor2.add_many(sensors)
        # Повтор не наращивает счётчик гаек (та же шпала) — только обновляет момент.
        self.state.record_nut_cycle(
            rail_id, per_channel_torque, per_channel_ok, increment=not is_retighten
        )
        verb = "обновлена" if is_retighten else "новая"
        await emit_pipeline_event(
            "tightening_completed",
            rshr_id=rail_id,
            event_ts=ts,
            summary=f"Закрутка ({verb} шпала, {pos} мм): 4 гайки, РШР #{rail_id}",
            payload={
                "screw_count": len(sensors),
                "errors": len(errors_to_add),
                "retighten": is_retighten,
                "sleeper_mm": pos,
            },
        )
        await self._publish_post2_stages(session)

    async def add_screw(
        self,
        frequency_torque: float,
        ts: datetime,
        *,
        rail_id: int,
        max_frequency: float = 0.0,
        mm_along_rail: int | None = None,
        channel: int | None = None,
    ) -> int:
        serial_number = self.state.next_serial_for_rail(rail_id)
        kwargs: dict = dict(
            rail_id=rail_id,
            serial_id=serial_number,
            max_torque=float(frequency_torque),
            max_frequency=float(max_frequency),
        )
        if mm_along_rail is not None:
            kwargs["mm_along_rail"] = int(mm_along_rail)
        if channel is not None:
            kwargs["channel"] = int(channel)
        screw = await self.uow.screw.add(Screw(**kwargs))
        self.state.append_screw(
            ScrewDC(
                screw_id=screw.screw_id,
                serial_id=serial_number,
                timestamp=ts,
                frequency_torque=frequency_torque,
                max_frequency=float(max_frequency),
                channel=channel,
            )
        )
        return screw.screw_id

    def _active_rail_transferred_to_post2(self, active: RailSession) -> bool:
        """РШР уже на посту 2, но active на посту 1 не сняли (лазер не гас)."""
        post2 = self.state.post2_tracker()
        if self.state.is_rail_waiting_at_post2(active.rail_id):
            return True
        return active.rail_id == post2.rail_at_post2

    def _is_mm_reset_for_new_rail(self, active: RailSession, mm: int) -> bool:
        if mm + self.NEW_RAIL_MM_RESET_DROP_MM < active.last_mm_along_rail:
            return True
        return active.last_mm_along_rail >= 500 and mm < active.last_mm_along_rail - 500

    def _should_start_new_rail_on_post1(self, active: RailSession, data: Sensor1Create) -> bool:
        if not (data.values.laser_on_rail_left or data.values.laser_on_rail_right):
            return False
        if self._active_rail_transferred_to_post2(active):
            return True
        # Дебаунс мигания лазера: если лазер пропадал лишь на доли секунды
        # (< POST1_MIN_LASER_OFF_SEC), возврат лазера + сброс mm энкодером — это глитч
        # на ОДНОМ рельсе, а не приход нового. Не раскалываем (фикс фантомных РШР).
        if active.laser_off_at is not None:
            off_sec = (data.timestamp - active.laser_off_at).total_seconds()
            if 0 <= off_sec < TIMING_CONFIG.post1_min_laser_off_sec:
                return False
        # Новый рельс распознаём только по реальному сбросу mm к ~0 после достаточно
        # долгого пропадания лазера (а не по мигающему лазеру — инвариант №6).
        return self._is_mm_reset_for_new_rail(active, int(data.values.mm_along_rail))

    async def _handoff_active_from_post1(self, active: RailSession, ts: datetime) -> None:
        """Снимает active с поста 1, если РШР уже ждёт/стоит на посту 2."""
        current = self.state.get_active_rail()
        if current is None or current.rail_id != active.rail_id:
            return
        if self.state.is_rail_waiting_at_post2(active.rail_id):
            self.state.clear_active()
            return
        if active.laser_off_at is None:
            active.laser_off_at = ts
        await self.park_active_for_post2()

    async def _publish_post1_stages_for_packet(self, data: Sensor1Create, active: RailSession) -> None:
        current_mm = data.values.mm_along_rail
        th_left = await self.get_threshold("mm_side_wear_left")
        th_right = await self.get_threshold("mm_side_wear_right")
        th_vleft = await self.get_threshold("mm_vertical_wear_left")
        th_vright = await self.get_threshold("mm_vertical_wear_right")
        th_res = await self.get_threshold("resistance")
        th_gauge = await self.get_threshold("mm_gauge")
        left_val = data.values.mm_side_wear_left
        right_val = data.values.mm_side_wear_right
        vleft_val = data.values.mm_vertical_wear_left
        vright_val = data.values.mm_vertical_wear_right
        left_ok = True if th_left is None else (th_left.min_value <= left_val <= th_left.max_value)
        right_ok = True if th_right is None else (th_right.min_value <= right_val <= th_right.max_value)
        vleft_ok = True if th_vleft is None else (th_vleft.min_value <= vleft_val <= th_vleft.max_value)
        vright_ok = True if th_vright is None else (th_vright.min_value <= vright_val <= th_vright.max_value)
        res_cur = self.state.get_resistance_current()
        res_avg = self.state.get_resistance_average()
        res_ok = True if th_res is None else (th_res.min_value <= res_cur <= th_res.max_value)
        gauge_cur = data.values.mm_gauge
        gauge_ok = True if th_gauge is None else (th_gauge.min_value <= gauge_cur <= th_gauge.max_value)
        errors_count = await self.uow.error.count_by_rail(active.rail_id)
        screws_completed = self.state.get_dashboard_screws()
        mm_gauge_avg = self.state.get_gauge_average()
        geometry = {
            "left_val": left_val,
            "left_ok": left_ok,
            "right_val": right_val,
            "right_ok": right_ok,
            "vleft_val": vleft_val,
            "vleft_ok": vleft_ok,
            "vright_val": vright_val,
            "vright_ok": vright_ok,
            "current_mm": current_mm,
            "gauge": gauge_cur,
            "gauge_ok": gauge_ok,
            "gauge_avg": mm_gauge_avg,
        }
        self.state.set_last_stage_geometry(geometry)
        nuts = self._build_nuts_payload(self.state.get_dashboard_nuts(active.rail_id))
        await self._publish_stages(
            errors_count=errors_count,
            current_mm=current_mm,
            left_val=left_val,
            left_ok=left_ok,
            right_val=right_val,
            right_ok=right_ok,
            vleft_val=vleft_val,
            vleft_ok=vleft_ok,
            vright_val=vright_val,
            vright_ok=vright_ok,
            screws_completed=screws_completed,
            resistance=res_cur,
            resistance_avg=res_avg,
            resistance_ok=res_ok,
            gauge=gauge_cur,
            gauge_ok=gauge_ok,
            gauge_avg=mm_gauge_avg,
            nuts=nuts,
        )

    async def _publish_post2_stages(self, session: RailSession) -> None:
        """Живая публикация стадий во время закрутки на посту 2.

        Геометрия (износ/колея) переиспользуется из последнего снимка поста 1,
        счётчики гаек и момент берутся из live-учёта state.
        """
        rail_id = session.rail_id
        geom = self.state.get_last_stage_geometry() or {}
        errors_count = await self.uow.error.count_by_rail(rail_id)
        screws_completed = self.state.get_dashboard_screws()
        res_cur = self.state.get_resistance_current()
        res_avg = self.state.get_resistance_average()
        th_res = await self.get_threshold("resistance")
        res_ok = True if th_res is None else (th_res.min_value <= res_cur <= th_res.max_value)
        nuts = self._build_nuts_payload(self.state.get_dashboard_nuts(rail_id))
        await self._publish_stages(
            errors_count=errors_count,
            current_mm=int(geom.get("current_mm", session.last_mm_along_rail)),
            left_val=float(geom.get("left_val", 0.0)),
            left_ok=bool(geom.get("left_ok", True)),
            right_val=float(geom.get("right_val", 0.0)),
            right_ok=bool(geom.get("right_ok", True)),
            vleft_val=float(geom.get("vleft_val", 0.0)),
            vleft_ok=bool(geom.get("vleft_ok", True)),
            vright_val=float(geom.get("vright_val", 0.0)),
            vright_ok=bool(geom.get("vright_ok", True)),
            screws_completed=screws_completed,
            resistance=res_cur,
            resistance_avg=res_avg,
            resistance_ok=res_ok,
            gauge=float(geom.get("gauge", 0.0)),
            gauge_ok=bool(geom.get("gauge_ok", True)),
            gauge_avg=float(geom.get("gauge_avg", 0.0)),
            nuts=nuts,
        )

    async def add_sensor1_data(self, data: Sensor1Create) -> None:
        if data.sensor_id == 1:
            await self.process_first_sensor1_data(data)
            return
        if data.sensor_id == 2:
            await self.process_second_sensor1_data(data)
            return
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

    async def process_first_sensor1_data(self, data: Sensor1Create) -> None:
        rail_id = self.state.is_in_closed(data.timestamp)
        if rail_id is not None:
            await self.uow.sensor1.add(
                Sensor1(rail_id=rail_id, timestamp=data.timestamp, **data.values.model_dump())
            )
            return

        active = self.state.get_active_rail()
        if active is not None and self._active_rail_transferred_to_post2(active):
            await self._handoff_active_from_post1(active, data.timestamp)
            active = None

        if active is None:
            await self._handle_post1_idle(data)
            return

        # Появился активный рельс — незавершённый кандидат старта больше не актуален.
        if self.state.has_pending_post1():
            self.state.clear_pending_post1()

        if self._should_start_new_rail_on_post1(active, data):
            if active.laser_off_at is None:
                active.laser_off_at = data.timestamp
            await self.park_active_for_post2()
            if self.state.get_active_rail() is not None:
                await self._handoff_active_from_post1(active, data.timestamp)
            await self.bind_active_rail(data)
            return

        if data.timestamp < active.start_time:
            return

        if not data.values.laser_on_rail_left and not data.values.laser_on_rail_right:
            if active.laser_off_at is None:
                active.laser_off_at = data.timestamp
            # Пост 1: рельс реально прошёл (≥ мин. длины) и лазер погас со сбросом mm к ~0
            # (граница рельса) → паркуем СРАЗУ, не дожидаясь распознавания на посту 2.
            # Освобождает пост 1 под следующую решётку (двух РШР на посту 1 быть не может).
            # Условие mm≈0 отсекает мигание лазера в середине прохода (там mm высокий).
            if (
                active.traversed_mm >= self.RSHR_LENGTH_DISCARD_BELOW_MM
                and int(data.values.mm_along_rail) <= self.MM_RESET_NEAR_ZERO
            ):
                await self.park_active_for_post2()
            else:
                await self._maybe_close_active_rail(data.timestamp)
            await self.uow.sensor1.add(
                Sensor1(rail_id=active.rail_id, timestamp=data.timestamp, **data.values.model_dump())
            )
            return

        # Лазер снова ON без сброса mm — это было кратковременное мигание (рука),
        # отменяем отложенное закрытие, чтобы не расколоть рельс на два.
        if active.laser_off_at is not None:
            active.laser_off_at = None

        await self._apply_sensor1_to_active(data, active)
        return

    async def _handle_post1_idle(self, data: Sensor1Create) -> None:
        """Пост 1, нет активного рельса: подтверждаем старт только по движению mm_along_rail."""
        laser_on = bool(data.values.laser_on_rail_left or data.values.laser_on_rail_right)

        if not laser_on:
            # Лазер погас до подтверждения движением — ложное срабатывание (рука под лазером).
            if self.state.has_pending_post1():
                self.state.clear_pending_post1()
            return

        if not self.state.has_pending_post1():
            self.state.begin_pending_post1(data)
        else:
            self.state.append_pending_post1(data)

        if self.state.pending_post1_advance_mm() >= TIMING_CONFIG.laser_confirm_advance_mm:
            await self._confirm_pending_post1()

    async def _confirm_pending_post1(self) -> None:
        """Движение подтвердило реальный РШР: создаём рельс и проигрываем накопленные пакеты."""
        pending = self.state.take_pending_post1()
        if pending is None or not pending.buffer:
            return
        await self.bind_active_rail(pending.buffer[0])
        active = self.state.get_active_rail()
        if active is None:
            return
        for data in pending.buffer[1:]:
            await self._apply_sensor1_to_active(data, active)

    async def _apply_sensor1_to_active(self, data: Sensor1Create, active: RailSession) -> None:
        """Обработка пакета Sensor1 при активном рельсе и лазере ON."""
        self.state.record_laser_flags(
            left_on_rail=data.values.laser_on_rail_left,
            right_on_rail=data.values.laser_on_rail_right,
        )
        # Отслеживание диапазонов для метрик Sensor1 на текущем мм
        current_mm = data.values.mm_along_rail
        for key in self.S1_RANGE_KEYS:
            th = await self.get_threshold(key)
            if th is None:
                continue
            value = getattr(data.values, key)
            await self._track_bad_range(
                metric_key=key,
                res_threshold=th,
                res_value=float(value),
                current_mm=current_mm,
                active=active,
            )
        self.state.update_active_progress(data.values.mm_along_rail, data.timestamp)
        self.state.update_gauge(float(data.values.mm_gauge))
        await self.uow.sensor1.add(
            Sensor1(
                rail_id=active.rail_id,
                timestamp=data.timestamp,
                **data.values.model_dump(),
            )
        )
        await self._publish_post1_stages_for_packet(data, active)

    async def process_second_sensor1_data(self, data: Sensor1Create) -> None:
        values = data.values
        on_rail = bool(values.laser_on_rail_left or values.laser_on_rail_right)
        was_on = self.state.post2_laser_was_on()
        post2 = self.state.post2_tracker()
        ts = data.timestamp
        current_mm = int(values.mm_along_rail)

        # Живая позиция поста 2 — «адрес шпалы» для текущей закрутки (нужна для
        # дедупа повторной закрутки той же шпалы). Нет рельса под лазером — None.
        self.state.set_post2_current_mm(current_mm if on_rail else None)

        # Максимальный пройденный mm текущей решётки на посту 2 — сигнал «прошла
        # полностью» (≈ длине прохода поста 1) для точной финализации по уходу.
        if on_rail and post2.rail_at_post2 is not None and current_mm > post2.rail_at_post2_max_mm:
            post2.rail_at_post2_max_mm = current_mm

        if on_rail and not was_on:
            # Фронт ON: не выпускаем рельс сразу, открываем кандидата сегмента.
            self.state.set_post2_laser_was_on(True)
            post2.pending_segment = True
            post2.pending_start_mm = current_mm
            post2.pending_start_ts = ts
        elif on_rail and was_on and post2.pending_segment:
            # Кандидат открыт: выпуск из FIFO только после подтверждения движением
            # (mm продвинулся) либо удержанием лазера >= post2_min_segment_sec —
            # страховка на случай, если энкодер поста 2 не двигается.
            advanced = (
                post2.pending_start_mm is not None
                and (current_mm - post2.pending_start_mm) >= TIMING_CONFIG.laser_confirm_advance_mm
            )
            held = (
                post2.pending_start_ts is not None
                and (ts - post2.pending_start_ts) >= timedelta(seconds=TIMING_CONFIG.post2_min_segment_sec)
            )
            if advanced or held:
                post2.pending_segment = False
                post2.pending_start_mm = None
                post2.pending_start_ts = None
                await self._confirm_post2_segment(ts)
        elif not on_rail and was_on:
            self.state.set_post2_laser_was_on(False)
            post2.last_laser_off_at = ts
            # Лазер погас: кандидат сегмента сбрасываем. Сама финализация ушедшего
            # рельса — в _post_event_tick по settle/grace: ждём «хвост» закрутки
            # (моменты приходят ещё ~5–10 с после гашения лазера), потом закрываем.
            post2.pending_segment = False
            post2.pending_start_mm = None
            post2.pending_start_ts = None

        rail_id = self._modbus_target_rail_id(for_modbus=False)
        if rail_id is None:
            rail_id = self.state.is_in_closed(data.timestamp)

        if rail_id is not None:
            # Длина РШР-сироты (пропустившей пост 1) берётся с энкодера поста 2 —
            # геометрии/mm поста 1 у неё нет. Держим last_mm как максимум по горящему
            # лазеру; finalize посчитает длину как segment_length(0, last_mm).
            if on_rail:
                sess = self.state.get_waiting_rail(rail_id)
                if sess is not None and sess.from_post2:
                    self.state.update_waiting_progress(
                        rail_id, max(current_mm, sess.last_mm_along_rail), ts
                    )
            await self.uow.sensor1.add(
                Sensor1(rail_id=rail_id, timestamp=data.timestamp, **values.model_dump())
            )

    async def _confirm_post2_segment(self, ts: datetime) -> None:
        """Подтверждённый движением сегмент поста 2: выпуск рельса из FIFO.

        Инвариант: на посту 2 физически не может быть двух РШР. Поэтому появление
        НОВОЙ решётки (подтверждённый сегмент) означает, что предыдущая обязана уйти.
        Если она не успела финализироваться штатно по лазеру — закрываем принудительно.
        """
        post2 = self.state.post2_tracker()
        # Старая решётка ещё «висит» на посту 2 → принудительный уход (была ошибка
        # финализации: лазер не дал чистый OFF или пакеты ухода не пришли).
        if post2.rail_at_post2 is not None:
            await self._finalize_departed_post2_rail(ts, reason="superseded_by_new_segment")

        if not post2.fifo_rail_ids:
            post2.unmatched_segments += 1
            logger.debug(
                "post2 segment ignored: empty fifo (unmatched=%s)",
                post2.unmatched_segments,
            )
            await emit_pipeline_event(
                "post2_unmatched",
                event_ts=ts,
                summary="Пост 2: лазер без РШР в очереди",
                payload={"unmatched_segments": post2.unmatched_segments},
            )
            return

        departed_id = post2.on_post2_segment_start()  # rail_at_post2 уже снят выше → None
        recognized_id = post2.rail_at_post2
        await emit_pipeline_event(
            "post2_recognized",
            rshr_id=recognized_id,
            event_ts=ts,
            summary=f"Пост 2: распознан проход РШР #{recognized_id}",
            payload={
                "departed_rail_id": departed_id,
                "fifo_remaining": list(post2.fifo_rail_ids),
                "segment_index": post2.post2_segment_index,
            },
        )
        if departed_id is not None:  # подстраховка, штатно departed_id уже None
            await self._depart_rail_from_post2(departed_id, ts)
        if recognized_id is not None:
            active = self.state.get_active_rail()
            if active is not None and active.rail_id == recognized_id:
                await self._handoff_active_from_post1(active, ts)

    async def _finalize_departed_post2_rail(self, ts: datetime, *, reason: str) -> bool:
        """Финализирует текущий `rail_at_post2` (решётка ушла с поста 2) и освобождает
        пост. Возвращает True, если рельс действительно закрыт.

        Единая точка ухода с поста 2 для всех триггеров: чистый OFF лазера, заезд
        следующей решётки, grace-фолбэк. Снимает `rail_at_post2`, чтобы Modbus/закрутка
        не целились в закрытый рельс.
        """
        post2 = self.state.post2_tracker()
        rail_id = post2.rail_at_post2
        if rail_id is None:
            return False
        session = self.state.find_rail_session(rail_id)
        if session is None or session.post2_depart_at is not None:
            post2.rail_at_post2 = None
            post2.rail_at_post2_max_mm = 0
            post2.last_laser_off_at = None
            return False
        logger.info("post2 depart rail_id=%s reason=%s", rail_id, reason)
        await self._depart_rail_from_post2(rail_id, ts)
        post2.rail_at_post2 = None
        post2.rail_at_post2_max_mm = 0
        post2.last_laser_off_at = None
        return True

    async def _depart_rail_from_post2(self, rail_id: int, ts: datetime) -> None:
        session = self.state.find_rail_session(rail_id)
        if session is None:
            return
        session.post2_depart_at = ts
        await emit_pipeline_event(
            "rshr_departed_post2",
            rshr_id=rail_id,
            event_ts=ts,
            summary=f"РШР #{rail_id} ушёл с поста 2",
            payload={"post2_depart_at": ts.isoformat()},
        )
        if self.state.is_tightening_active() and self.state.tightening_rail_id() == rail_id:
            await self._finalize_tightening_cycle(ts, session)
        schedule_rail_departure_burst(rail_id)
        await self.finalize_rail(session)

    async def _maybe_close_departed_post2_rail(self, event_ts: datetime) -> None:
        """Финализация рельса, ушедшего с поста 2 (лазер погас), на каждом событии.

        Два режима ожидания после последнего OFF лазера:
        - **settle** (короткий): рельс реально прошёл (`rail_at_post2_max_mm` дотянул до
          длины) и лазер дал чистый OFF → ждём только «хвост» закрутки (моменты приходят
          ещё ~5–10 с после гашения), затем закрываем. Это ОСНОВНОЙ путь ухода.
        - **grace** (длинный): mm не дотянул (мигание/сирота без длины поста 2) — на
          случай разреженных данных (рельс встал за лазером, пакеты прекратились).

        Безопасно для «парковки между сменами»: недокрученный припаркованный рельс
        лежит ПОД лазером поста 2 (`post2_laser_was_on == True`) либо вовсе без пакетов
        лазера (`last_laser_off_at is None` после регидрации) — в обоих случаях выходим.
        """
        post2 = self.state.post2_tracker()
        if post2.rail_at_post2 is None:
            return
        # Рельс ещё под лазером поста 2 (закрутка либо пауза/парковка) — ждём.
        if self.state.post2_laser_was_on():
            return
        if post2.last_laser_off_at is None:
            return
        if post2.rail_at_post2_max_mm >= self.RSHR_LENGTH_DISCARD_BELOW_MM:
            wait = timedelta(seconds=TIMING_CONFIG.post2_depart_settle_sec)
            reason = "post2_laser_off"
        else:
            wait = timedelta(seconds=TIMING_CONFIG.post2_depart_grace_sec)
            reason = "grace_no_full_pass"
        if event_ts < post2.last_laser_off_at + wait:
            return
        await self._finalize_departed_post2_rail(event_ts, reason=reason)

    async def _post_event_tick(self, event_ts: datetime) -> None:
        """Страховки после каждого merged-события (не зависят от типа пакета).

        Держать синхронным с боевым `_process_merged_event` И офлайн-харнесом
        `scripts/replay_logs.py` — оба вызывают этот метод.
        """
        if self.state.get_active_rail() is not None:
            await self._maybe_close_active_rail(event_ts)
        await self._maybe_close_departed_post2_rail(event_ts)

    async def _maybe_close_active_rail(self, event_ts: datetime) -> None:
        active = self.state.get_active_rail()
        if active is None:
            return
        if active.post2_depart_at is not None:
            return
        if self.state.is_rail_waiting_at_post2(active.rail_id):
            return
        post2 = self.state.post2_tracker()
        if active.rail_id == post2.rail_at_post2 or active.rail_id in post2.fifo_rail_ids:
            return
        if active.laser_off_at is not None:
            grace = timedelta(seconds=TIMING_CONFIG.tail_grace_sec)
            if event_ts >= active.laser_off_at + grace:
                if self.state.is_tightening_active():
                    await self._finalize_tightening_cycle(event_ts, active)
                await self.finalize_rail(active)
                return
        max_open = timedelta(seconds=TIMING_CONFIG.max_rail_open_sec)
        if event_ts >= active.start_time + max_open:
            logger.critical("Rail %s exceeded MAX_RAIL_OPEN_SEC — force close", active.rail_id)
            if self.state.is_tightening_active():
                await self._finalize_tightening_cycle(event_ts, active)
            await self.finalize_rail(active)

    async def park_active_for_post2(self) -> None:
        """Снимает РШР с поста 1 после laser_off; закрутка и эпюра — на посту 2."""
        active = self.state.get_active_rail()
        if active is None or active.laser_off_at is None:
            return
        pass_sec = (active.laser_off_at - active.start_time).total_seconds()
        already_at_post2 = active.rail_id == self.state.post2_tracker().rail_at_post2
        if pass_sec > TIMING_CONFIG.post1_max_pass_sec and not already_at_post2:
            logger.warning(
                "post1 pass discarded (%.0fs > %.0fs) rail_id=%s",
                pass_sec,
                TIMING_CONFIG.post1_max_pass_sec,
                active.rail_id,
            )
            self.state.post2_tracker().remove_from_fifo(active.rail_id)
            await emit_pipeline_event(
                "rshr_discarded",
                rshr_id=active.rail_id,
                event_ts=active.laser_off_at,
                summary=f"РШР #{active.rail_id} отброшен: долгий проход поста 1",
                payload={"reason": "post1_pass_too_long", "pass_sec": pass_sec},
            )
            await self.discard_active_rail()
            return
        if self.state.is_tightening_active() and self.state.tightening_rail_id() == active.rail_id:
            await self._finalize_tightening_cycle(
                active.last_timestamp or datetime.utcnow(),
                active,
            )
        left, right = self.state.get_laser_counts()
        active.laser_left_count = left
        active.laser_right_count = right
        self.state.park_at_post2(active)
        self.state.clear_active()
        self.state.reset_resistance_stats()
        self.state.reset_temperature_stats()
        self.state.reset_gauge_stats()
        self.state.reset_laser_counts()
        await emit_pipeline_event(
            "rshr_parked_post1",
            rshr_id=active.rail_id,
            event_ts=active.laser_off_at or active.last_timestamp,
            summary=f"РШР #{active.rail_id} снят с поста 1, ожидает пост 2",
            payload={
                "start_mm": active.start_mm_along_rail,
                "end_mm": active.last_mm_along_rail,
                "length_mm": active.traversed_mm,
                "fifo": list(self.state.post2_tracker().fifo_rail_ids),
            },
        )
        await self._publish_stages_empty()

    async def discard_active_rail(self) -> None:
        """Удаляет активную РШР с длиной < 15 м (ошибка распознавания)."""
        active = self.state.get_active_rail()
        if active is None:
            return
        rail_id = active.rail_id
        await detach_rail_from_sensor_state(rail_id, self.redis)
        await self.uow.rail.delete_by_id(rail_id)
        self.state.clear_active()
        self.state.reset_resistance_stats()
        self.state.reset_temperature_stats()
        self.state.reset_gauge_stats()
        self.state.reset_total_screws()
        self.state.clear_screw_session()
        self.state.reset_laser_counts()
        self.state.reset_tightening_cycle()
        self.state.clear_rail_sleepers(rail_id)
        await self._publish_stages_empty()

    async def close_active_rail(self) -> None:
        active = self.state.get_active_rail()
        if active is None:
            return
        await self.finalize_rail(active)

    async def finalize_rail(self, session: RailSession) -> None:
        """Финальное закрытие РШР (эпюра, статус) — после ухода с поста 2 или форс-закрытия на посту 1."""
        rail_id = session.rail_id
        if self.state.get_active_rail() and self.state.get_active_rail().rail_id == rail_id:
            self.state.clear_active()
        self.state.pop_waiting_rail(rail_id)

        # Длина — по накопленному пути (сшивает сегменты через сбросы энкодера при
        # мигании лазера). Fallback на last−start для регидрированных сессий (traversed=0).
        length_mm = max(
            session.traversed_mm,
            segment_length_mm(session.start_mm_along_rail, session.last_mm_along_rail),
        )
        # Сироту поста 2 (пропустила пост 1) по длине НЕ отбрасываем: длина у неё —
        # с энкодера поста 2 и может быть неполной, но закрутка реальна (была серия
        # моментов M1–M4). Иначе удалили бы готовую РШР вместе с гайками.
        if not session.from_post2 and length_mm < self.RSHR_LENGTH_DISCARD_BELOW_MM:
            await emit_pipeline_event(
                "rshr_discarded",
                rshr_id=rail_id,
                event_ts=session.last_timestamp,
                summary=f"РШР #{rail_id} отброшен: длина {length_mm} мм < 15 м",
                payload={"reason": "too_short", "length_mm": length_mm, "discarded": True},
            )
            await detach_rail_from_sensor_state(rail_id, self.redis)
            await self.uow.rail.delete_by_id(rail_id)
            await self._publish_stages_empty()
            return

        if self.state.is_tightening_active() and self.state.tightening_rail_id() == rail_id:
            await self._finalize_tightening_cycle(
                session.last_timestamp or datetime.utcnow(),
                session,
            )

        end_mm = session.last_mm_along_rail
        for key, start_mm, start_value in self.state.pop_all_bad_ranges():
            th = await self.get_threshold(key)
            if th is None:
                continue
            await self.uow.error.add(
                Error(
                    rail_id=rail_id,
                    screw_id=None,
                    value_name=key,
                    description=f"{self.METRIC_DISPLAY.get(key, key)} было неприемлемым с {start_mm} мм по {end_mm} мм",
                    unit_of_measurement=th.unit_of_measurement,
                    value=start_value,
                    min_value=th.min_value,
                    max_value=th.max_value,
                    is_critical=th.is_critical,
                )
            )
            await self._publish_error(
                timestamp=(session.last_timestamp if session.last_timestamp else datetime.now()),
                description=f"{self.METRIC_DISPLAY.get(key, key)} было неприемлемым с {start_mm} мм по {end_mm} мм",
                value_name=key,
                value=start_value,
            )

        screw_count = await self.uow.screw.count_by_rail(rail_id)
        self.state.set_rail_screw_count(rail_id, screw_count)

        if session.from_post2:
            # Помечаем замечанием: рельс положили между постами, пост 1 он миновал,
            # геометрического контроля (колея/износ/длина поста 1) по нему нет.
            await self.uow.error.add(
                Error(
                    rail_id=rail_id,
                    screw_id=None,
                    value_name="no_post1_geometry",
                    description="РШР собрана без геометрического контроля (пропущен пост 1)",
                    unit_of_measurement=None,
                    value=0.0,
                    min_value=0.0,
                    max_value=0.0,
                    is_critical=False,
                )
            )

        # Эпюра = число УНИКАЛЬНЫХ шпал (повторные закрутки одной шпалы не дублируются
        # на этапе записи, поэтому screw_count уже без дублей). Берём из реестра позиций;
        # fallback на ceil(screw_count/4) для регидрированных сессий (реестр пуст).
        positions = self.state.rail_sleeper_positions(rail_id)
        sleepers_value: int | None
        sleeper_spacing_mm: int | None = None
        if positions:
            sleepers_value = len(positions)
            if len(positions) > 1:
                # Среднее расстояние между соседними шпалами: (последняя − первая)/(N−1).
                sleeper_spacing_mm = round((positions[-1] - positions[0]) / (len(positions) - 1))
        elif screw_count:
            sleepers_value = math.ceil(screw_count / 4)
        else:
            sleepers_value = None

        update_kwargs: dict = dict(
            status=RailStatus.COMPLETED,
            end_time=session.last_timestamp,
            sleepers=sleepers_value,
            sleeper_spacing_mm=sleeper_spacing_mm,
            side=self._resolve_rail_side_from_session(session),
        )
        update_kwargs["length_mm"] = int(length_mm)
        update_kwargs["resistance_avg"] = self.state.get_resistance_average()
        update_kwargs["temperature_avg"] = self.state.get_temperature_average()
        rmin = self.state.get_resistance_min()
        rmax = self.state.get_resistance_max()
        if rmin is not None:
            update_kwargs["resistance_min"] = rmin
        if rmax is not None:
            update_kwargs["resistance_max"] = rmax
        completed_rail = await self.uow.rail.update_fields(rail_id=rail_id, **update_kwargs)
        session.end_time = completed_rail.end_time if completed_rail else session.last_timestamp
        await self._record_tightening_count_anomaly(rail_id, screw_count, length_mm)
        self.state.append_closed(session)
        self.state.clear_rail_screw_count(rail_id)
        self.state.clear_screw_session()
        self.state.reset_resistance_stats()
        self.state.reset_temperature_stats()
        self.state.reset_gauge_stats()
        self.state.reset_laser_counts()
        self.state.reset_tightening_cycle()
        self.state.clear_rail_sleepers(rail_id)
        await emit_pipeline_event(
            "rshr_closed",
            rshr_id=rail_id,
            event_ts=session.end_time or session.last_timestamp,
            summary=f"РШР #{rail_id} закрыт: {length_mm} мм, {screw_count} гаек",
            payload={
                "length_mm": length_mm,
                "screw_count": screw_count,
                "sleepers": sleepers_value,
                "side": update_kwargs.get("side").value if update_kwargs.get("side") else None,
            },
        )
        await self._publish_stages_empty()

    async def bind_active_rail(self, data: Sensor1Create) -> None:
        prev = self.state.get_active_rail()
        if prev is not None:
            if prev.laser_off_at is not None or self._active_rail_transferred_to_post2(prev):
                if prev.laser_off_at is None:
                    prev.laser_off_at = data.timestamp
                await self.park_active_for_post2()

        self.state.clear_screw_session()
        self.state.reset_resistance_stats()
        self.state.reset_temperature_stats()
        self.state.reset_gauge_stats()
        self.state.reset_tightening_cycle()
        # инициализация счётчиков лазеров для новой активной рельсы
        self.state.reset_laser_counts()
        
        rail = await self.uow.rail.add(Rail(start_time=data.timestamp))
        start_mm = int(data.values.mm_along_rail)
        self.state.set_active(
            RailSession(
                rail_id=rail.rail_id,
                start_time=data.timestamp,
                end_time=None,
                last_mm_along_rail=start_mm,
                last_timestamp=data.timestamp,
                start_mm_along_rail=start_mm,
            )
        )
        self.state.post2_tracker().enqueue_opened_rail(rail.rail_id)
        await emit_pipeline_event(
            "rshr_opened",
            rshr_id=rail.rail_id,
            event_ts=data.timestamp,
            summary=f"Открыт РШР #{rail.rail_id} на посту 1",
            payload={
                "start_mm": start_mm,
                "laser_left": bool(data.values.laser_on_rail_left),
                "laser_right": bool(data.values.laser_on_rail_right),
            },
        )
        # Первичное отслеживание диапазонов для метрик Sensor1
        active = self.state.get_active_rail()
        current_mm = int(data.values.mm_along_rail)
        self.state.update_gauge(float(data.values.mm_gauge))
        # Запишем первый замер лазерных флагов
        self.state.record_laser_flags(
            left_on_rail=bool(data.values.laser_on_rail_left),
            right_on_rail=bool(data.values.laser_on_rail_right),
        )
        for key in self.S1_RANGE_KEYS:
            th = await self.get_threshold(key)
            if th is None:
                continue
            value = getattr(data.values, key)
            await self._track_bad_range(
                metric_key=key,
                res_threshold=th,
                res_value=float(value),
                current_mm=current_mm,
                active=active,
            )
        await self.uow.sensor1.add(
            Sensor1(rail_id=rail.rail_id, timestamp=data.timestamp, **data.values.model_dump())
        )
        await self._publish_post1_stages_for_packet(data, active)

    async def list_sensor1_by_rail(self, rail_id: int, *, limit: int = 20, offset: int = 0):
        if await self.uow.rail.get_by_id(rail_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rail not found")
        return await self.uow.sensor1.list_by_rail(rail_id=rail_id, limit=limit, offset=offset)

    async def _record_tightening_count_anomaly(
        self, rail_id: int, screw_count: int, length_mm: int
    ) -> None:
        """Органика данных: фиксируем 0 / <160 / >220 гаек без «лечения» на объекте."""
        if length_mm < self.RSHR_LENGTH_MIN_OK_MM:
            return
        desc: str | None = None
        if screw_count == 0:
            desc = "Нет данных закрутки (0 гаек) при нормальной длине РШР"
        elif screw_count < TIMING_CONFIG.screws_count_min_ok:
            desc = (
                f"Мало гаек: {screw_count} (ожидалось "
                f"{TIMING_CONFIG.screws_count_min_ok}–{TIMING_CONFIG.screws_count_max_ok})"
            )
        elif screw_count > TIMING_CONFIG.screws_count_max_ok:
            desc = (
                f"Много гаек: {screw_count} (ожидалось "
                f"{TIMING_CONFIG.screws_count_min_ok}–{TIMING_CONFIG.screws_count_max_ok})"
            )
        if desc is None:
            return
        logger.warning("Rail %s tightening anomaly: %s", rail_id, desc)
        await self.uow.error.add(
            Error(
                rail_id=rail_id,
                screw_id=None,
                value_name="screw_count",
                description=desc,
                unit_of_measurement="шт",
                value=float(screw_count),
                min_value=float(TIMING_CONFIG.screws_count_min_ok),
                max_value=float(TIMING_CONFIG.screws_count_max_ok),
                is_critical=screw_count == 0 or screw_count > TIMING_CONFIG.screws_count_max_ok,
            )
        )

    def _resolve_rail_side_from_session(self, session: RailSession) -> RailSide | None:
        left, right = session.laser_left_count, session.laser_right_count
        diff = abs(left - right)
        if left == 0 and right == 0:
            return None
        if diff <= 1:
            return RailSide.CENTER
        return RailSide.LEFT if left > right else RailSide.RIGHT

# ---- Merged event-time worker ----
async def _process_merged_event(state: SensorState, ev: MergedSensorEvent) -> None:
    redis = RedisAPI()
    async with state.fsm_lock():
        try:
            async with get_unscoped_db() as db:
                uow = TimeScaleDBUnitOfWork(db)
                service = SensorService(uow=uow, redis=redis)
                service.state = state
                if ev.kind == "s1":
                    await service.add_sensor1_data(ev.payload)
                else:
                    await service.add_sensor2_data(ev.payload)
                await service._post_event_tick(ev.event_ts)
        except Exception:
            logger.exception(
                "sensor merged worker failed kind=%s event_ts=%s",
                ev.kind,
                ev.event_ts,
            )
        state.set_watermark(_event_watermark_key(ev), ev.event_ts)


async def _sensor_merged_worker(state: SensorState) -> None:
    pending: list[tuple[datetime, int, MergedSensorEvent]] = []
    max_seen: datetime | None = None

    while True:
        item: MergedSensorEvent = await state.merged_queue().get()
        try:
            seq = next(_event_counter)
            heapq.heappush(pending, (item.event_ts, seq, item))
            if max_seen is None or item.event_ts > max_seen:
                max_seen = item.event_ts

            buffer = timedelta(milliseconds=TIMING_CONFIG.reorder_buffer_ms)
            watermark = max_seen - buffer

            while pending and pending[0][0] <= watermark:
                _, _, ev = heapq.heappop(pending)
                # Любая ошибка обработки одного пакета не должна ронять бесконечный
                # цикл worker'а — иначе sensor_raw продолжает писаться, а FSM молча
                # умирает и РШР перестаёт создаваться.
                try:
                    await _handle_merged_event(state, ev)
                except Exception:
                    state.mark_worker_error()
                    logger.exception(
                        "merged worker event failed kind=%s event_ts=%s",
                        ev.kind,
                        ev.event_ts,
                    )
                    try:
                        await emit_pipeline_event(
                            "worker_error",
                            event_ts=ev.event_ts,
                            summary=f"Ошибка обработки пакета {ev.kind}",
                            payload={"kind": ev.kind, "event_ts": ev.event_ts.isoformat()},
                        )
                    except Exception:
                        logger.exception("failed to emit worker_error event")
        finally:
            state.merged_queue().task_done()


def _stream_skew_seconds(received_at: datetime, event_ts: datetime) -> float | None:
    """received_at(сервер) − event_ts(устройство), tz-безопасно. Метрика дрейфа NTP."""
    def naive(dt: datetime | None) -> datetime | None:
        if dt is None:
            return None
        return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt

    r, e = naive(received_at), naive(event_ts)
    if r is None or e is None:
        return None
    return (r - e).total_seconds()


async def _handle_merged_event(state: SensorState, ev: MergedSensorEvent) -> None:
    watermark_key = _event_watermark_key(ev)
    current_wm = state.get_watermark(watermark_key)
    if current_wm is not None and ev.event_ts < current_wm:
        state.mark_packet_reordered()

    # Метрика перекоса часов потока (дрейф NTP на сканере/ПЛК) — для диагностики.
    skew = _stream_skew_seconds(ev.received_at, ev.event_ts)
    if skew is not None:
        state.record_stream_skew(watermark_key, round(skew, 1))
        if abs(skew) > TIMING_CONFIG.max_late_packet_sec / 2:
            logger.warning(
                "clock skew %.0fs on stream %s (NTP drift на сканере/ПЛК?)",
                skew,
                watermark_key,
            )

    closed_rail_id = state.is_in_closed(ev.event_ts)
    closed_session = state.find_closed_rail(closed_rail_id) if closed_rail_id is not None else None
    policy = classify_late_packet(
        ev.event_ts,
        watermark=current_wm,
        rail_start=closed_session.start_time if closed_session else None,
        rail_end=(closed_session.end_time or closed_session.last_timestamp) if closed_session else None,
        rail_closed=closed_session is not None,
        config=TIMING_CONFIG,
        now=ev.received_at,
    )

    if policy == LatePacketPolicy.STALE:
        state.mark_packet_stale()
        logger.warning("Dropping stale packet kind=%s event_ts=%s", ev.kind, ev.event_ts)
        await emit_pipeline_event(
            "packet_stale",
            event_ts=ev.event_ts,
            summary=f"Устаревший пакет {ev.kind}",
            payload={"kind": ev.kind, "stream_key": watermark_key, "event_ts": ev.event_ts.isoformat()},
        )
        return
    if policy == LatePacketPolicy.LATE_APPEND:
        state.mark_packet_late_append()
        await emit_pipeline_event(
            "packet_late",
            rshr_id=closed_rail_id,
            event_ts=ev.event_ts,
            summary=f"Поздний пакет {ev.kind} для РШР #{closed_rail_id}",
            payload={"kind": ev.kind},
        )

    await _process_merged_event(state, ev)


_workers_started = False
_worker_tasks: list[asyncio.Task] = []


async def rehydrate_in_progress_rails(state: SensorState) -> None:
    """Восстановление единственной «парковочной» РШР после рестарта сервиса."""
    async with get_unscoped_db() as db:
        uow = TimeScaleDBUnitOfWork(db)
        in_progress = await uow.rail.list_in_progress()
        if not in_progress:
            return
        if len(in_progress) > 1:
            logger.warning(
                "Multiple IN_PROGRESS rails (%s); keeping newest parked, completing others",
                [r.rail_id for r in in_progress],
            )
            parked = in_progress[0]
            to_complete = in_progress[1:]
            redis = RedisAPI()
            service = SensorService(uow=uow, redis=redis)
            service.state = state
            for rail in to_complete:
                screw_count = await uow.screw.count_by_rail(rail.rail_id)
                await uow.rail.update_fields(
                    rail_id=rail.rail_id,
                    status=RailStatus.COMPLETED,
                    sleepers=math.ceil(screw_count / 4) if screw_count else 0,
                    end_time=rail.start_time,
                )
            in_progress = [parked]

        rail = in_progress[0]
        screw_count = await uow.screw.count_by_rail(rail.rail_id)
        state.set_rail_screw_count(rail.rail_id, screw_count)

        last_row = await uow.sensor1.last_by_rail(rail.rail_id)
        last_mm = int(rail.length_mm or 0)
        last_ts = rail.start_time or datetime.utcnow()
        if last_row is not None:
            last_mm = int(last_row.mm_along_rail)
            last_ts = last_row.timestamp

        session = RailSession(
            rail_id=rail.rail_id,
            start_time=rail.start_time or last_ts,
            end_time=None,
            last_mm_along_rail=last_mm,
            last_timestamp=last_ts,
            start_mm_along_rail=last_mm,
            laser_off_at=last_ts,
        )
        state.park_at_post2(session)
        post2 = state.post2_tracker()
        post2.rail_at_post2 = rail.rail_id
        if rail.rail_id in post2.fifo_rail_ids:
            post2.fifo_rail_ids = [x for x in post2.fifo_rail_ids if x != rail.rail_id]
        logger.info(
            "Rehydrated parked rail_id=%s screws=%s",
            rail.rail_id,
            screw_count,
        )


def get_worker_status() -> dict:
    """Статус фоновых worker'ов для debug-эндпоинта."""
    return {
        "workers_started": _workers_started,
        "worker_count": len(_worker_tasks),
        "workers_alive": [not t.done() for t in _worker_tasks],
        "all_alive": bool(_worker_tasks) and all(not t.done() for t in _worker_tasks),
    }


async def start_sensor_workers() -> list[asyncio.Task]:
    global _workers_started, _worker_tasks
    if _workers_started:
        return _worker_tasks
    state = SENSOR_STATE
    await rehydrate_in_progress_rails(state)
    _worker_tasks = [asyncio.create_task(_sensor_merged_worker(state))]
    _workers_started = True
    return _worker_tasks


async def stop_sensor_workers() -> None:
    global _workers_started, _worker_tasks
    for t in _worker_tasks:
        t.cancel()
    _workers_started = False
    _worker_tasks = []