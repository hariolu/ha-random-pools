# All comments in English.
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional, List

import voluptuous as vol
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import (
    DOMAIN,
    # Text pools
    CONF_DIRECTORY,
    CONF_POOLS,
    DEFAULT_DIRECTORY,
    # Sound pools
    CONF_SOUNDS_DIRECTORY,
    CONF_SOUND_POOLS,
    DEFAULT_SOUNDS_DIRECTORY,
    # URL mode
    CONF_URL_MODE,
    DEFAULT_URL_MODE,
    # Limits
    MAX_LINES,
    MAX_CHARS,
    # Attrs
    ATTR_FILE, ATTR_LINE_COUNT, ATTR_TRUNCATED_LINES, ATTR_IGNORED_BLANK,
    ATTR_LAST_INDEX, ATTR_FILE_MTIME, ATTR_DIR, ATTR_FILE_COUNT, ATTR_LAST_FILE,
    ATTR_RELATIVE_URL, ATTR_DIR_MTIME, ATTR_SHUFFLE_COUNT, ATTR_RELOAD_COUNT,
    ATTR_LAST_SHUFFLE, ATTR_LAST_RELOAD,
)
from . import POOLS  # shared registry for services

_LOGGER = logging.getLogger(__name__)

# ----- Schemas -----

POOL_SCHEMA = vol.Schema(
    {
        vol.Required("file"): cv.string,   # e.g. startup.txt
        vol.Required("name"): cv.string,   # Friendly name
        vol.Optional("unique_id"): cv.string,
        vol.Optional("entity_suffix"): cv.string,  # e.g. pools_text_startup
    }
)

SOUND_POOL_SCHEMA = vol.Schema(
    {
        vol.Required("folder"): cv.string,  # e.g. alarm -> folder under sounds root
        vol.Required("name"): cv.string,    # Friendly name
        vol.Optional("unique_id"): cv.string,
        vol.Optional("entity_suffix"): cv.string,  # e.g. pools_sound_alarm
    }
)

PLATFORM_SCHEMA = vol.Schema(
    {
        vol.Required("platform"): vol.Equal(DOMAIN),
        # Text
        vol.Optional(CONF_DIRECTORY, default=DEFAULT_DIRECTORY): cv.string,
        vol.Optional(CONF_POOLS, default=[]): vol.All(cv.ensure_list, [POOL_SCHEMA]),
        # Sounds
        vol.Optional(CONF_SOUNDS_DIRECTORY, default=DEFAULT_SOUNDS_DIRECTORY): cv.string,
        vol.Optional(CONF_SOUND_POOLS, default=[]): vol.All(cv.ensure_list, [SOUND_POOL_SCHEMA]),
        # URL mode
        vol.Optional(CONF_URL_MODE, default=DEFAULT_URL_MODE): vol.In(["auto","local","media","none"]),
    }
)

# -------------------------------------------------------------------
# Blocking I/O helpers — offloaded to the executor from async context.
# -------------------------------------------------------------------

def _scan_txt_names_sync(path: str) -> List[str]:
    if not os.path.isdir(path):
        return []
    try:
        return sorted(
            e.name for e in os.scandir(path)
            if e.is_file() and e.name.lower().endswith(".txt")
        )
    except Exception:
        return []

def _scan_sound_dirs_sync(root: str) -> List[str]:
    if not os.path.isdir(root):
        return []
    pools: List[str] = []
    try:
        for e in os.scandir(root):
            if not e.is_dir():
                continue
            try:
                has_mp3 = any(
                    f.is_file() and f.name.lower().endswith(".mp3")
                    for f in os.scandir(e.path)
                )
            except FileNotFoundError:
                has_mp3 = False
            if has_mp3:
                pools.append(e.name)
    except Exception:
        return []
    return sorted(pools)

async def _async_scan_txt_names(hass: HomeAssistant, path: str) -> List[str]:
    return await hass.async_add_executor_job(_scan_txt_names_sync, path)

