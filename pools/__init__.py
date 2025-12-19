# All comments in English.
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN

PLATFORMS = [Platform.SENSOR]
_LOGGER = logging.getLogger(__name__)

# Global registry of pools (entity_id -> pool object).
# Pool objects are expected to expose async_* methods used by services below.
POOLS: Dict[str, Any] = {}


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Pools integration and register services."""

    async def _gather_for(call: ServiceCall, coro_name: str) -> None:
        """Collect matching pools and await their async_* coroutines in parallel.

        Accepts:
        - entity_id: string or list of strings
        - all: bool (if true, ignore entity_id and apply to all pools)
        """
        entity_ids = call.data.get("entity_id")
        targets = entity_ids if isinstance(entity_ids, list) else ([entity_ids] if entity_ids else [])

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

    # --- Service handlers (core pool ops) ---

    async def handle_shuffle(call: ServiceCall) -> None:
        """Shuffle/advance pool(s) and push state."""
        await _gather_for(call, "async_shuffle_and_push_state")

    async def handle_reload(call: ServiceCall) -> None:
        """Force reload pool(s) from disk and push state."""
        await _gather_for(call, "async_force_reload_and_push_state")

    async def handle_reset(call: ServiceCall) -> None:
        """Reset counters/history on pool(s) and push attributes."""
        await _gather_for(call, "async_reset_and_push_attrs")

    async def handle_shuffle_all(call: ServiceCall) -> None:
        """Shuffle all pools and push state (compat shim)."""
        # Explicitly set call.data['all'] so _gather_for applies to all pools.
        call.data.setdefault("all", True)
        await _gather_for(call, "async_shuffle_and_push_state")

    async def handle_reload_all(call: ServiceCall) -> None:
        """Reload all pools from disk and push state (compat shim)."""
        call.data.setdefault("all", True)
        await _gather_for(call, "async_force_reload_and_push_state")

    # --- Response services (data-only; no playback logic here) ---

    async def handle_get_line(call: ServiceCall) -> Dict[str, Any]:
        """Return current line for a lines pool (optionally shuffle first)."""
        entity_id = call.data.get("entity_id")
        if not entity_id:
            return {"ok": False, "error": "missing entity_id"}

        pool = POOLS.get(entity_id)
        if pool is None:
            return {"ok": False, "error": f"entity not found: {entity_id}"}

        if call.data.get("shuffle", True):
            coro = getattr(pool, "async_shuffle_and_push_state", None)
            if coro is not None:
                await coro()

        st = hass.states.get(entity_id)
        return {
            "ok": True,
            "entity_id": entity_id,
            "value": st.state if st else "",
            "attributes": dict(st.attributes) if st else {},
        }

    async def handle_get_media(call: ServiceCall) -> Dict[str, Any]:
        """Return current selection for a media pool (optionally shuffle first).

        Keeps this service playback-agnostic. Consumers can use:
        - filename (state)
        - attributes.relative_url (recommended)
        - attributes.absolute_url / attributes.file (optional)
        """
        entity_id = call.data.get("entity_id")
        if not entity_id:
            return {"ok": False, "error": "missing entity_id"}

        pool = POOLS.get(entity_id)
        if pool is None:
            return {"ok": False, "error": f"entity not found: {entity_id}"}

        if call.data.get("shuffle", True):
            coro = getattr(pool, "async_shuffle_and_push_state", None)
            if coro is not None:
                await coro()

        st = hass.states.get(entity_id)
        attrs = dict(st.attributes) if st else {}

        # Provide common fields explicitly for convenience
        rel = str(attrs.get("relative_url") or "")
        abs_path = str(attrs.get("absolute_url") or attrs.get("file") or "")

        return {
            "ok": True,
            "entity_id": entity_id,
            "filename": st.state if st else "",
            "relative_url": rel,
            "absolute_path": abs_path,
            "attributes": attrs,
        }

    # Register services
    hass.services.async_register(DOMAIN, "shuffle", handle_shuffle)
    hass.services.async_register(DOMAIN, "reload", handle_reload)
    hass.services.async_register(DOMAIN, "reset_stats", handle_reset)

    # Back-compat helpers used by your existing scripts
    hass.services.async_register(DOMAIN, "shuffle_all", handle_shuffle_all)
    hass.services.async_register(DOMAIN, "reload_all", handle_reload_all)

    # Data-only response services
    hass.services.async_register(DOMAIN, "get_line", handle_get_line, supports_response=True)
    hass.services.async_register(DOMAIN, "get_media", handle_get_media, supports_response=True)

    _LOGGER.debug(
        "pools: services registered (shuffle, reload, reset_stats, shuffle_all, reload_all, get_line, get_media)"
    )
    return True
