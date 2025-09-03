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

# Global registry of pool entities (entity_id -> object exposing async_* APIs)
POOLS: Dict[str, "BasePool"] = {}

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async def _gather_for(call: ServiceCall, coro: str):
        entity_ids = call.data.get("entity_id")
        targets = entity_ids if isinstance(entity_ids, list) else [entity_ids] if entity_ids else []
        if call.data.get("all") or not targets:
            targets = list(POOLS.keys())

        tasks = []
        for eid in targets:
            pool = POOLS.get(eid)
            if pool and hasattr(pool, coro):
                tasks.append(getattr(pool, coro)())
        if tasks:
            await asyncio.gather(*tasks)

    hass.services.async_register(DOMAIN, "shuffle", lambda c: _gather_for(c, "async_shuffle_and_push_state"))
    hass.services.async_register(DOMAIN, "reload", lambda c: _gather_for(c, "async_force_reload_and_push_state"))
    hass.services.async_register(DOMAIN, "reset_stats", lambda c: _gather_for(c, "async_reset_and_push_attrs"))
    hass.services.async_register(DOMAIN, "shuffle_all", lambda c: _gather_for(c, "async_shuffle_and_push_state"))
    hass.services.async_register(DOMAIN, "reload_all", lambda c: _gather_for(c, "async_force_reload_and_push_state"))
    return True
