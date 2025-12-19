# All comments in English.
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Tuple

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN

PLATFORMS = [Platform.SENSOR]
_LOGGER = logging.getLogger(__name__)

# Global registry of pool entities (entity_id -> object exposing async_* APIs).
# sensor_lines.py and sensor_media.py add themselves here on creation.
POOLS: Dict[str, "BasePool"] = {}


def _parse_service(service_str: str) -> Tuple[str, str]:
    """Parse 'domain.service' into (domain, service)."""
    if not service_str:
        return ("notify", "mobile_app_pixel_5")
    if "." in service_str:
        d, s = service_str.split(".", 1)
        return (d.strip(), s.strip())
    # If user passes only service name, assume notify.*
    return ("notify", service_str.strip())


def _best_base_url(hass: HomeAssistant) -> str:
    """Pick the best available base URL from HA config."""
    try:
        if hass.config.internal_url:
            return str(hass.config.internal_url).rstrip("/")
        if hass.config.external_url:
            return str(hass.config.external_url).rstrip("/")
    except Exception:
        return ""
    return ""


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Pools integration (YAML mode). Register services."""

    async def _gather_for(call: ServiceCall, coro_name: str) -> None:
        """Collect matching pools and await their async_* coroutines in parallel."""
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

    # --- Service handlers ---

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
        # Reuse the same gather logic; forcing 'all' makes it explicit.
        call.data.setdefault("all", True)
        await _gather_for(call, "async_shuffle_and_push_state")

    async def handle_reload_all(call: ServiceCall) -> None:
        """Reload all pools from disk and push state (compat shim)."""
        call.data.setdefault("all", True)
        await _gather_for(call, "async_force_reload_and_push_state")

    async def handle_play_vlc(call: ServiceCall) -> None:
        """Shuffle a media pool, build URL, and launch VLC via notify command_activity."""
        entity_id = call.data.get("entity_id")
        if not entity_id:
            return

        pool = POOLS.get(entity_id)
        if pool is None:
            _LOGGER.warning("pools.play_vlc: entity not found: %s", entity_id)
            return

        # Optional shuffle before playback
        if call.data.get("shuffle", True):
            coro = getattr(pool, "async_shuffle_and_push_state", None)
            if coro is not None:
                await coro()

        # Read relative_url from entity attributes
        st = hass.states.get(entity_id)
        rel = ""
        if st:
            rel = str(st.attributes.get("relative_url") or "")

        # Build final URL
        base_url = str(call.data.get("base_url") or "").rstrip("/")
        if not base_url:
            base_url = _best_base_url(hass)

        # If rel is already absolute (http/https/media-source), keep as-is
        url = ""
        if rel.startswith("http://") or rel.startswith("https://") or rel.startswith("media-source://"):
            url = rel
        elif rel.startswith("/"):
            url = f"{base_url}{rel}" if base_url else ""
        else:
            url = ""

        if not url:
            _LOGGER.warning(
                "pools.play_vlc: empty url (entity=%s base_url='%s' rel='%s')",
                entity_id,
                base_url,
                rel,
            )
            return

        # Optional: VLC scheme wrapper (some VLC builds accept 'vlc://http://...')
        if call.data.get("vlc_scheme", False):
            url = f"vlc://{url}"

        notify_service = str(call.data.get("notify_service") or "notify.mobile_app_pixel_5")
        domain, service = _parse_service(notify_service)

        intent_action = str(call.data.get("intent_action") or "android.intent.action.VIEW")
        intent_package = str(call.data.get("intent_package_name") or "org.videolan.vlc")

        payload: Dict[str, Any] = {
            "message": "command_activity",
            "data": {
                "intent_action": intent_action,
                "intent_package_name": intent_package,
                "intent_uri": url,
            },
        }

        await hass.services.async_call(domain, service, payload, blocking=False)

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

    # Register services
    hass.services.async_register(DOMAIN, "shuffle", handle_shuffle)
    hass.services.async_register(DOMAIN, "reload", handle_reload)
    hass.services.async_register(DOMAIN, "reset_stats", handle_reset)
    hass.services.async_register(DOMAIN, "shuffle_all", handle_shuffle_all)
    hass.services.async_register(DOMAIN, "reload_all", handle_reload_all)

    hass.services.async_register(DOMAIN, "play_vlc", handle_play_vlc)
    hass.services.async_register(DOMAIN, "get_line", handle_get_line, supports_response=True)

    _LOGGER.debug("pools: services registered (shuffle, reload, reset_stats, shuffle_all, reload_all, play_vlc, get_line)")
    return True
