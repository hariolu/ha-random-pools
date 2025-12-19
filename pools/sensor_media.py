# All comments in English.
# sensor_media.py — "Media" pools (formerly "sounds")
# Features:
# - selection_mode: random | queue
# - no_repeat: N (history-based anti-repeat for random)
# - fallback_url
# - include/exclude (glob)
# - media_extensions (any playable by your client, e.g., VLC)
# - serve_from: component | www | media  → builds URLs accordingly
# - Autodiscovery when media_pools not specified (async-safe via executor)
# - Reduced logging noise on expected conditions

from __future__ import annotations

import logging
import os
from collections import deque
from typing import Any, Dict, List, Optional

import voluptuous as vol
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import (
    DOMAIN,
    # Config keys
    CONF_MEDIA_DIRECTORY,
    CONF_MEDIA_POOLS,
    CONF_SELECTION_MODE,
    CONF_NO_REPEAT,
    CONF_FALLBACK_URL,
    CONF_SERVE_FROM,
    CONF_INCLUDE,
    CONF_EXCLUDE,
    CONF_MEDIA_EXTS,
    # Defaults
    DEFAULT_MEDIA_DIRECTORY,
    DEFAULT_SELECTION_MODE,
    DEFAULT_NO_REPEAT,
    DEFAULT_FALLBACK_URL,
    DEFAULT_SERVE_FROM,
    DEFAULT_INCLUDE,
    DEFAULT_EXCLUDE,
    DEFAULT_MEDIA_EXTS,
    # Attrs
    ATTR_DIR,
    ATTR_FILE_COUNT,
    ATTR_LAST_INDEX,
    ATTR_LAST_FILE,
    ATTR_RELATIVE_URL,
    ATTR_ABSOLUTE_URL,
    ATTR_DIR_MTIME,
    ATTR_SHUFFLE_COUNT,
    ATTR_RELOAD_COUNT,
    ATTR_LAST_SHUFFLE,
    ATTR_LAST_RELOAD,
    ATTR_FILE,
)

# Global registry imported from __init__.py (keys are entity_id → object with async_* APIs)
from . import POOLS  # noqa: F401  (import used at runtime)

# Async-safe discovery helpers (use executor under the hood)
from .discover import scan_media_folders

_LOGGER = logging.getLogger(__name__)


# ───────────────────────── Schemas ─────────────────────────

POOL_SCHEMA = vol.Schema(
    {
        vol.Required("folder"): cv.string,          # subfolder under media_directory
        vol.Required("name"): cv.string,            # friendly name
        vol.Optional("unique_id"): cv.string,       # stable unique_id
        vol.Optional("entity_suffix"): cv.string,   # e.g., pools_media_alerts
    }
)

PLATFORM_SCHEMA = vol.Schema(
    {
        vol.Required("platform"): vol.Equal(DOMAIN),
        vol.Optional(CONF_MEDIA_DIRECTORY, default=DEFAULT_MEDIA_DIRECTORY): cv.string,
        vol.Optional(CONF_MEDIA_POOLS, default=[]): vol.All(cv.ensure_list, [POOL_SCHEMA]),
        vol.Optional(CONF_SELECTION_MODE, default=DEFAULT_SELECTION_MODE): vol.In(["random", "queue"]),
        vol.Optional(CONF_NO_REPEAT, default=DEFAULT_NO_REPEAT): vol.All(int, vol.Range(min=0, max=1000)),
        vol.Optional(CONF_FALLBACK_URL, default=DEFAULT_FALLBACK_URL): cv.string,
        vol.Optional(CONF_SERVE_FROM, default=DEFAULT_SERVE_FROM): vol.In(["component", "www", "media"]),
        vol.Optional(CONF_INCLUDE, default=DEFAULT_INCLUDE): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(CONF_EXCLUDE, default=DEFAULT_EXCLUDE): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(CONF_MEDIA_EXTS, default=DEFAULT_MEDIA_EXTS): vol.All(cv.ensure_list, [cv.string]),
    }
)


# ───────────────────────── Utilities ─────────────────────────

def _slugify(s: str) -> str:
    s = s.lower()
    out: List[str] = []
    prev_us = False
    for ch in s:
        if ch.isalnum():
            out.append(ch)
            prev_us = False
        else:
            if not prev_us:
                out.append("_")
                prev_us = True
    return "".join(out).strip("_")


def _derive_suffix(folder: str) -> str:
    base = _slugify(os.path.basename(folder))
    return f"pools_media_{base}"


def _resolve_hass_path(hass: HomeAssistant, rel: str) -> str:
    if rel.startswith("/"):
        return rel
    return hass.config.path(rel)


def _match_patterns(name: str, includes: List[str], excludes: List[str]) -> bool:
    from fnmatch import fnmatch
    ok = True if not includes else any(fnmatch(name, pat) for pat in includes)
    if includes and not ok:
        return False
    if any(fnmatch(name, pat) for pat in excludes):
        return False
    return True


# ───────────────────────── Setup ─────────────────────────

