#!/usr/bin/env python3
"""Прогон сырых логов датчиков через НАСТОЯЩИЙ FSM (api/v1/sensor/service.py).

Зачем: офлайн-скрипты `test toch/simulate_capture.py` и `scripts/verify_rshr_replay.py`
содержат СВОИ копии логики FSM и расходятся с боевым `service.py`. Этот харнес вместо
копии гоняет сырьё через сам `SensorService` + `SensorState` + pydantic-схемы, подменяя
только БД/Redis/Telegram заглушками (они не влияют на распознавание — только на хранение).
Значит выход совпадает с продом, и можно, зная что реально было, проверять корректность.

Запуск (обычный python3, нужен только pydantic, который уже стоит):
    python3 scripts/replay_logs.py --rshr /путь/rshr_data.jsonl --modbus /путь/modbus_data.jsonl

Полезные флаги:
    --from "2026-06-25T06:40:00"   только события с этого момента (по метке устройства)
    --to   "2026-06-25T06:50:00"   только до этого момента
    --events                       печатать всю цепочку pipeline-событий
    --json out.json                выгрузить результат в JSON (для сравнения во времени)
    --expected ground_truth.json   сверить с эталоном (rails/screws/...)

Метки устройств в записи РАЗЪЕХАВШИЕСЯ (NTP): сортируем по метке устройства — в окне
закрутки часы сходятся, так что порядок корректен. Перекос показывается в шапке отчёта.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import types
from datetime import datetime
from pathlib import Path

# --------------------------------------------------------------------------------------
# 1. Бутстрап путей + заглушки тяжёлых модулей (до импорта service.py)
# --------------------------------------------------------------------------------------
SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))


def _shim_package(name: str, real_dir: Path) -> None:
    """Синтетический пакет: подсовывает __path__ на реальную папку, но НЕ запускает
    реальный __init__.py родителя (тот тянет jwt/fastapi-роутеры и т.п.)."""
    mod = types.ModuleType(name)
    mod.__path__ = [str(real_dir)]
    mod.__package__ = name
    sys.modules[name] = mod


def _stub_module(name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


# Родительские пакеты с «тяжёлым» __init__ — шимим, чтобы грузились только нужные подмодули.
_shim_package("api", SRC / "api")
_shim_package("api.v1", SRC / "api" / "v1")
_shim_package("api.v1.rail", SRC / "api" / "v1" / "rail")
_shim_package("api.v1.ws", SRC / "api" / "v1" / "ws")
_shim_package("api.v1.stream_monitor", SRC / "api" / "v1" / "stream_monitor")
_shim_package("infra", SRC / "infra")
_shim_package("infra.timescale_db", SRC / "infra" / "timescale_db")
_shim_package("infra.redis", SRC / "infra" / "redis")
_shim_package("infra.telegram", SRC / "infra" / "telegram")


# --- заглушки БД-моделей: принимают любые kwargs, хранят как атрибуты --------------------
class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Enum(str):
    pass


def _enum_cls(name, *members):
    """Возвращает КЛАСС (а не экземпляр) — чтобы аннотации вида `RailSide | None`
    вычислялись (функц. аннотации в service.py не ленивые)."""
    return type(name, (), {m: _Enum(m) for m in members})


_stub_module(
    "infra.timescale_db.models",
    Rail=_Row, Sensor1=_Row, Sensor2=_Row, Screw=_Row, Error=_Row,
    RailStatus=_enum_cls("RailStatus", "COMPLETED", "IN_PROGRESS"),
    ScrewStatus=_enum_cls("ScrewStatus", "COMPLETED", "IN_PROGRESS"),
    RailSide=_enum_cls("RailSide", "LEFT", "RIGHT", "CENTER"),
)


# --- заглушки соединений/UoW (реальные fake-репозитории создаём в драйвере) --------------
class _StubUoW:  # noqa: D401 - только для импорта типа в BaseService/служебном пути
    def __init__(self, *a, **k):
        pass


class _StubRedis:
    def __init__(self, *a, **k):
        pass


def _get_unscoped_db():
    raise RuntimeError("get_unscoped_db не должен вызываться в реплее")


_stub_module("infra.timescale_db.uow", TimeScaleDBUnitOfWork=_StubUoW)
_stub_module("infra.timescale_db.ts_db", get_unscoped_db=_get_unscoped_db)
_stub_module("infra.redis.redis_api", RedisAPI=_StubRedis)


async def _noop_async(*a, **k):
    return None


def _noop_sync(*a, **k):
    return None


_stub_module("api.v1.rail.fsm", detach_rail_from_sensor_state=_noop_async)
_stub_module("api.v1.ws.service", cache_dashboard_env_stats=_noop_async)
_stub_module("infra.telegram.rail_burst", schedule_rail_departure_burst=_noop_sync)

# --- перехват pipeline-событий (главный выход распознавания) -----------------------------
PIPELINE_EVENTS: list[dict] = []


async def _emit_pipeline_event(event_type, *, rshr_id=None, payload=None, event_ts=None, summary=None):
    PIPELINE_EVENTS.append(
        {
            "event_type": event_type,
            "rshr_id": rshr_id,
            "event_ts": event_ts.isoformat() if isinstance(event_ts, datetime) else event_ts,
            "payload": payload or {},
            "summary": summary,
        }
    )


_stub_module("api.v1.stream_monitor.pipeline_hooks", emit_pipeline_event=_emit_pipeline_event)
# stream_monitor.service используется только роутером — пустышка на всякий случай
_stub_module("api.v1.stream_monitor.service", stream_monitor=types.SimpleNamespace())

# --- лёгкая заглушка fastapi (service.py/state.py импортируют HTTPException/status/Depends)
if "fastapi" not in sys.modules:
    class _HTTPException(Exception):
        def __init__(self, *a, status_code=None, detail=None, **k):
            super().__init__(detail or "")
            self.status_code = status_code

    def _Depends(x=None):
        return x

    _stub_module("fastapi", HTTPException=_HTTPException, Depends=_Depends, status=types.SimpleNamespace())
    _stub_module(
        "starlette",
        status=types.SimpleNamespace(HTTP_400_BAD_REQUEST=400, HTTP_202_ACCEPTED=202),
    )
    _stub_module(
        "starlette.status", HTTP_400_BAD_REQUEST=400, HTTP_202_ACCEPTED=202,
    )

# --------------------------------------------------------------------------------------
# 2. Импорт НАСТОЯЩИХ классов
# --------------------------------------------------------------------------------------
from api.v1.sensor.schemas import Sensor1Create, Sensor2Create  # noqa: E402
from api.v1.sensor.state import SensorState, MergedSensorEvent  # noqa: E402
from api.v1.sensor.service import SensorService, _event_watermark_key, TIMING_CONFIG  # noqa: E402
from rshr_core.rshr_length import classify_length_mm  # noqa: E402
from rshr_core.tightening import has_moment_activity  # noqa: E402

# Всплески момента (реальная закрутка), пришедшие когда на посту 2 нет РШР → потеряны.
LOST_TIGHTENING_SPIKES = 0


# --------------------------------------------------------------------------------------
# 3. Fake-репозитории (in-memory): хранят ровно то, что нужно FSM для счёта гаек/эпюры
# --------------------------------------------------------------------------------------
class _RailRepo:
    def __init__(self):
        self.rows: dict[int, _Row] = {}
        self._seq = 0

    async def add(self, rail):
        self._seq += 1
        rail.rail_id = self._seq
        self.rows[self._seq] = rail
        return rail

    async def get_by_id(self, rail_id):
        return self.rows.get(rail_id)

    async def update_fields(self, *, rail_id, **kwargs):
        row = self.rows.get(rail_id) or _Row(rail_id=rail_id)
        for k, v in kwargs.items():
            setattr(row, k, v)
        self.rows[rail_id] = row
        return row

    async def delete_by_id(self, rail_id):
        self.rows.pop(rail_id, None)


class _ScrewRepo:
    def __init__(self):
        self._seq = 0
        self.by_rail: dict[int, int] = {}

    async def add(self, screw):
        self._seq += 1
        screw.screw_id = self._seq
        rid = getattr(screw, "rail_id", None)
        if rid is not None:
            self.by_rail[rid] = self.by_rail.get(rid, 0) + 1
        return screw

    async def update(self, *, screw_id, **fields):
        return None

    async def count_by_rail(self, rail_id):
        return self.by_rail.get(rail_id, 0)


class _ErrorRepo:
    def __init__(self):
        self.by_rail: dict[int, int] = {}

    async def add(self, error):
        rid = getattr(error, "rail_id", None)
        if rid is not None:
            self.by_rail[rid] = self.by_rail.get(rid, 0) + 1

    async def add_many(self, errors):
        for e in errors:
            await self.add(e)

    async def count_by_rail(self, rail_id):
        return self.by_rail.get(rail_id, 0)


class _SinkRepo:
    async def add(self, *a, **k):
        return None

    async def add_many(self, *a, **k):
        return None


class _ThresholdRepo:
    async def get_by_value(self, key):
        return None  # без порогов: распознавание рельсов/длин/циклов от них не зависит

    async def list_all(self):
        return []


class FakeUoW:
    def __init__(self):
        self.rail = _RailRepo()
        self.screw = _ScrewRepo()
        self.error = _ErrorRepo()
        self.sensor1 = _SinkRepo()
        self.sensor2 = _SinkRepo()
        self.threshold = _ThresholdRepo()


class FakeRedis:
    async def get(self, *a, **k):
        return None

    async def set(self, *a, **k):
        return None

    async def publish(self, *a, **k):
        return None


# --------------------------------------------------------------------------------------
# 4. Загрузка сырья
# --------------------------------------------------------------------------------------
def _iter_json_objects(path: str):
    """Терпимый парсер JSONL: пересобирает перенесённые строки через raw_decode."""
    buf = Path(path).read_text(encoding="utf-8", errors="replace")
    dec = json.JSONDecoder()
    i, n = 0, len(buf)
    ok = bad = 0
    while i < n:
        while i < n and buf[i] in " \r\n\t":
            i += 1
        if i >= n:
            break
        try:
            obj, end = dec.raw_decode(buf, i)
            i = end
            if isinstance(obj, dict):
                ok += 1
                yield obj
            else:
                bad += 1
        except json.JSONDecodeError:
            nl = buf.find("\n", i)
            if nl == -1:
                break
            i = nl + 1
            bad += 1
    sys.stderr.write(f"  {Path(path).name}: распознано {ok}, пропущено битых {bad}\n")


def load_events(rshr_path: str | None, modbus_path: str | None):
    """Возвращает список (event_ts, kind, payload) отсортированный по метке устройства."""
    events = []
    skipped = 0
    if rshr_path:
        for o in _iter_json_objects(rshr_path):
            try:
                payload = Sensor1Create.model_validate(o)
                events.append((payload.timestamp, "s1", payload))
            except Exception:
                skipped += 1
    if modbus_path:
        for o in _iter_json_objects(modbus_path):
            try:
                payload = Sensor2Create.model_validate(o)
                events.append((payload.timestamp, "s2", payload))
            except Exception:
                skipped += 1
    if skipped:
        sys.stderr.write(f"  пропущено записей с ошибкой валидации: {skipped}\n")
    events.sort(key=lambda e: e[0])
    return events


# --------------------------------------------------------------------------------------
# 5. Драйвер: повторяет _process_merged_event из service.py, но с fake-зависимостями
# --------------------------------------------------------------------------------------
async def run_replay(events, *, ts_from=None, ts_to=None):
    state = SensorState()
    uow = FakeUoW()
    redis = FakeRedis()

    for event_ts, kind, payload in events:
        if ts_from and event_ts < ts_from:
            continue
        if ts_to and event_ts > ts_to:
            continue
        ev = MergedSensorEvent(event_ts=event_ts, kind=kind, payload=payload, received_at=event_ts)
        async with state.fsm_lock():
            service = SensorService(uow=uow, redis=redis)
            service.state = state
            try:
                if kind == "s1":
                    await service.add_sensor1_data(payload)
                else:
                    # До обработки: всплеск момента без РШР на посту 2 = потерянная закрутка
                    if (
                        has_moment_activity(payload.values)
                        and state.post2_tracker().rail_at_post2 is None
                    ):
                        global LOST_TIGHTENING_SPIKES
                        LOST_TIGHTENING_SPIKES += 1
                    await service.add_sensor2_data(payload)
                active = state.get_active_rail()
                if active:
                    await service._maybe_close_active_rail(event_ts)
            except Exception as exc:  # как в проде: один битый пакет не валит прогон
                sys.stderr.write(f"  ! ошибка обработки {kind} @ {event_ts}: {exc!r}\n")
            state.set_watermark(_event_watermark_key(ev), event_ts)

    return state, uow


# --------------------------------------------------------------------------------------
# 6. Отчёт
# --------------------------------------------------------------------------------------
def build_report(state, uow):
    closes = [e for e in PIPELINE_EVENTS if e["event_type"] == "rshr_closed"]
    opens = [e for e in PIPELINE_EVENTS if e["event_type"] == "rshr_opened"]
    parks = [e for e in PIPELINE_EVENTS if e["event_type"] == "rshr_parked_post1"]
    departs = [e for e in PIPELINE_EVENTS if e["event_type"] == "rshr_departed_post2"]
    discards = [e for e in PIPELINE_EVENTS if e["event_type"] == "rshr_discarded"]
    t_started = [e for e in PIPELINE_EVENTS if e["event_type"] == "tightening_started"]
    t_completed = [e for e in PIPELINE_EVENTS if e["event_type"] == "tightening_completed"]

    cycles_by_rail: dict[int, int] = {}
    screws_by_rail: dict[int, int] = {}
    for e in t_completed:
        rid = e["rshr_id"]
        cycles_by_rail[rid] = cycles_by_rail.get(rid, 0) + 1
        screws_by_rail[rid] = screws_by_rail.get(rid, 0) + int(e["payload"].get("screw_count", 0))

    sleepers_reg = getattr(state, "_rail_sleepers", {})
    rails = []
    for rid in sorted(uow.rail.rows):
        row = uow.rail.rows[rid]
        length = getattr(row, "length_mm", None)
        # Для COMPLETED берём сохранённые в рельсе значения (реестр позиций к этому
        # моменту очищен); для IN_PROGRESS — из живого реестра состояния.
        positions = sorted(int(s["pos"]) for s in sleepers_reg.get(rid, []))
        persisted_sleepers = getattr(row, "sleepers", None)
        persisted_spacing = getattr(row, "sleeper_spacing_mm", None)
        if positions:
            uniq = len(positions)
            spacing_mm = round((positions[-1] - positions[0]) / (uniq - 1)) if uniq > 1 else None
        else:
            uniq = int(persisted_sleepers) if persisted_sleepers else 0
            spacing_mm = int(persisted_spacing) if persisted_spacing else None
        rails.append(
            {
                "rail_id": rid,
                "status": str(getattr(row, "status", "IN_PROGRESS")),
                "length_mm": length,
                "length_class": classify_length_mm(length) if isinstance(length, int) else None,
                "sleepers_эпюра": getattr(row, "sleepers", None) or (uniq or None),
                "уник_шпал": uniq,
                "шаг_см": round(spacing_mm / 10, 1) if spacing_mm else None,
                "screws": uow.screw.by_rail.get(rid, 0),
                "tightening_cycles": cycles_by_rail.get(rid, 0),
                "side": str(getattr(row, "side", "")) or None,
            }
        )

    modbus_skipped = sum(1 for e in PIPELINE_EVENTS if e["event_type"] == "modbus_skipped")
    post2_unmatched = sum(1 for e in PIPELINE_EVENTS if e["event_type"] == "post2_unmatched")

    # Предупреждения: распознаём «грязный» старт записи и потерянные закрутки
    warnings = []
    if opens:
        first_start = opens[0]["payload"].get("start_mm")
        if isinstance(first_start, (int, float)) and abs(first_start) > 30_000:
            warnings.append(
                f"Запись началась «на середине»: первый РШР #{opens[0]['rshr_id']} открыт с "
                f"start_mm={first_start} (лазер уже был включён). Его длина и ранний учёт "
                f"недостоверны — для чистого прогона записывайте с момента, когда под лазерами нет рельса."
            )
    if post2_unmatched:
        warnings.append(
            f"{post2_unmatched}×: рельс пришёл на пост 2, а очередь FIFO пуста → его закрутка "
            f"ушла в modbus_skipped (потеряна). Обычно из-за старта записи «на середине»."
        )
    if LOST_TIGHTENING_SPIKES:
        warnings.append(
            f"ПОТЕРЯНО ~{LOST_TIGHTENING_SPIKES} всплесков момента (закрутка) — пришли, когда на "
            f"посту 2 не было распознанного РШР. Это и есть незасчитанная закрутка."
        )

    return {
        "counts": {
            "rshr_opened": len(opens),
            "rshr_parked_post1": len(parks),
            "rshr_departed_post2": len(departs),
            "rshr_closed": len(closes),
            "rshr_discarded": len(discards),
            "tightening_started": len(t_started),
            "tightening_completed": len(t_completed),
            "modbus_skipped": modbus_skipped,
            "lost_tightening_spikes": LOST_TIGHTENING_SPIKES,
            "post2_unmatched": post2_unmatched,
            "pipeline_events_total": len(PIPELINE_EVENTS),
        },
        "rails": rails,
        "warnings": warnings,
        "stream_skew_sec": dict(getattr(state, "_stream_skew_sec", {})),
    }


def print_report(report, *, show_events=False):
    c = report["counts"]
    print("\n" + "=" * 78)
    print("РЕЗУЛЬТАТ РАСПОЗНАВАНИЯ (через настоящий FSM service.py)")
    print("=" * 78)
    print(
        f"Открыто РШР: {c['rshr_opened']} | припарковано: {c['rshr_parked_post1']} | "
        f"ушло с поста2: {c['rshr_departed_post2']} | ЗАКРЫТО: {c['rshr_closed']} | "
        f"отброшено: {c['rshr_discarded']}"
    )
    print(
        f"Циклы закрутки: started={c['tightening_started']} completed={c['tightening_completed']} | "
        f"ПОТЕРЯНО всплесков закрутки={c['lost_tightening_spikes']} | post2_unmatched={c['post2_unmatched']} | "
        f"всего pipeline-событий: {c['pipeline_events_total']}"
    )
    if report.get("warnings"):
        print("\n⚠ ПРЕДУПРЕЖДЕНИЯ:")
        for w in report["warnings"]:
            print(f"  • {w}")
    if report["stream_skew_sec"]:
        sk = ", ".join(f"{k}={v:+.0f}s" for k, v in report["stream_skew_sec"].items())
        print(f"Перекос часов потоков (received−event, тут=0 т.к. реплей): {sk}")

    print("\nРЕЛЬСЫ (по порядку создания):")
    print(
        f"{'id':>4} {'статус':<12} {'длина,мм':>9} {'уник.шпал':>9} {'шаг,см':>7} "
        f"{'циклы':>6} {'гайки(БД)':>9}"
    )
    print("-" * 64)
    for r in report["rails"]:
        ln = r["length_mm"] if r["length_mm"] is not None else "—"
        uniq = r["уник_шпал"] or "—"
        step = r["шаг_см"] if r["шаг_см"] is not None else "—"
        print(
            f"{r['rail_id']:>4} {r['status']:<12} {str(ln):>9} {str(uniq):>9} {str(step):>7} "
            f"{r['tightening_cycles']:>6} {r['screws']:>9}"
        )

    if show_events:
        print("\nЦЕПОЧКА PIPELINE-СОБЫТИЙ:")
        for e in PIPELINE_EVENTS:
            rid = f"#{e['rshr_id']}" if e["rshr_id"] is not None else "—"
            print(f"  {e['event_ts']}  {e['event_type']:<22} {rid:<7} {e['summary'] or ''}")
    print()


def compare_expected(report, expected_path):
    exp = json.loads(Path(expected_path).read_text(encoding="utf-8"))
    print("СВЕРКА С ЭТАЛОНОМ:")
    fails = 0
    for key, want in exp.get("counts", {}).items():
        got = report["counts"].get(key)
        ok = got == want
        fails += 0 if ok else 1
        print(f"  {'OK ' if ok else 'FAIL'} {key}: эталон={want} получено={got}")
    print(f"  => {'ВСЁ СОВПАЛО' if fails == 0 else f'{fails} расхождений'}")
    return fails


def _parse_cli_ts(raw):
    if not raw:
        return None
    return datetime.fromisoformat(raw.replace("Z", "")).replace(tzinfo=None)


def main():
    ap = argparse.ArgumentParser(description="Прогон сырых логов датчиков через настоящий FSM")
    ap.add_argument("--rshr", help="путь к rshr_data.jsonl (Sensor1)")
    ap.add_argument("--modbus", help="путь к modbus_data.jsonl (Sensor2)")
    ap.add_argument("--from", dest="ts_from", help="начало окна, ISO (метка устройства)")
    ap.add_argument("--to", dest="ts_to", help="конец окна, ISO (метка устройства)")
    ap.add_argument("--events", action="store_true", help="печатать всю цепочку pipeline-событий")
    ap.add_argument("--json", dest="json_out", help="выгрузить результат в JSON")
    ap.add_argument("--expected", help="сверить с эталонным JSON")
    args = ap.parse_args()

    if not args.rshr and not args.modbus:
        ap.error("укажите хотя бы --rshr и/или --modbus")

    sys.stderr.write("Загрузка сырья...\n")
    events = load_events(args.rshr, args.modbus)
    sys.stderr.write(f"Всего событий к прогону: {len(events)}\n")

    state, uow = asyncio.run(
        run_replay(events, ts_from=_parse_cli_ts(args.ts_from), ts_to=_parse_cli_ts(args.ts_to))
    )
    report = build_report(state, uow)
    print_report(report, show_events=args.events)

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps({"report": report, "pipeline_events": PIPELINE_EVENTS}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        sys.stderr.write(f"JSON выгружен: {args.json_out}\n")

    if args.expected:
        fails = compare_expected(report, args.expected)
        sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
