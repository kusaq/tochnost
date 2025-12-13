import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from api.v1.sensor.state import SENSOR_STATE
from infra.timescale_db.ts_db import get_unscoped_db
from infra.timescale_db.uow import TimeScaleDBUnitOfWork
from infra.redis.redis_api import RedisAPI


async def run_sender(ws: WebSocket, redis: RedisAPI, channels_to_sub: list[str]) -> None:
    async for ch, data in redis.iter_pubsub_multi(channels_to_sub):
        try:
            if ws.client_state != WebSocketState.CONNECTED:
                break
            payload = data
            try:
                payload = json.loads(data)
            except Exception:
                pass
            message = {"channel": ch, "data": payload}
            await ws.send_text(json.dumps(message, ensure_ascii=False))
        except Exception:
            break


async def run_push_stats(ws: WebSocket, redis: RedisAPI) -> None:
    while ws.client_state == WebSocketState.CONNECTED:
        try:
            now = datetime.now(timezone.utc)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            hour_ago = now - timedelta(hours=1)

            temp = await redis.get("dashboard:stats:temperature_current")
            hum = await redis.get("dashboard:stats:humidity_current")
            temperature = temp if temp is not None else "N/A"
            humidity = hum if hum is not None else "N/A"

            async with get_unscoped_db() as db:
                uow = TimeScaleDBUnitOfWork(db)
                errors_count = await uow.error.count_all()
                rails_today = await uow.rail.count_completed_since(today_start)
                rails_per_hour = await uow.rail.count_completed_since(hour_ago)

            hours_passed = max(1.0, (now - today_start).total_seconds() / 3600.0)
            avg_speed_per_hour = round(rails_today / hours_passed, 2)

            message = {
                "channel": "dashboard:stats",
                "data": {
                    "temperature_current": temperature,
                    "humidity_current": humidity,
                    "errors_count": errors_count,
                    "rails_today": rails_today,
                    "rails_per_hour": rails_per_hour,
                    "avg_speed_per_hour": avg_speed_per_hour,
                },
            }
            await ws.send_text(json.dumps(message, ensure_ascii=False))
        except asyncio.CancelledError:
            break
        except Exception:
            pass
        finally:
            await asyncio.sleep(2)


async def run_push_status(ws: WebSocket) -> None:
    while ws.client_state == WebSocketState.CONNECTED:
        try:
            message: dict[Any, Any] = {
                "channel": "dashboard:status",
            }

            active = SENSOR_STATE.get_active_rail()
            if not active:
                message["data"] = {}
                await ws.send_text(json.dumps(message, ensure_ascii=False))
                await asyncio.sleep(2)
                continue

            async with get_unscoped_db() as db:
                uow = TimeScaleDBUnitOfWork(db)
                rail = await uow.rail.get_by_id(active.rail_id)

            message["data"] = {
                "rail_id": rail.rail_id,
                "name": rail.name,
                "status": rail.status.value,
                "object_name": rail.object_name,
                "fastening_type": rail.fastening_type,
                "start_time": rail.start_time.isoformat() if rail.start_time else None,
                "end_time": rail.end_time.isoformat() if rail.end_time else None,
            }
            await ws.send_text(json.dumps(message, ensure_ascii=False))
        except asyncio.CancelledError:
            break
        except Exception:
            pass
        finally:
            await asyncio.sleep(2)