async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up Media pools from YAML."""
    root = config.get(CONF_MEDIA_DIRECTORY, DEFAULT_MEDIA_DIRECTORY)
    pools_cfg: List[dict] = list(config.get(CONF_MEDIA_POOLS, []))
    selection_mode: str = config.get(CONF_SELECTION_MODE, DEFAULT_SELECTION_MODE)
    no_repeat: int = config.get(CONF_NO_REPEAT, DEFAULT_NO_REPEAT)
    fallback_url: str = config.get(CONF_FALLBACK_URL, DEFAULT_FALLBACK_URL)
    serve_from: str = config.get(CONF_SERVE_FROM, DEFAULT_SERVE_FROM)
    includes: List[str] = config.get(CONF_INCLUDE, DEFAULT_INCLUDE)
    excludes: List[str] = config.get(CONF_EXCLUDE, DEFAULT_EXCLUDE)
    exts: List[str] = [e.lower() for e in config.get(CONF_MEDIA_EXTS, DEFAULT_MEDIA_EXTS)]

    # Autodiscover subfolders that contain at least one matching media file (async-safe).
    if not pools_cfg:
        found = await scan_media_folders(hass, root, exts, includes, excludes)
        for entry in found:
            suffix = _derive_suffix(entry)
            pools_cfg.append(
                {
                    "folder": entry,
                    "name": f"Pools Media {entry.replace('_',' ')}",
                    "entity_suffix": suffix,
                    "unique_id": suffix,
                }
            )
        if found:
            _LOGGER.debug(
                "pools(media): auto-discovered %d folders in %s",
                len(found),
                _resolve_hass_path(hass, root),
            )
        else:
            _LOGGER.debug("pools(media): no matching media in %s", _resolve_hass_path(hass, root))

    entities: List[SensorEntity] = []
    for item in pools_cfg[:255]:
        try:
            folder = item["folder"]
            name = item["name"]
            unique_id = item.get("unique_id")
            suffix = item.get("entity_suffix") or _derive_suffix(folder)
            suggested_entity_id = f"sensor.{suffix}"
            entities.append(
                MediaSensor(
                    hass=hass,
                    root=root,
                    folder=folder,
                    name=name,
                    unique_id=unique_id,
                    suggested_entity_id=suggested_entity_id,
                    selection_mode=selection_mode,
                    no_repeat=no_repeat,
                    fallback_url=fallback_url,
                    serve_from=serve_from,
                    includes=includes,
                    excludes=excludes,
                    exts=exts,
                )
            )
        except Exception as e:
            _LOGGER.exception("pools(media): failed to init %s: %s", item, e)

    if entities:
        add_entities(entities, update_before_add=True)


# ───────────────────────── Entity ─────────────────────────

class MediaSensor(SensorEntity):
    """A sensor that exposes one media URL or file path, according to selection rules."""

    _attr_should_poll = False

    def __init__(
        self,
        hass: HomeAssistant,
        root: str,
        folder: str,
        name: str,
        unique_id: Optional[str],
        suggested_entity_id: str,
        selection_mode: str,
        no_repeat: int,
        fallback_url: str,
        serve_from: str,
        includes: List[str],
        excludes: List[str],
        exts: List[str],
    ) -> None:
        self.hass = hass
        self._attr_name = name
        self._unique_id = unique_id or f"{DOMAIN}:{suggested_entity_id}"
        self.entity_id = suggested_entity_id

        # State & attrs
        self._state: str = ""
        self._attrs: Dict[str, Any] = {
            ATTR_SHUFFLE_COUNT: 0,
            ATTR_RELOAD_COUNT: 0,
            ATTR_LAST_SHUFFLE: None,
            ATTR_LAST_RELOAD: None,
        }

        # Pool config
        self.dir_path = _resolve_hass_path(hass, os.path.join(root, folder))
        self.root = root
        self.folder = folder
        self.selection_mode = selection_mode
        self.no_repeat = max(0, int(no_repeat))
        self.history: deque[int] = deque(maxlen=self.no_repeat)  # indices history for anti-repeat
        self.fallback_url = fallback_url
        self.serve_from = serve_from
        self.includes = includes
        self.excludes = excludes
        self.exts = exts

        # Pool state
        self.files: List[str] = []
        self.last_index: Optional[int] = None
        self.last_file: Optional[str] = None
        self.dir_mtime: Optional[float] = None

        # Register into global service registry
        from . import POOLS as _REG
        _REG[self.entity_id] = self

    # -------------- HA properties --------------

    @property
    def unique_id(self) -> str | None:
        return self._unique_id

    @property
    def native_value(self) -> str | None:
        return self._state

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        return self._attrs

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, "pools")},
            name="Random Pools",
            manufacturer="Open Community",
            model="Lines & Media Pools",
        )

    # -------------- HA lifecycle --------------

    async def async_added_to_hass(self) -> None:
        await self.async_force_reload_and_push_state()

    # -------------- Scan & reload --------------

    def _scan_dir(self) -> None:
        """(Executor) Scan media folder with filters and extensions."""
        self.files = []
        self.last_index = None
        self.last_file = None
        self.dir_mtime = None

        if not os.path.isdir(self.dir_path):
            _LOGGER.debug("pools(media): folder not found: %s", self.dir_path)
            return

        try:
            latest = 0.0
            for name in sorted(os.listdir(self.dir_path)):
                low = name.lower()
                if not any(low.endswith(ext) for ext in self.exts):
                    continue
                if not _match_patterns(name, self.includes, self.excludes):
                    continue
                full = os.path.join(self.dir_path, name)
                try:
                    st = os.stat(full)
                    latest = max(latest, st.st_mtime)
                    self.files.append(name)
                except FileNotFoundError:
                    continue
            self.dir_mtime = latest if latest > 0 else None
        except Exception as e:
            _LOGGER.exception("pools(media): scan error %s: %s", self.dir_path, e)

    def _maybe_reload(self) -> None:
        """(Executor) Rescan; folders are small and cheap to read."""
        self._scan_dir()

    # -------------- URL building --------------

    def _build_url(self, basename: Optional[str]) -> str:
        """Build a URL depending on serve_from. Empty if not web-served."""
        if not basename:
            return ""

        # Serve from /local when using /config/www
        if self.serve_from == "www" or (self.serve_from == "component" and self.root.startswith("www/")):
            sub = f"{self.root.split('www/', 1)[-1].strip('/')}/{self.folder}"
            return f"/local/{sub}/{basename}"

        # Serve as media-source when using /config/media
        if self.serve_from == "media" or (self.serve_from == "component" and self.root.startswith("media/")):
            sub_media = f"{self.root.split('media/', 1)[-1].strip('/')}/{self.folder}"
            return f"media-source://media_source/local/{sub_media}/{basename}"

        # component: not web-served → return empty; absolute path exposed in attrs
        return ""

    # -------------- Selection --------------

    def _pick_next(self) -> str:
        """Pick next media according to selection_mode & no_repeat."""
        import random

        if not self.files:
            return self.fallback_url or ""

        if self.selection_mode == "queue":
            if self.last_index is None:
                self.last_index = -1
            idx = (self.last_index + 1) % len(self.files)
        else:
            choices = list(range(len(self.files)))
            if self.no_repeat > 0 and self.history:
                for h in set(self.history):
                    if h in choices and len(choices) > 1:
                        choices.remove(h)
            idx = random.choice(choices) if choices else 0

        self.last_index = idx
        if self.no_repeat > 0:
            self.history.append(idx)
        self.last_file = self.files[idx]
        return self._build_url(self.last_file)

    # -------------- Service APIs (used by __init__.py) --------------

    async def async_shuffle_and_push_state(self):
        """Shuffle (or queue step) and push state."""
        # Run directory scan in executor to avoid blocking the event loop
        await self.hass.async_add_executor_job(self._maybe_reload)
        url = self._pick_next()
        from datetime import datetime
        self._attrs[ATTR_SHUFFLE_COUNT] = int(self._attrs.get(ATTR_SHUFFLE_COUNT, 0)) + 1
        self._attrs[ATTR_LAST_SHUFFLE] = datetime.now().isoformat(timespec="seconds")
        self._update_and_push(url)

    async def async_force_reload_and_push_state(self):
        """Force rescan then pick and push state."""
        # Run directory scan in executor to avoid blocking the event loop
        await self.hass.async_add_executor_job(self._scan_dir)
        url = self._pick_next()
        from datetime import datetime
        self._attrs[ATTR_RELOAD_COUNT] = int(self._attrs.get(ATTR_RELOAD_COUNT, 0)) + 1
        self._attrs[ATTR_LAST_RELOAD] = datetime.now().isoformat(timespec="seconds")
        self._update_and_push(url)

    async def async_reset_and_push_attrs(self):
        """Reset counters and history; keep current state value."""
        self.history.clear()
        self._attrs.update(
            {
                ATTR_SHUFFLE_COUNT: 0,
                ATTR_RELOAD_COUNT: 0,
                ATTR_LAST_SHUFFLE: None,
                ATTR_LAST_RELOAD: None,
            }
        )
        self.async_write_ha_state()

    # -------------- State push --------------

    def _update_and_push(self, url: str) -> None:
        """Update state & attributes; push to HA.

        NOTE:
        - State is kept "clean" (filename only) to avoid hardcoded base URLs.
        - Use ATTR_RELATIVE_URL to build the full URL in automations.
        """
        abs_file = os.path.join(self.dir_path, self.last_file) if self.last_file else None
        rel_url = url or None

        # Keep sensor state minimal: filename only (no /local/... in state)
        self._state = self.last_file or ""

        self._attrs.update(
            {
                ATTR_DIR: self.dir_path,
                ATTR_FILE_COUNT: len(self.files),
                ATTR_LAST_INDEX: self.last_index,
                ATTR_LAST_FILE: self.last_file,
                ATTR_RELATIVE_URL: rel_url,   # /local/... or media-source://... or ''
                ATTR_ABSOLUTE_URL: abs_file,  # /config/www/... absolute path
                ATTR_FILE: abs_file,          # alias
            }
        )
        self.async_write_ha_state()
