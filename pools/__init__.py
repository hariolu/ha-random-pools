# All comments in English.
from __future__ import annotations

import asyncio
import logging
from typing import Dict
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.const import Platform
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN

PLATFORMS = [Platform.SENSOR]
_LOGGER = logging.getLogger(__name__)

# Global registry of pool entities (entity_id -> object exposing async_* APIs).
# sensor_lines.py and sensor_media.py add themselves here on creation.
POOLS: Dict[str, "BasePool"] = {}


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Pools integration (YAML mode). Register services."""

    async def _gather_for(call: ServiceCall, coro_name: str) -> None:
        """Collect matching pools and await their async_* coroutines in parallel."""
        entity_ids = call.data.get("entity_id")
        targets = (
            entity_ids
            if isinstance(entity_ids, list)
            else [entity_ids] if entity_ids
            else []
        )
        # If 'all: true' or no explicit targets were provided, act on all pools
        if call.data.get("all") or not targets:
            targets = list(POOLS.keys())

        tasks = []
        for eid in targets:
            pool = POOLS.get(eid)
            if pool is None:
                continue
            coro = getattr(pool, coro_name, None)
            if coro is not None:
                tasks.append(coro())

        if tasks:
            await asyncio.gather(*tasks)

    # --- Async service handlers (must be awaited by HA) ---

    async def handle_shuffle(call: ServiceCall) -> None:
        """Shuffle/advance pool(s) and push state."""
        await _gather_for(call, "async_shuffle_and_push_state")

    async def handle_reload(call: ServiceCall) -> None:
        """Force reload pool(s) from disk and push state."""
        await _gather_for(call, "async_force_reload_and_push_state")

    async def handle_reset(call: ServiceCall) -> None:
        """Reset counters/history on pool(s) and push attributes."""
        await _gather_for(call, "async_reset_and_push_attrs")

    # Convenience aliases that behave like 'all: true'
    async def handle_shuffle_all(call: ServiceCall) -> None:
        await _gather_for(call, "async_shuffle_and_push_state")

    async def handle_reload_all(call: ServiceCall) -> None:
        await _gather_for(call, "async_force_reload_and_push_state")

    # Register services (async handlers instead of lambda-returning coroutines).
    hass.services.async_register(DOMAIN, "shuffle", handle_shuffle)
    hass.services.async_register(DOMAIN, "reload", handle_reload)
    hass.services.async_register(DOMAIN, "reset_stats", handle_reset)
    hass.services.async_register(DOMAIN, "shuffle_all", handle_shuffle_all)
    hass.services.async_register(DOMAIN, "reload_all", handle_reload_all)

    _LOGGER.debug("pools: services registered (shuffle, reload, reset_stats, *_all)")
    return True