async def _async_scan_sound_dirs(hass: HomeAssistant, root: str) -> List[str]:
    return await hass.async_add_executor_job(_scan_sound_dirs_sync, root)

# ----- Setup -----

async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up pools sensors from YAML."""
    directory = config.get(CONF_DIRECTORY, DEFAULT_DIRECTORY)
    pools_cfg: List[dict] = list(config.get(CONF_POOLS, []))

    sounds_root = config.get(CONF_SOUNDS_DIRECTORY, DEFAULT_SOUNDS_DIRECTORY)
    sound_pools_cfg: List[dict] = list(config.get(CONF_SOUND_POOLS, []))

    url_mode = config.get(CONF_URL_MODE, DEFAULT_URL_MODE)

    entities: list[SensorEntity] = []

    # -------- Text pools ----------
    if not pools_cfg:
        discovered = await _autodiscover_text_pools(hass, directory)
        if discovered:
            _LOGGER.info("pools: auto-discovered %d text pools in %s", len(discovered), directory)
            pools_cfg = discovered
        else:
            _LOGGER.warning("pools: no text pools discovered in %s (and none provided)", directory)

    for item in pools_cfg[:255]:
        try:
            file = item["file"]
            name = item["name"]
            unique_id = item.get("unique_id")
            suffix = item.get("entity_suffix") or _derive_text_suffix(file)
            suggested_entity_id = f"sensor.{suffix}"
            sensor = PoolsTextSensor(
                hass=hass,
                directory=directory,
                filename=file,
                name=name,
                unique_id=unique_id,
                suggested_entity_id=suggested_entity_id,
            )
            entities.append(sensor)
        except Exception as e:
            _LOGGER.exception("pools: failed to initialize text pool %s: %s", item, e)

    # -------- Sound pools ----------
    if not sound_pools_cfg:
        discovered_snd = await _autodiscover_sound_pools(hass, sounds_root)
        if discovered_snd:
            _LOGGER.info("pools: auto-discovered %d sound pools in %s", len(discovered_snd), sounds_root)
            sound_pools_cfg = discovered_snd
        else:
            _LOGGER.debug("pools: no sound pools discovered in %s", sounds_root)

    for item in sound_pools_cfg[:255]:
        try:
            folder = item["folder"]
            name = item["name"]
            unique_id = item.get("unique_id")
            suffix = item.get("entity_suffix") or _derive_sound_suffix(folder)
            suggested_entity_id = f"sensor.{suffix}"
            sensor = PoolsSoundSensor(
                hass=hass,
                sounds_root=sounds_root,
                folder=folder,
                name=name,
                unique_id=unique_id,
                suggested_entity_id=suggested_entity_id,
                url_mode=url_mode,
            )
            entities.append(sensor)
        except Exception as e:
            _LOGGER.exception("pools: failed to initialize sound pool %s: %s", item, e)

    add_entities(entities, update_before_add=True)

# ----- Helpers -----

def _slugify(s: str) -> str:
    s = s.lower()
    out = []
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

def _derive_text_suffix(filename: str) -> str:
    base = os.path.splitext(os.path.basename(filename))[0]
    return f"pools_text_{_slugify(base)}"

def _derive_sound_suffix(folder: str) -> str:
    base = _slugify(os.path.basename(folder))
    return f"pools_sound_{base}"

def _nicename_from_base(base: str) -> str:
    return base.replace("_", " ")

async def _autodiscover_text_pools(hass: HomeAssistant, directory: str) -> List[dict]:
    pools: List[dict] = []
    path = _resolve_hass_path(directory)
    if not os.path.isdir(path):
        _LOGGER.debug("pools: text dir not found: %s -> %s", directory, path)
        return pools
    try:
        names = await _async_scan_txt_names(hass, path)
        for name in names[:255]:
            base = os.path.splitext(name)[0]
            nicename = _nicename_from_base(base)
            suffix = _derive_text_suffix(name)
            pools.append({
                "file": name,
                "name": f"Pools Text {nicename}",
                "entity_suffix": suffix,
                "unique_id": suffix,
            })
    except Exception as e:
        _LOGGER.exception("pools: failed to autodiscover text pools in %s: %s", path, e)
    return pools

async def _autodiscover_sound_pools(hass: HomeAssistant, sounds_root: str) -> List[dict]:
    pools: List[dict] = []
    root = _resolve_hass_path(sounds_root)
    if not os.path.isdir(root):
        return pools
    try:
        subdirs = await _async_scan_sound_dirs(hass, root)
        for d in subdirs:
            suffix = _derive_sound_suffix(d)
            nicename = _nicename_from_base(d)
            pools.append({
                "folder": d,
                "name": f"Pools Sound {nicename}",
                "entity_suffix": suffix,
                "unique_id": suffix,
            })
            if len(pools) >= 255:
                break
    except Exception as e:
        _LOGGER.exception("pools: failed to autodiscover sound pools in %s: %s", root, e)
    return pools

def _resolve_hass_path(rel: str) -> str:
    base = os.getenv("HASS_CONFIG", "/config")
    if rel.startswith("/"):
        return rel
    return os.path.join(base, rel)

# ----- Entities -----

class _BasePoolSensor(SensorEntity):
    """Shared logic for both text and sound sensors."""
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, name: str, unique_id: Optional[str], suggested_entity_id: str):
        self.hass = hass
        self._attr_name = name
        self._unique_id = unique_id or f"{DOMAIN}:{suggested_entity_id}"
        self.entity_id = suggested_entity_id
        self._registered_key: Optional[str] = self.entity_id
        self._state: str = ""
        self._attrs: Dict[str, Any] = {}

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
            model="Text & Sound Pools",
        )

    async def async_added_to_hass(self) -> None:
        if self._registered_key != self.entity_id:
            if self._registered_key in POOLS:
                try:
                    del POOLS[self._registered_key]
                except Exception:
                    pass
            POOLS[self.entity_id] = self._pool
            self._registered_key = self.entity_id

        await self._pool.async_force_reload_and_push_state()

    def _update_from_pool(self, new_state: str) -> None:
        self._state = new_state
        self._attrs = self._pool.as_attrs()

class PoolsTextSensor(_BasePoolSensor):
    def __init__(
        self,
        hass: HomeAssistant,
        directory: str,
        filename: str,
        name: str,
        unique_id: Optional[str],
        suggested_entity_id: str,
    ):
        super().__init__(hass, name, unique_id, suggested_entity_id)
        self._pool = PhrasePool(hass, self, directory, filename)
        POOLS[self.entity_id] = self._pool

class PoolsSoundSensor(_BasePoolSensor):
    def __init__(
        self,
        hass: HomeAssistant,
        sounds_root: str,
        folder: str,
        name: str,
        unique_id: Optional[str],
        suggested_entity_id: str,
        url_mode: str,
    ):
        super().__init__(hass, name, unique_id, suggested_entity_id)
        self._pool = SoundPool(hass, self, sounds_root, folder, url_mode=url_mode)
        POOLS[self.entity_id] = self._pool

# ---------- Base + Text Pool ----------

class BasePool:
    def __init__(self, hass: HomeAssistant, entity) -> None:
        self.hass = hass
        self.entity = entity
        self.shuffle_count = 0
        self.reload_count = 0
        self.last_shuffle_iso: Optional[str] = None
        self.last_reload_iso: Optional[str] = None

    def reset_stats(self) -> None:
        self.shuffle_count = 0
        self.reload_count = 0
        self.last_shuffle_iso = None
        self.last_reload_iso = None

class PhrasePool(BasePool):
    def __init__(self, hass: HomeAssistant, entity, directory: str, filename: str):
        super().__init__(hass, entity)
        self.directory = directory
        self.filename = filename
        self.full_path = hass.config.path(os.path.join(directory, filename))
        self.lines: List[str] = []
        self.truncated_lines = 0
        self.ignored_blank = 0
        self.last_index: Optional[int] = None
        self.file_mtime: Optional[float] = None

    def _load_file(self) -> None:
        self.lines = []
        self.truncated_lines = 0
        self.ignored_blank = 0
        if not os.path.exists(self.full_path):
            logging.getLogger(__name__).warning("File does not exist: %s", self.full_path)
            self.file_mtime = None
            return
        try:
            stat = os.stat(self.full_path)
            self.file_mtime = stat.st_mtime
            with open(self.full_path, "r", encoding="utf-8", errors="ignore") as f:
                for raw in f:
                    if len(self.lines) >= MAX_LINES:
                        break
                    line = raw.rstrip("\r\n")
                    if not line.strip():
                        self.ignored_blank += 1
                        continue
                    if len(line) > MAX_CHARS:
                        line = line[:MAX_CHARS]
                        self.truncated_lines += 1
                    self.lines.append(line)
        except Exception as e:
            logging.getLogger(__name__).exception("Failed reading %s: %s", self.full_path, e)

    def _maybe_reload(self) -> None:
        try:
            stat = os.stat(self.full_path)
            if self.file_mtime is None or stat.st_mtime != self.file_mtime:
                self._load_file()
        except FileNotFoundError:
            self._load_file()

    def pick_random(self) -> str:
        import random
        if not self.lines:
            return ""
        if len(self.lines) == 1:
            self.last_index = 0
            return self.lines[0]
        choices = list(range(len(self.lines)))
        if self.last_index is not None and self.last_index in choices and len(choices) > 1:
            choices.remove(self.last_index)
        idx = random.choice(choices)
        self.last_index = idx
        return self.lines[idx]

    async def async_shuffle_and_push_state(self):
        await self.hass.async_add_executor_job(self._maybe_reload)
        phrase = self.pick_random()
        self.shuffle_count += 1
        from datetime import datetime
        self.last_shuffle_iso = datetime.now().isoformat(timespec="seconds")
        self.entity._update_from_pool(phrase)
        self.entity.async_write_ha_state()

    async def async_force_reload_and_push_state(self):
        await self.hass.async_add_executor_job(self._load_file)
        from datetime import datetime
        self.reload_count += 1
        self.last_reload_iso = datetime.now().isoformat(timespec="seconds")
        phrase = self.pick_random()
        self.entity._update_from_pool(phrase)
        self.entity.async_write_ha_state()

    def as_attrs(self) -> dict:
        from datetime import datetime
        mtime_iso = (
            datetime.fromtimestamp(self.file_mtime).isoformat()
            if self.file_mtime else None
        )
        return {
            ATTR_FILE: self.full_path,
            ATTR_LINE_COUNT: len(self.lines),
            ATTR_TRUNCATED_LINES: self.truncated_lines,
            ATTR_IGNORED_BLANK: self.ignored_blank,
            ATTR_LAST_INDEX: self.last_index,
            ATTR_FILE_MTIME: mtime_iso,
            ATTR_SHUFFLE_COUNT: self.shuffle_count,
            ATTR_RELOAD_COUNT: self.reload_count,
            ATTR_LAST_SHUFFLE: self.last_shuffle_iso,
            ATTR_LAST_RELOAD: self.last_reload_iso,
        }

# ---------- Sound Pool ----------

class SoundPool(BasePool):
    """Handles scanning a category dir and picking a random MP3.
    Returns a URL depending on url_mode:
      - 'auto'  -> '/local/...' if path under 'www/', else 'media-source://...' if under 'media/'
      - 'local' -> force '/local/...'
      - 'media' -> force 'media-source://media_source/local/...'
      - 'none'  -> return empty state; URL only in attrs (absolute path), useful for custom pipelines.
    """

    def __init__(self, hass: HomeAssistant, entity, sounds_root: str, folder: str, url_mode: str = "auto"):
        super().__init__(hass, entity)
        self.sounds_root = sounds_root
        self.folder = folder
        self.url_mode = url_mode
        self.dir_path = hass.config.path(os.path.join(sounds_root, folder))
        self.files: List[str] = []      # basenames
        self.last_index: Optional[int] = None
        self.dir_mtime: Optional[float] = None
        self.last_file: Optional[str] = None

    def _scan_dir(self) -> None:
        self.files = []
        self.last_index = None
        self.last_file = None
        self.dir_mtime = None
        if not os.path.isdir(self.dir_path):
            return
        try:
            latest = 0.0
            for name in sorted(os.listdir(self.dir_path)):
                if not name.lower().endswith(".mp3"):
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
            logging.getLogger(__name__).exception("Failed scanning sounds dir %s: %s", self.dir_path, e)

    def _maybe_reload(self) -> None:
        self._scan_dir()

    def _build_url(self, basename: str) -> str:
        # 'www/...' -> /local/..., 'media/...' -> media-source://media_source/local/...
        subpath = f"{self.sounds_root}/{self.folder}".split("www/", 1)[-1].strip("/")
        if self.url_mode == "local" or (self.url_mode == "auto" and self.sounds_root.startswith("www/")):
            return f"/local/{subpath}/{basename}"
        if self.url_mode == "media" or (self.url_mode == "auto" and self.sounds_root.startswith("media/")):
            # media-source requires 'local' provider; user must place files under /config/media
            sub_media = f"{self.sounds_root.split('media/',1)[-1].strip('/')}/{self.folder}"
            return f"media-source://media_source/local/{sub_media}/{basename}"
        # 'none' or unknown -> empty state; consumer can use absolute path from attrs
        return ""

    def pick_random(self) -> str:
        import random
        if not self.files:
            self.last_file = None
            return ""
        if len(self.files) == 1:
            self.last_index = 0
            self.last_file = self.files[0]
        else:
            choices = list(range(len(self.files)))
            if self.last_index is not None and self.last_index in choices and len(choices) > 1:
                choices.remove(self.last_index)
            idx = random.choice(choices)
            self.last_index = idx
            self.last_file = self.files[idx]
        return self._build_url(self.last_file)

    async def async_shuffle_and_push_state(self):
        await self.hass.async_add_executor_job(self._maybe_reload)
        url = self.pick_random()
        from datetime import datetime
        self.shuffle_count += 1
        self.last_shuffle_iso = datetime.now().isoformat(timespec="seconds")
        self.entity._update_from_pool(url)
        self.entity.async_write_ha_state()

    async def async_force_reload_and_push_state(self):
        await self.hass.async_add_executor_job(self._scan_dir)
        from datetime import datetime
        self.reload_count += 1
        self.last_reload_iso = datetime.now().isoformat(timespec="seconds")
        url = self.pick_random()
        self.entity._update_from_pool(url)
        self.entity.async_write_ha_state()

    def as_attrs(self) -> dict:
        from datetime import datetime
        mtime_iso = (
            datetime.fromtimestamp(self.dir_mtime).isoformat()
            if self.dir_mtime else None
        )
        # Absolute path for external pipelines
        abs_file = os.path.join(self.dir_path, self.last_file) if self.last_file else None
        # Derive relative URL again for attrs
        rel_url = self._build_url(self.last_file) if self.last_file else None
        return {
            ATTR_DIR: self.dir_path,
            ATTR_FILE_COUNT: len(self.files),
            ATTR_LAST_INDEX: self.last_index,
            ATTR_LAST_FILE: self.last_file,
            ATTR_RELATIVE_URL: rel_url,
            ATTR_DIR_MTIME: mtime_iso,
            ATTR_SHUFFLE_COUNT: self.shuffle_count,
            ATTR_RELOAD_COUNT: self.reload_count,
            ATTR_LAST_SHUFFLE: self.last_shuffle_iso,
            ATTR_LAST_RELOAD: self.last_reload_iso,
            ATTR_FILE: abs_file,
        }
