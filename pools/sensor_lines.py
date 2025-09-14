# All comments in English.
# Lines platform (formerly "text")
from __future__ import annotations

import logging
import os
import unicodedata
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
    CONF_LINES_DIRECTORY,
    CONF_LINES_POOLS,
    CONF_SELECTION_MODE,
    CONF_NO_REPEAT,
    CONF_FALLBACK_TEXT,
    CONF_INCLUDE,
    CONF_EXCLUDE,
    CONF_LINES_EXTS,
    CONF_MAX_LINES,
    CONF_MAX_CHARS,
    # Defaults
    DEFAULT_LINES_DIRECTORY,
    DEFAULT_SELECTION_MODE,
    DEFAULT_NO_REPEAT,
    DEFAULT_FALLBACK_TEXT,
    DEFAULT_INCLUDE,
    DEFAULT_EXCLUDE,
    DEFAULT_LINES_EXTS,
    DEFAULT_MAX_LINES,
    DEFAULT_MAX_CHARS,
    # Attrs
    ATTR_FILE,
    ATTR_LINE_COUNT,
    ATTR_TRUNCATED_LINES,
    ATTR_IGNORED_BLANK,
    ATTR_LAST_INDEX,
    ATTR_FILE_MTIME,
    ATTR_SHUFFLE_COUNT,
    ATTR_RELOAD_COUNT,
    ATTR_LAST_SHUFFLE,
    ATTR_LAST_RELOAD,
)
from . import POOLS  # global registry for bulk services
from .utils import slugify, resolve_path
from .discover import scan_files

_LOGGER = logging.getLogger(__name__)

# ───────────────────────── Schemas ─────────────────────────

POOL_SCHEMA = vol.Schema(
    {
        vol.Required("file"): cv.string,          # relative filename under lines_directory
        vol.Required("name"): cv.string,          # friendly name
        vol.Optional("unique_id"): cv.string,     # stable unique_id
        vol.Optional("entity_suffix"): cv.string, # e.g., pools_lines_hello
    }
)

PLATFORM_SCHEMA = vol.Schema(
    {
        vol.Required("platform"): vol.Equal(DOMAIN),
        vol.Optional(CONF_LINES_DIRECTORY, default=DEFAULT_LINES_DIRECTORY): cv.string,
        vol.Optional(CONF_LINES_POOLS, default=[]): vol.All(cv.ensure_list, [POOL_SCHEMA]),
        vol.Optional(CONF_SELECTION_MODE, default=DEFAULT_SELECTION_MODE): vol.In(["random", "queue"]),
        vol.Optional(CONF_NO_REPEAT, default=DEFAULT_NO_REPEAT): vol.All(int, vol.Range(min=0, max=1000)),
        vol.Optional(CONF_FALLBACK_TEXT, default=DEFAULT_FALLBACK_TEXT): cv.string,
        vol.Optional(CONF_INCLUDE, default=DEFAULT_INCLUDE): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(CONF_EXCLUDE, default=DEFAULT_EXCLUDE): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(CONF_LINES_EXTS, default=DEFAULT_LINES_EXTS): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(CONF_MAX_LINES, default=DEFAULT_MAX_LINES): vol.All(int, vol.Range(min=1, max=10000)),
        vol.Optional(CONF_MAX_CHARS, default=DEFAULT_MAX_CHARS): vol.All(int, vol.Range(min=1, max=20000)),
    }
)

# ───────────────────────── Helpers ─────────────────────────

def _derive_suffix(filename: str) -> str:
    base = os.path.splitext(os.path.basename(filename))[0]
    return f"pools_lines_{slugify(base)}"

# ───────────────────────── Setup ─────────────────────────

