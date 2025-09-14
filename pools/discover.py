import os
from typing import List
from homeassistant.core import HomeAssistant
from .utils import resolve_path, match_patterns

async def scan_files(hass: HomeAssistant, directory: str, exts: List[str], includes: List[str], excludes: List[str]) -> List[str]:
    abs_dir = resolve_path(hass, directory)
    def _scan():
        if not os.path.isdir(abs_dir): return []
        return [
            f for f in sorted(os.listdir(abs_dir))
            if any(f.lower().endswith(ext) for ext in exts) and match_patterns(f, includes, excludes)
        ]
    return await hass.async_add_executor_job(_scan)

async def scan_media_folders(hass: HomeAssistant, root: str, exts: List[str], includes: List[str], excludes: List[str]) -> List[str]:
    abs_root = resolve_path(hass, root)
    def _scan():
        if not os.path.isdir(abs_root): return []
        found = []
        for entry in sorted(os.listdir(abs_root)):
            full = os.path.join(abs_root, entry)
            if not os.path.isdir(full): continue
            try:
                has_media = any(
                    f.lower().endswith(tuple(exts)) and match_patterns(f, includes, excludes)
                    for f in os.listdir(full)
                )
            except Exception:
                has_media = False
            if has_media: found.append(entry)
        return found
    return await hass.async_add_executor_job(_scan)
