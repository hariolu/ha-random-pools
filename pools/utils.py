from __future__ import annotations
import os
from typing import List
from homeassistant.core import HomeAssistant

def slugify(s: str) -> str:
    s = s.lower()
    out, prev = [], False
    for ch in s:
        if ch.isalnum():
            out.append(ch); prev = False
        else:
            if not prev:
                out.append("_"); prev = True
    return "".join(out).strip("_")

def resolve_path(hass: HomeAssistant, rel: str) -> str:
    if rel.startswith("/"): return rel
    return hass.config.path(rel)

def match_patterns(name: str, includes: List[str], excludes: List[str]) -> bool:
    from fnmatch import fnmatch
    ok = True if not includes else any(fnmatch(name, pat) for pat in includes)
    if includes and not ok: return False
    if any(fnmatch(name, pat) for pat in excludes): return False
    return True
