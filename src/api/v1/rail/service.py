from datetime import datetime

from fastapi import HTTPException, status

from api.v1.base.service import BaseService
from api.v1.rail.schemas import RailsListResponse, RailUpdate, RailRead, RailMetricRead


class RailService(BaseService):
    async def list_rails(
        self,
        *,
        name: str | None,
        status: str | None,
        fastening_type: str | None,
        object_name: str | None,
        limit: int,
        offset: int,
        sort_by: str | None = None,
        order: str | None = None,
    ) -> RailsListResponse:
        items, total = await self.uow.rail.list_filtered_paginated(
            name=name,
            status=status,
            fastening_type=fastening_type,
            object_name=object_name,
            limit=limit,
            offset=offset,
            sort_by=(sort_by or "rail_id"),
            order_desc=(order or "desc").lower() != "asc",
        )
        return RailsListResponse(items=[RailRead.model_validate(i) for i in items], total=total)

    async def update_rail(self, rail_id: int, payload: RailUpdate) -> RailRead | None:
        updated = await self.uow.rail.update_fields(rail_id, **payload.model_dump(exclude_unset=True))
        return RailRead.model_validate(updated) if updated else None

    async def delete_rail(self, rail_id: int) -> None:
        deleted_id = await self.uow.rail.delete_by_id(rail_id)
        if deleted_id is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rail not found")

    async def delete_rails(self, rail_ids: list[int]) -> int:
        deleted_ids = await self.uow.rail.delete_by_ids(rail_ids)
        if not deleted_ids:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rails not found")
        return len(deleted_ids)

    async def get_aggregated_metrics(self, rail_id: int) -> list[RailMetricRead]:
        # Получаем все Sensor1 и Sensor2 по рельсе
        s1_list = await self.uow.sensor1.list_by_rail(rail_id=rail_id, limit=100000, offset=0)
        s2_list = await self.uow.sensor2.list_by_rail(rail_id=rail_id)

        # Собираем значения по ключам
        def collect_s1(key: str) -> list[float]:
            vals: list[float] = []
            for s in s1_list:
                v = getattr(s, key, None)
                if v is not None:
                    try:
                        vals.append(float(v))
                    except Exception:
                        pass
            return vals

        def collect_s1_with_ts(key: str) -> list[tuple[datetime, float]]:
            vals: list[tuple[datetime, float]] = []
            for s in s1_list:
                v = getattr(s, key, None)
                if v is not None:
                    try:
                        vals.append((s.timestamp, float(v)))
                    except Exception:
                        pass
            return vals

        def latest_s1(key: str) -> tuple[float | None, "datetime | None"]:
            for s in reversed(s1_list):
                v = getattr(s, key, None)
                if v is not None:
                    try:
                        return float(v), s.timestamp
                    except Exception:
                        continue
            return None, None

        def collect_s1_bool(key: str) -> list[bool]:
            vals: list[bool] = []
            for s in s1_list:
                v = getattr(s, key, None)
                if v is not None:
                    vals.append(bool(v))
            return vals

        def latest_s1_bool(key: str) -> tuple[bool | None, datetime | None]:
            for s in reversed(s1_list):
                v = getattr(s, key, None)
                if v is not None:
                    return bool(v), s.timestamp
            return None, None

        def collect_s1_bool_with_ts(key: str) -> list[tuple[datetime, bool]]:
            vals: list[tuple[datetime, bool]] = []
            for s in s1_list:
                v = getattr(s, key, None)
                if v is not None:
                    vals.append((s.timestamp, bool(v)))
            return vals

        def collect_s2(key: str) -> list[float]:
            vals: list[float] = []
            for s in s2_list:
                v = getattr(s, key, None)
                if v is not None:
                    try:
                        vals.append(float(v))
                    except Exception:
                        pass
            return vals

        def collect_s2_with_ts(key: str) -> list[tuple[datetime, float]]:
            vals: list[tuple[datetime, float]] = []
            for s in s2_list:
                v = getattr(s, key, None)
                if v is not None:
                    try:
                        vals.append((s.timestamp, float(v)))
                    except Exception:
                        pass
            return vals

        def latest_s2(key: str) -> tuple[float | None, "datetime | None"]:
            for s in reversed(s2_list):
                v = getattr(s, key, None)
                if v is not None:
                    try:
                        return float(v), s.timestamp
                    except Exception:
                        continue
            return None, None

        def collect_s2_int(key: str) -> list[int]:
            vals: list[int] = []
            for s in s2_list:
                v = getattr(s, key, None)
                if v is not None:
                    try:
                        vals.append(int(v))
                    except Exception:
                        pass
            return vals

        def collect_s2_int_with_ts(key: str) -> list[tuple[datetime, int]]:
            vals: list[tuple[datetime, int]] = []
            for s in s2_list:
                v = getattr(s, key, None)
                if v is not None:
                    try:
                        vals.append((s.timestamp, int(v)))
                    except Exception:
                        pass
            return vals

        def latest_s2_int(key: str) -> tuple[int | None, "datetime | None"]:
            for s in reversed(s2_list):
                v = getattr(s, key, None)
                if v is not None:
                    try:
                        return int(v), s.timestamp
                    except Exception:
                        continue
            return None, None

        def avg(vals: list[float]) -> float | None:
            return (sum(vals) / len(vals)) if vals else None

        def max_val(vals: list[float]) -> float | None:
            return max(vals) if vals else None

        # Получаем пороги для "required"
        thresholds = {t.value: t async for t in _async_iter(await self.uow.threshold.list_all())}

        def required_for(key: str) -> str | None:
            th = thresholds.get(key)
            if not th:
                return None
            unit = f" {th.unit_of_measurement}" if th.unit_of_measurement else ""
            return f"от {th.min_value}{unit} до {th.max_value}{unit}"

        items: list[RailMetricRead] = []

        # 1) Пустое агрегирование
        empty_keys = [
            ("encoder1", "encoder1"),
            ("encoder2", "encoder2"),
            ("encoder3", "encoder3"),
            ("encoder4", "encoder4"),
        ]
        for disp, key in empty_keys:
            vals = collect_s1(key)
            latest_value, latest_ts = latest_s1(key)
            items.append(
                RailMetricRead(
                    rail_id=rail_id,
                    name=disp,
                    value=latest_value,
                    required=None,
                    values=collect_s1_with_ts(key),
                    note=None,
                )
            )

        laser_keys = [
            ("laserOnRailLeft", "laser_on_rail_left"),
            ("laserOnRailRight", "laser_on_rail_right"),
            ("laserOnTieLeft", "laser_on_tie_left"),
            ("laserOnTieRight", "laser_on_tie_right"),
        ]
        for disp, key in laser_keys:
            latest_value, latest_ts = latest_s1_bool(key)
            # Для совместимости value остаётся числом (0/1) либо None
            num_value: float | None
            if latest_value is None:
                num_value = None
            else:
                num_value = 1.0 if latest_value else 0.0
            items.append(
                RailMetricRead(
                    rail_id=rail_id,
                    name=disp,
                    value=num_value,
                    required=None,
                    values=collect_s1_bool_with_ts(key),
                    note=None,
                )
            )

        s2_status_keys = [
            ("Состояние ПЧ1", "frequency_status_1"),
            ("Состояние ПЧ2", "frequency_status_2"),
            ("Состояние ПЧ3", "frequency_status_3"),
            ("Состояние ПЧ4", "frequency_status_4"),
        ]
        for disp, key in s2_status_keys:
            latest_value, latest_ts = latest_s2_int(key)
            num_value: float | None = float(latest_value) if latest_value is not None else None
            items.append(
                RailMetricRead(
                    rail_id=rail_id,
                    name=disp,
                    value=num_value,
                    required=None,
                    values=collect_s2_int_with_ts(key),
                    note=None,
                )
            )

        # 2) Максимум
        mm_along_vals = collect_s1("mm_along_rail")
        max_mm = max_val(mm_along_vals)
        if max_mm is not None:
            # ищем timestamp первого вхождения максимума с конца (последнее измерение с макс. значением)
            for s in reversed(s1_list):
                v = getattr(s, "mm_along_rail", None)
                if v is not None and float(v) == float(max_mm):
                    # timestamp можно использовать в будущем, но сейчас не включаем в схему
                    break
        items.append(
            RailMetricRead(
                rail_id=rail_id,
                name="mmAlongRail",
                value=max_mm,
                required=None,
                values=collect_s1_with_ts("mm_along_rail"),
                note=None,
            )
        )

        # 3) Среднее
        avg_map = [
            ("mmBoltHeightLeftInner", "mm_bolt_height_left_inner", "mm_bolt_height_left_inner"),
            ("mmBoltHeightLeftOuter", "mm_bolt_height_left_outer", "mm_bolt_height_left_outer"),
            ("mmBoltHeightRightInner", "mm_bolt_height_right_inner", "mm_bolt_height_right_inner"),
            ("mmBoltHeightRightOuter", "mm_bolt_height_right_outer", "mm_bolt_height_right_outer"),
            ("mmGauge", "mm_gauge", "mm_gauge"),
            ("mmSideWearLeft", "mm_side_wear_left", "mm_side_wear_left"),
            ("mmSideWearRight", "mm_side_wear_right", "mm_side_wear_right"),
            ("mmVerticalWearLeft", "mm_vertical_wear_left", "mm_vertical_wear_left"),
            ("mmVerticalWearRight", "mm_vertical_wear_right", "mm_vertical_wear_right"),
            ("radRailTiltLeft", "rad_rail_tilt_left", "rad_rail_tilt_left"),
            ("radRailTiltRight", "rad_rail_tilt_right", "rad_rail_tilt_right"),
        ]
        for disp, key, th_key in avg_map:
            vals = collect_s1(key)
            avg_val = avg(vals)
            latest_value, latest_ts = latest_s1(key)
            items.append(
                RailMetricRead(
                    rail_id=rail_id,
                    name=disp,
                    value=avg_val,
                    required=required_for(th_key),
                    values=collect_s1_with_ts(key),
                    note=None,
                )
            )

        # Средние по Sensor2: температура и влажность
        temp_vals = collect_s2("temperature")
        items.append(
            RailMetricRead(
                rail_id=rail_id,
                name="temperature",
                value=avg(temp_vals),
                required=required_for("temperature"),
                values=collect_s2_with_ts("temperature"),
                note=None,
            )
        )
        hum_vals = collect_s2("humidity")
        items.append(
            RailMetricRead(
                rail_id=rail_id,
                name="humidity",
                value=avg(hum_vals),
                required=required_for("humidity"),
                values=collect_s2_with_ts("humidity"),
                note=None,
            )
        )

        torque_keys = [
            ("Момент ПЧ1", "frequency_torque_1"),
            ("Момент ПЧ2", "frequency_torque_2"),
            ("Момент ПЧ3", "frequency_torque_3"),
            ("Момент ПЧ4", "frequency_torque_4"),
        ]
        for disp, key in torque_keys:
            vals = collect_s2(key)
            items.append(
                RailMetricRead(
                    rail_id=rail_id,
                    name=disp,
                    value=avg(vals),
                    required=required_for("frequency_torque"),
                    values=collect_s2_with_ts(key),
                    note=None,
                )
            )

        conv_freq_keys = [
            ("Частота ПЧ1", "converter_frequency_1"),
            ("Частота ПЧ2", "converter_frequency_2"),
            ("Частота ПЧ3", "converter_frequency_3"),
            ("Частота ПЧ4", "converter_frequency_4"),
        ]
        for disp, key in conv_freq_keys:
            vals = collect_s2(key)
            items.append(
                RailMetricRead(
                    rail_id=rail_id,
                    name=disp,
                    value=avg(vals),
                    required=None,
                    values=collect_s2_with_ts(key),
                    note=None,
                )
            )

        return items


async def _async_iter(seq):
    for x in seq:
        yield x