async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up Lines pools from YAML."""
    directory = config.get(CONF_LINES_DIRECTORY, DEFAULT_LINES_DIRECTORY)
    pools_cfg: List[dict] = list(config.get(CONF_LINES_POOLS, []))
    selection_mode: str = config.get(CONF_SELECTION_MODE, DEFAULT_SELECTION_MODE)
    no_repeat: int = config.get(CONF_NO_REPEAT, DEFAULT_NO_REPEAT)
    fallback_text: str = config.get(CONF_FALLBACK_TEXT, DEFAULT_FALLBACK_TEXT)
    includes: List[str] = config.get(CONF_INCLUDE, DEFAULT_INCLUDE)
    excludes: List[str] = config.get(CONF_EXCLUDE, DEFAULT_EXCLUDE)
    exts: List[str] = [e.lower() for e in config.get(CONF_LINES_EXTS, DEFAULT_LINES_EXTS)]
    max_lines: int = config.get(CONF_MAX_LINES, DEFAULT_MAX_LINES)
    max_chars: int = config.get(CONF_MAX_CHARS, DEFAULT_MAX_CHARS)

    # Autodiscover *.ext files if none specified (async-safe via executor).
    if not pools_cfg:
        discovered = await scan_files(hass, directory, exts, includes, excludes)
        for entry in discovered:
            suffix = _derive_suffix(entry)
            pools_cfg.append(
                {
                    "file": entry,
                    "name": f"Pools Lines {os.path.splitext(entry)[0].replace('_',' ')}",
                    "entity_suffix": suffix,
                    "unique_id": suffix,
                }
            )
        _LOGGER.debug(
            "pools(lines): auto-discovered %d files in %s",
            len(discovered),
            resolve_path(hass, directory),
        )

    entities: List[SensorEntity] = []
    for item in pools_cfg[:255]:
        try:
            file = item["file"]
            name = item["name"]
            unique_id = item.get("unique_id")
            suffix = item.get("entity_suffix") or _derive_suffix(file)
            suggested_entity_id = f"sensor.{suffix}"
            entities.append(
                LinesSensor(
                    hass=hass,
                    directory=directory,
                    filename=file,
                    name=name,
                    unique_id=unique_id,
                    suggested_entity_id=suggested_entity_id,
                    selection_mode=selection_mode,
                    no_repeat=no_repeat,
                    fallback_text=fallback_text,
                    max_lines=max_lines,
                    max_chars=max_chars,
                )
            )
        except Exception as e:
            _LOGGER.exception("pools(lines): failed to init %s: %s", item, e)

    if entities:
        add_entities(entities, update_before_add=True)

# ───────────────────────── Entity ─────────────────────────

class LinesSensor(SensorEntity):
    """A sensor that exposes one line from a text file, according to selection rules."""

    _attr_should_poll = False

    def __init__(
        self,
        hass: HomeAssistant,
        directory: str,
        filename: str,
        name: str,
        unique_id: Optional[str],
        suggested_entity_id: str,
        selection_mode: str,
        no_repeat: int,
        fallback_text: str,
        max_lines: int,
        max_chars: int,
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
        self.file_path = resolve_path(hass, os.path.join(directory, filename))
        self.selection_mode = selection_mode
        self.no_repeat = max(0, int(no_repeat))
        self.history: deque[int] = deque(maxlen=self.no_repeat)  # indices history for anti-repeat
        self.fallback_text = fallback_text
        self.max_lines = max_lines
        self.max_chars = max_chars

        # Pool state
        self.lines: List[str] = []
        self.truncated = 0
        self.ignored_blank = 0
        self.last_index: Optional[int] = None
        self.file_mtime: Optional[float] = None

        # Register into global service registry
        POOLS[self.entity_id] = self

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

    # -------------- File I/O (executor) --------------

    def _load_file(self) -> None:
        """Read & parse the file, applying limits and normalization."""
        self.lines = []
        self.truncated = 0
        self.ignored_blank = 0

        if not os.path.exists(self.file_path):
            self.file_mtime = None
            return

        try:
            st = os.stat(self.file_path)
            self.file_mtime = st.st_mtime

            with open(self.file_path, "r", encoding="utf-8", errors="ignore") as f:
                for raw in f:
                    if len(self.lines) >= self.max_lines:
                        break
                    # Strip BOM, normalize, trim whitespace and CR/LF
                    line = raw.replace("\ufeff", "").rstrip("\r\n")
                    line = unicodedata.normalize("NFC", line).strip()
                    if not line:
                        self.ignored_blank += 1
                        continue
                    if len(line) > self.max_chars:
                        line = line[: self.max_chars]
                        self.truncated += 1
                    self.lines.append(line)

        except Exception as e:
            _LOGGER.exception("pools(lines): read error %s: %s", self.file_path, e)

    def _maybe_reload(self) -> None:
        """Reload if mtime changed; if file missing, graceful load."""
        try:
            st = os.stat(self.file_path)
            if self.file_mtime is None or st.st_mtime != self.file_mtime:
                self._load_file()
        except FileNotFoundError:
            self._load_file()

    # -------------- Selection --------------

    def _pick_next(self) -> str:
        """Pick next line according to selection_mode & no_repeat."""
        import random

        if not self.lines:
            return self.fallback_text or ""

        if self.selection_mode == "queue":
            # Walk sequentially; wrap around.
            if self.last_index is None:
                self.last_index = -1
            idx = (self.last_index + 1) % len(self.lines)
        else:
            # Random with anti-repeat history.
            choices = list(range(len(self.lines)))
            if self.no_repeat > 0 and self.history:
                for h in set(self.history):
                    # Avoid duplicates, but keep at least 1 option.
                    if h in choices and len(choices) > 1:
                        choices.remove(h)
            idx = random.choice(choices) if choices else 0

        # Track history & last index
        self.last_index = idx
        if self.no_repeat > 0:
            self.history.append(idx)

        return self.lines[idx]

    # -------------- Service APIs (used by __init__.py) --------------

    async def async_shuffle_and_push_state(self):
        """Shuffle (or queue step) and push state."""
        await self.hass.async_add_executor_job(self._maybe_reload)
        value = self._pick_next()
        from datetime import datetime
        self._attrs[ATTR_SHUFFLE_COUNT] = int(self._attrs.get(ATTR_SHUFFLE_COUNT, 0)) + 1
        self._attrs[ATTR_LAST_SHUFFLE] = datetime.now().isoformat(timespec="seconds")
        self._update_and_push(value)

    async def async_force_reload_and_push_state(self):
        """Force reload from disk then pick and push state."""
        await self.hass.async_add_executor_job(self._load_file)
        value = self._pick_next()
        from datetime import datetime
        self._attrs[ATTR_RELOAD_COUNT] = int(self._attrs.get(ATTR_RELOAD_COUNT, 0)) + 1
        self._attrs[ATTR_LAST_RELOAD] = datetime.now().isoformat(timespec="seconds")
        self._update_and_push(value)

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

    def _update_and_push(self, value: str) -> None:
        """Update state & attributes; push to HA."""
        mtime_iso: Optional[str] = None
        try:
            if self.file_mtime:
                from datetime import datetime
                mtime_iso = datetime.fromtimestamp(self.file_mtime).isoformat()
        except Exception:
            mtime_iso = None

        self._state = value
        self._attrs.update(
            {
                ATTR_FILE: self.file_path,
                ATTR_LINE_COUNT: len(self.lines),
                ATTR_TRUNCATED_LINES: self.truncated,
                ATTR_IGNORED_BLANK: self.ignored_blank,
                ATTR_LAST_INDEX: self.last_index,
                ATTR_FILE_MTIME: mtime_iso,
            }
        )
        self.async_write_ha_state()
