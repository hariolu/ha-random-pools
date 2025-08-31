# All comments in English.
from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.const import Platform
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN

PLATFORMS = [Platform.SENSOR]
_LOGGER = logging.getLogger(__name__)

# Global registry so services can reach pools by entity_id
POOLS: Dict[str, "BasePool"] = {}

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register services shared by both text and sound pools."""

    async def _svc_shuffle(call: ServiceCall) -> None:
        entity_ids = call.data.get("entity_id")
        targets = entity_ids if isinstance(entity_ids, list) else [entity_ids]
        if not targets or targets == [None]:
            _LOGGER.warning("pools.shuffle called without entity_id")
            return
        tasks = []
        for ent_id in targets:
            pool = POOLS.get(ent_id)
            if pool:
                tasks.append(pool.async_shuffle_and_push_state())
            else:
                _LOGGER.warning("No pool bound to entity_id: %s", ent_id)
        if tasks:
            await asyncio.gather(*tasks)

    async def _svc_reload(call: ServiceCall) -> None:
        entity_ids = call.data.get("entity_id")
        targets = entity_ids if isinstance(entity_ids, list) else [entity_ids]
        tasks = []
        for ent_id in targets:
            pool = POOLS.get(ent_id)
            if pool:
                tasks.append(pool.async_force_reload_and_push_state())
            else:
                _LOGGER.warning("No pool bound to entity_id: %s", ent_id)
        if tasks:
            await asyncio.gather(*tasks)

    async def _svc_reset_stats(call: ServiceCall) -> None:
        entity_ids = call.data.get("entity_id")
        targets = entity_ids if isinstance(entity_ids, list) else [entity_ids]
        for ent_id in (targets or []):
            pool = POOLS.get(ent_id)
            if pool:
                pool.reset_stats()
                # push attrs update (state unchanged)
                pool.entity._update_from_pool(pool.entity.native_value or "")
                pool.entity.async_write_ha_state()

    hass.services.async_register(DOMAIN, "shuffle", _svc_shuffle)
    hass.services.async_register(DOMAIN, "reload", _svc_reload)
    hass.services.async_register(DOMAIN, "reset_stats", _svc_reset_stats)
    return True
