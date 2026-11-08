"""Scraped games: the community list of game asset dumps that Fleasion publishes.

The index (CLOG.json) looks like:

    {"games": {"Arsenal": {"Owner": "Sky", "id": 286090429,
                           "github": "https://.../ORIGINAL.json",
                           "replacement": "https://.../REPLACEMENT.json"}, ...}}

("Replacement" is sometimes capitalised.) The files it points to are free-form nested JSON
whose leaves are asset IDs, e.g. {"gunsounds": {"Pistols": {"Deagle_Fire": "7656488588"}}}.
Nothing here is executed: we only read IDs out of it for the user to copy into a rule.
"""

from __future__ import annotations

import hashlib
import ssl
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import config as cfgmod

CLOG_URL = "https://raw.githubusercontent.com/fleasion/Fleasion/refs/heads/clog/CLOG.json"
MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024
TIMEOUT = 15


@dataclass
class Game:
    name: str
    place_id: int | None
    owner: str
    assets_url: str | None
    replacements_url: str | None


def cache_dir() -> Path:
    d = cfgmod.app_dir() / "PreJsons"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_file(url: str) -> Path:
    return cache_dir() / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".json")


def download(url: str) -> bytes:
    """GET an https URL with a size limit and a timeout. Raises OSError or ValueError."""
    problem = cfgmod.url_problem(url)
    if problem:
        raise ValueError(f"{url}: {problem}")
    req = urllib.request.Request(url, headers={"User-Agent": "Proxion"})  # noqa: S310 (https checked above)
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=ssl.create_default_context()) as resp:  # noqa: S310
        data = resp.read(MAX_DOWNLOAD_BYTES + 1)
    if len(data) > MAX_DOWNLOAD_BYTES:
        raise ValueError(f"{url}: bigger than {MAX_DOWNLOAD_BYTES // (1024 * 1024)} MB")
    return data


def fetch_json(url: str, *, offline_ok: bool = True, downloader=download):
    """Download and parse JSON, caching it. Falls back to the cached copy when offline.

    Returns (data, from_cache).
    """
    cache = _cache_file(url)
    try:
        raw = downloader(url)
        data = cfgmod.decode_json_bytes(raw)
        cache.write_bytes(raw)
        return data, False
    except (OSError, ValueError, RecursionError):
        if offline_ok and cache.exists():
            return cfgmod.decode_json_bytes(cache.read_bytes()), True
        raise


def _url(entry: dict, *keys: str) -> str | None:
    """First usable https link among keys. Anything unsafe is treated as missing."""
    for k in keys:
        v = entry.get(k)
        if isinstance(v, str) and not cfgmod.url_problem(v):
            return v
    return None


def parse_clog(data) -> list[Game]:
    """Turn CLOG.json into a sorted list of games. Bad entries are skipped."""
    games = data.get("games", data) if isinstance(data, dict) else data
    if isinstance(games, dict):
        items = list(games.items())
    elif isinstance(games, list):
        items = [(g.get("name") or g.get("game") or "?", g) for g in games if isinstance(g, dict)]
    else:
        return []
    out = []
    for name, g in items:
        if not isinstance(g, dict):
            continue
        place = cfgmod.as_asset_id(g.get("id") or g.get("placeId") or g.get("place_id") or "")
        owner = next((str(g[k]) for k in ("Owner", "owner", "credit", "Credit", "author", "Author") if g.get(k)), "?")

        out.append(Game(str(name), place, owner, _url(g, "github"), _url(g, "replacement", "Replacement")))
    return sorted(out, key=lambda x: x.name.lower())


def leaf_values(node, limit: int = 100_000) -> list[str]:
    """Every leaf value under a JSON node, as strings (IDs, links), depth first."""
    out: list[str] = []
    stack = [node]
    while stack and len(out) < limit:
        cur = stack.pop()
        if isinstance(cur, dict):
            stack.extend(reversed(list(cur.values())))
        elif isinstance(cur, list):
            stack.extend(reversed(cur))
        elif cur is not None and not isinstance(cur, bool):
            out.append(str(cur))
    return out


def asset_ids(values: list[str]) -> list[int]:
    """Just the usable asset IDs from leaf values, in order, without duplicates."""
    seen, out = set(), []
    for v in values:
        n = cfgmod.as_asset_id(v)
        if n is not None and n > cfgmod.RESERVED_MAX and n not in seen:
            seen.add(n)
            out.append(n)
    return out
