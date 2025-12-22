from datetime import datetime
import math
import json

from api.v1.sensor.schemas import ThresholdEntry, Thresholds, RailSession, Screw as ScrewDC
from api.v1.base.service import BaseService
from api.v1.sensor.schemas import Sensor1Create, Sensor2Create
from api.v1.sensor.state import SensorState
from infra.timescale_db.models import Rail, Sensor1, Sensor2, Screw, RailStatus, ScrewStatus, Error, RailSide


class SensorService(BaseService):
    state: SensorState

    THRESHOLDS_CACHE_KEY = "thresholds:all"

    # Человекочитаемые имена метрик
    METRIC_DISPLAY: dict[str, str] = {
        "resistance": "Сопротивление между рельсами",
        "mm_gauge": "Ширина колеи",
        "mm_side_wear_left": "Боковой износ левого рельса",
        "mm_side_wear_right": "Боковой износ правого рельса",
        "mm_vertical_wear_left": "Вертикальный износ левого рельса",
        "mm_vertical_wear_right": "Вертикальный износ правого рельса",
        "rad_rail_tilt_left": "Подуклонка левого рельса",
        "rad_rail_tilt_right": "Подуклонка правого рельса",
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
        resistance_ok: bool,
        gauge: float,
        gauge_ok: bool,
        gauge_avg: float,
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
                    "resistance_ok": resistance_ok,
                    "mm_gauge": gauge,
                    "mm_gauge_ok": gauge_ok,
                    "mm_gauge_avg": gauge_avg,
                },
                ensure_ascii=False,
            ),
        )
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
                    timestamp=datetime.now(),
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

    async def add_sensor2_data(self, sensor2_data: Sensor2Create) -> None:
        await self.redis.set("dashboard:stats:temperature_current", sensor2_data.values.temperature, expire=300)
        await self.redis.set("dashboard:stats:humidity_current", sensor2_data.values.humidity, expire=300)

        if not self.state.has_active_rail():
            await self._publish_stages_empty()
            return
        active = self.state.get_active_rail()
        self.state.update_resistance(float(sensor2_data.values.resistance))

        res_threshold = await self.get_threshold("resistance")
        if res_threshold:
            await self._track_bad_range(
                metric_key="resistance",
                res_threshold=res_threshold,
                res_value=sensor2_data.values.resistance,
                current_mm=active.last_mm_along_rail if active else 0,
                active=active,
            )

        if sensor2_data.values.all_frequency_status_zero():
            if self.state.has_screw_session:
                errors_to_add: list[Error] = []
                ft_threshold = await self.get_threshold("frequency_torque")
                completed_batch: list[ScrewDC] = []
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
                    completed_batch.append(screw)
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
                )
            else:
                screw_id = self.state.screw_session_item(i-1).screw_id
                self.state.update_screw_max_torque(i-1, getattr(sensor2_data.values, f"frequency_torque_{i}"))
            sensors.append(
                Sensor2(timestamp=sensor2_data.timestamp, screw_id=screw_id, **sensor2_data.values.model_dump())
            )
        await self.uow.sensor2.add_many(sensors)

    async def add_screw(self, frequency_torque: float, ts: datetime) -> int:
        serial_number = self.state.next_serial()
        active = self.state.get_active_rail()
        screw = await self.uow.screw.add(Screw(rail_id=active.rail_id, serial_id=serial_number))
        self.state.append_screw(
            ScrewDC(
                screw_id=screw.screw_id,
                serial_id=serial_number,
                timestamp=ts,
                frequency_torque=frequency_torque,
            )
        )
        return screw.screw_id

    async def add_sensor1_data(self, data: Sensor1Create) -> None:
        rail_id = self.state.is_in_closed(data.timestamp)
        if rail_id is not None:
            await self.uow.sensor1.add(
                Sensor1(rail_id=rail_id, timestamp=data.timestamp, **data.values.model_dump())
            )
            return

        active = self.state.get_active_rail()
        if active:
            if data.timestamp < active.start_time:
                return

            if data.values.mm_along_rail >= active.last_mm_along_rail:
                # Копим статистику по лазерам для определения стороны рельсы
                self.state.record_laser_flags(
                    left_on_rail=bool(data.values.laser_on_rail_left),
                    right_on_rail=bool(data.values.laser_on_rail_right),
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
                res_ok = True if th_res is None else (th_res.min_value <= res_cur <= th_res.max_value)
                gauge_cur = data.values.mm_gauge
                gauge_ok = True if th_gauge is None else (th_gauge.min_value <= gauge_cur <= th_gauge.max_value)
                errors_count = await self.uow.error.count_by_rail(active.rail_id)
                screws_completed = self.state.get_total_screws()
                mm_gauge_avg = self.state.get_gauge_average()
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
                    resistance_ok=res_ok,
                    gauge=gauge_cur,
                    gauge_ok=gauge_ok,
                    gauge_avg=mm_gauge_avg,
                )
            elif data.values.mm_along_rail == 0:
                await self.close_active_rail()
            else:
                # Если произошёл откат более чем на 5% текущего прогресса — закрываем рельсу и открываем новую
                last_mm = max(1, int(active.last_mm_along_rail))
                curr_mm = int(data.values.mm_along_rail)
                if curr_mm < active.last_mm_along_rail:
                    decrease_ratio = (last_mm - curr_mm) / float(last_mm)
                    if decrease_ratio > 0.05:
                        await self.close_active_rail()
                        await self.bind_active_rail(data)
                    else:
                        # Меньше 5% — сохраняем измерение, но фиксируем сбой датчика
                        await self.uow.sensor1.add(
                            Sensor1(
                                rail_id=active.rail_id,
                                timestamp=data.timestamp,
                                **data.values.model_dump(),
                            )
                        )
                        delta_mm = float(last_mm - curr_mm)
                        description = f"Сбой датчика расстояния: откат {delta_mm:.0f} мм ({decrease_ratio * 100:.2f}%)"
                        await self.uow.error.add(
                            Error(
                                rail_id=active.rail_id,
                                screw_id=None,
                                value_name="mm_along_rail_backtrack",
                                description=description,
                                unit_of_measurement="мм",
                                value=delta_mm,
                                min_value=0.0,
                                max_value=0.0,
                                is_critical=False,
                            )
                        )
                        await self._publish_error(
                            timestamp=data.timestamp,
                            description=description,
                            value_name="mm_along_rail_backtrack",
                            value=delta_mm,
                        )
            return

        if data.values.mm_along_rail > 0:
            await self.bind_active_rail(data)
        else:
            await self._publish_stages_empty()
        return

    async def close_active_rail(self) -> None:
        active = self.state.get_active_rail()
        # Закрываем все открытые диапазоны "плохих" значений на конце рельсы
        end_mm = active.last_mm_along_rail
        for key, start_mm, start_value in self.state.pop_all_bad_ranges():
            th = await self.get_threshold(key)
            if th is None:
                continue
            await self.uow.error.add(
                Error(
                    rail_id=active.rail_id,
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
                timestamp=(active.last_timestamp if active.last_timestamp else datetime.now()),
                description=f"{self.METRIC_DISPLAY.get(key, key)} было неприемлемым с {start_mm} мм по {end_mm} мм",
                value_name=key,
                value=start_value,
            )
        completed_rail = await self.uow.rail.update_fields(
            rail_id=active.rail_id,
            status=RailStatus.COMPLETED,
            end_time=active.last_timestamp,
            sleepers=math.ceil(self.state.get_total_screws() / 4),
            side=self._resolve_rail_side(),
        )
        active.end_time = completed_rail.end_time
        self.state.append_closed(active)
        self.state.clear_active()
        self.state.reset_resistance_stats()
        self.state.reset_gauge_stats()
        self.state.reset_total_screws()
        self.state.clear_screw_session()
        self.state.reset_laser_counts()
        await self._publish_stages_empty()

    async def bind_active_rail(self, data: Sensor1Create) -> None:
        self.state.reset_total_screws()
        self.state.clear_screw_session()
        self.state.reset_resistance_stats()
        self.state.reset_gauge_stats()
        # инициализация счётчиков лазеров для новой активной рельсы
        self.state.reset_laser_counts()
        
        rail = await self.uow.rail.add(Rail(start_time=data.timestamp))
        self.state.set_active(RailSession(
            rail_id=rail.rail_id,
            start_time=data.timestamp,
            end_time=None,
            last_mm_along_rail=data.values.mm_along_rail,
            last_timestamp=data.timestamp,
        ))
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

    async def list_sensor1_by_rail(self, rail_id: int, *, limit: int = 20, offset: int = 0):
        return await self.uow.sensor1.list_by_rail(rail_id=rail_id, limit=limit, offset=offset)

    def _resolve_rail_side(self) -> RailSide | None:
        """
        Определяет сторону рельсы по накопленным значениям:
        - если |left - right| <= 1 — Центральная
        - иначе — сторона с большим количеством True.
        """
        left, right = self.state.get_laser_counts()
        diff = abs(left - right)
        if left == 0 and right == 0:
            return None
        if diff <= 1:
            return RailSide.CENTER
        return RailSide.LEFT if left > right else RailSide.RIGHT
