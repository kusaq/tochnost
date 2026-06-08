import json
import logging

from api.v1.sensor.state import SENSOR_STATE
from infra.redis.redis_api import RedisAPI

logger = logging.getLogger(__name__)


async def detach_rail_from_sensor_state(rail_id: int, redis: RedisAPI) -> None:
    """Clears SENSOR_STATE active/waiting/post2 fifo for the given rail and publishes empty stages."""
    state = SENSOR_STATE
    post2 = state.post2_tracker()

    active = state.get_active_rail()
    if active is not None and active.rail_id == rail_id:
        state.clear_active()
        state.reset_resistance_stats()
        state.reset_temperature_stats()
        state.reset_gauge_stats()
        state.reset_total_screws()
        state.clear_screw_session()
        state.reset_laser_counts()
        state.reset_tightening_cycle()

    state.pop_waiting_rail(rail_id)
    post2.remove_from_fifo(rail_id)
    if post2.rail_at_post2 == rail_id:
        post2.rail_at_post2 = None
    state.clear_rail_screw_count(rail_id)

    try:
        await redis.publish(
            "dashboard:stages",
            json.dumps({}, ensure_ascii=False),
        )
    except Exception:
        logger.exception("Failed to publish dashboard:stages after detaching rail %s", rail_id)
