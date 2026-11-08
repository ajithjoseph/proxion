"""Settings and replacement configs.

Configs use the same file format as Fleasion, so configs can be shared both ways:

    {"replacement_rules": [
        {"name": "Sky", "replace_ids": [123, "Hat"], "mode": "id", "with_id": 456, "enabled": true},
        {"name": "My file", "replace_ids": [789], "mode": "local", "local_path": "/Folder/sky.png"},
        {"name": "Web", "replace_ids": [111], "mode": "cdn", "cdn_url": "https://..."},
        {"name": "Gone", "replace_ids": [222], "mode": "remove"},
        {"type": "group", "name": "Folder", "children": [ ...more rules... ]}
    ]}

Each config is one .json file in the configs folder. settings.json says which
configs are turned on. Rules are kept as plain dicts so keys we don't use are
preserved when the file is saved again.
"""

from __future__ import annotations

import contextlib
import ipaddress
import json
import locale
import os
import re
import shutil
import sys
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

APP_NAME = "Proxion"

MODE_ID = "id"  # swap to another Roblox asset id (with_id)
MODE_LOCAL = "local"  # serve a file from disk (local_path)
MODE_CDN = "cdn"  # send Roblox to a URL (cdn_url)
MODE_REMOVE = "remove"  # tell Roblox the asset does not exist
MODES = (MODE_ID, MODE_LOCAL, MODE_CDN, MODE_REMOVE)

# Roblox asset type ids. Names can be used in replace_ids to hit every asset of a type.
ASSET_TYPES = {
    1: "Image",
    2: "TShirt",
    3: "Audio",
    4: "Mesh",
    5: "Lua",
    8: "Hat",
    9: "Place",
    10: "Model",
    11: "Shirt",
    12: "Pants",
    13: "Decal",
    17: "Head",
    18: "Face",
    19: "Gear",
    21: "Badge",
    24: "Animation",
    27: "Torso",
    28: "RightArm",
    29: "LeftArm",
    30: "LeftLeg",
    31: "RightLeg",
    32: "Package",
    34: "GamePass",
    38: "Plugin",
    40: "MeshPart",
    41: "HairAccessory",
    42: "FaceAccessory",
    43: "NeckAccessory",
    44: "ShoulderAccessory",
    45: "FrontAccessory",
    46: "BackAccessory",
    47: "WaistAccessory",
    48: "ClimbAnimation",
    49: "DeathAnimation",
    50: "FallAnimation",
    51: "IdleAnimation",
    52: "JumpAnimation",
    53: "RunAnimation",
    54: "SwimAnimation",
    55: "WalkAnimation",
    56: "PoseAnimation",
    61: "EmoteAnimation",
    62: "Video",
    63: "TexturePack",
    64: "TShirtAccessory",
    65: "ShirtAccessory",
    66: "PantsAccessory",
    67: "JacketAccessory",
    68: "SweaterAccessory",
    69: "ShortsAccessory",
    70: "LeftShoeAccessory",
    71: "RightShoeAccessory",
    72: "DressSkirtAccessory",
    73: "FontFamily",
    76: "EyebrowAccessory",
    77: "EyelashAccessory",
    78: "MoodAnimation",
    79: "DynamicHead",
}
TYPE_BY_NAME = {v.lower(): k for k, v in ASSET_TYPES.items()}
RESERVED_MAX = 80  # Fleasion ignores bare ids 1..80 because they clash with type ids
BAD_NAME_CHARS = '\\/:*?"<>|'
# Windows device names that can't be used as file names, with or without an extension
RESERVED_NAMES = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
MAX_CONFIG_BYTES = 20 * 1024 * 1024  # configs are small text files, anything bigger is not a config
MAX_GROUP_DEPTH = 32
_ID_RE = re.compile(r"[0-9]{1,19}", re.ASCII)  # fits in int64, rejects "²" and other unicode digits


# ---------------------------------------------------------------- folders
def app_dir() -> Path:
    override = os.environ.get("PROXION_HOME")
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
    else:
        base = Path.home() / ".proxion"
    base.mkdir(parents=True, exist_ok=True)
    return base


def configs_dir() -> Path:
    d = app_dir() / "configs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def settings_path() -> Path:
    return app_dir() / "settings.json"


def log_path() -> Path:
    return app_dir() / "assets.jsonl"


def cert_dir() -> Path:
    d = app_dir() / "certs"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------- settings
@dataclass
class Settings:
    enabled_configs: list[str] = field(default_factory=lambda: ["Default"])
    last_config: str = "Default"
    capture_process: str = "RobloxPlayerBeta"
    proxy_mode: str = "local"  # "local" grabs only Roblox, "regular" listens on proxy_port
    proxy_port: int = 8080
    clear_cache_on_start: bool = True  # like Fleasion: clear Roblox's cache when the proxy starts
    seen_welcome: bool = False  # first run shows the welcome and the Help tab

    @classmethod
    def from_dict(cls, d: dict) -> Settings:
        s = cls()
        for k in asdict(s):
            if k in d:
                setattr(s, k, d[k])
        s.proxy_port = int(s.proxy_port)
        s.enabled_configs = [str(n) for n in s.enabled_configs]
        return s


Config = Settings  # proxy.build_command takes either name


def load_settings() -> Settings:
    _migrate_v0()
    p = settings_path()
    s = Settings()
    if p.exists():
        with contextlib.suppress(ValueError, TypeError):
            s = Settings.from_dict(json.loads(p.read_text(encoding="utf-8")))
    if not list_configs():
        write_config("Default", empty_config())
    return s


def save_settings(s: Settings) -> None:
    _atomic_write(settings_path(), json.dumps(asdict(s), indent=2))


load = load_settings  # older name


def _migrate_v0() -> None:
    """Proxion 0.1 kept rules in config.json. Move them into configs/Default.json."""
    old = app_dir() / "config.json"
    if not old.exists():
        return
    try:
        data = json.loads(old.read_text(encoding="utf-8"))
    except ValueError:
        return
    rules = []
    for r in data.get("rules", []):
        mode = {"file": MODE_LOCAL}.get(r.get("mode"), r.get("mode", MODE_ID))
        rule = {
            "name": r.get("name", "Rule"),
            "replace_ids": r.get("targets", []),
            "mode": mode,
            "enabled": r.get("enabled", True),
        }
        if mode == MODE_ID:
            rule["with_id"] = r.get("replacement", "")
        elif mode == MODE_LOCAL:
            rule["local_path"] = r.get("replacement", "")
        rules.append(rule)
    write_config("Default", {"replacement_rules": rules})
    s = {k: data[k] for k in ("capture_process", "proxy_mode", "proxy_port") if k in data}
    _atomic_write(settings_path(), json.dumps(asdict(Settings.from_dict(s)), indent=2))
    old.rename(old.with_suffix(".migrated.json"))


# ---------------------------------------------------------------- config files
def empty_config() -> dict:
    return {"replacement_rules": []}


def list_configs() -> list[str]:
    return sorted((p.stem for p in configs_dir().glob("*.json")), key=str.lower)


def config_file(name: str) -> Path:
    return configs_dir() / f"{name}.json"


def decode_json_bytes(raw: bytes):
    """Parse JSON in whatever encoding Notepad or a Discord download used."""
    encodings = ["utf-8-sig", "utf-16", "utf-32", "cp1252", locale.getpreferredencoding(False)]
    last = None
    for enc in encodings:
        try:
            return json.loads(raw.decode(enc))
        except (UnicodeError, ValueError) as e:
            last = e
    raise ValueError(f"not a valid JSON config ({last})")


def normalize(data) -> dict:
    """Accept {"replacement_rules": [...]}, a bare list, or an empty dict."""
    if isinstance(data, list):
        return {"replacement_rules": data}
    if not isinstance(data, dict):
        raise ValueError("config must be a JSON object or list")
    if not isinstance(data.get("replacement_rules"), list):
        data["replacement_rules"] = []
    return data


def read_config(name: str) -> dict:
    p = config_file(name)
    if not p.exists():
        return empty_config()
    try:
        return normalize(decode_json_bytes(p.read_bytes()))
    except ValueError:
        return empty_config()


def write_config(name: str, data: dict) -> None:
    _atomic_write(config_file(name), json.dumps(data, indent=2))


def _is_reserved(name: str) -> bool:
    return name.split(".")[0].strip().lower() in RESERVED_NAMES


def check_name(name: str) -> str:
    name = name.strip()
    if (
        not name
        or any(c in BAD_NAME_CHARS or ord(c) < 32 for c in name)
        or name.endswith(".")
        or name in (".", "..")
        or _is_reserved(name)
    ):
        raise ValueError(
            f"Config names can't be empty, end with a dot, use any of  {BAD_NAME_CHARS}  "
            "or be a Windows device name like CON or NUL"
        )
    return name


def unique_name(base: str) -> str:
    base = "".join("_" if c in BAD_NAME_CHARS or ord(c) < 32 else c for c in base).strip().rstrip(".") or "Config"
    if _is_reserved(base):
        base = f"{base}_"
    existing = {n.lower() for n in list_configs()}
    name, i = base, 2
    while name.lower() in existing:
        name, i = f"{base} ({i})", i + 1
    return name


def create_config(name: str) -> str:
    name = check_name(name)
    if config_file(name).exists():
        raise FileExistsError(f'A config called "{name}" already exists')
    write_config(name, empty_config())
    return name


def duplicate_config(name: str) -> str:
    new = unique_name(f"{name} copy")
    shutil.copyfile(config_file(name), config_file(new))
    return new


def rename_config(old: str, new: str, settings: Settings) -> str:
    new = check_name(new)
    if new.lower() != old.lower() and config_file(new).exists():
        raise FileExistsError(f'A config called "{new}" already exists')
    os.replace(config_file(old), config_file(new))
    settings.enabled_configs = [new if n == old else n for n in settings.enabled_configs]
    if settings.last_config == old:
        settings.last_config = new
    return new


def delete_config(name: str, settings: Settings) -> None:
    if len(list_configs()) <= 1:
        raise ValueError("You need at least one config")
    config_file(name).unlink(missing_ok=True)
    settings.enabled_configs = [n for n in settings.enabled_configs if n != name]
    if settings.last_config == name:
        settings.last_config = list_configs()[0]


def import_config(path: str | Path) -> str:
    """Copy a config file (Fleasion or Proxion) into the configs folder.

    Returns the name it was saved under. Raises ValueError if it isn't a config.
    """
    path = Path(path)
    if not path.is_file():
        raise ValueError("not a file")
    if path.stat().st_size > MAX_CONFIG_BYTES:
        raise ValueError(f"too big for a config (over {MAX_CONFIG_BYTES // (1024 * 1024)} MB)")
    try:
        data = normalize(decode_json_bytes(path.read_bytes()))
    except RecursionError as e:  # absurdly nested JSON
        raise ValueError("config is nested too deeply") from e
    name = unique_name(path.stem)
    write_config(name, data)  # re-written as clean UTF-8
    return name


def export_config(name: str, dest: str | Path) -> None:
    Path(dest).write_text(json.dumps(read_config(name), indent=2), encoding="utf-8")


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)  # the proxy never sees half a file


# ---------------------------------------------------------------- rules
def iter_rules(rules: list, group_enabled: bool = True, path: tuple = ()) -> Iterator[tuple[tuple, dict, bool]]:
    """Yield (index path, rule, effective enabled) for every rule, walking into groups."""
    if not isinstance(rules, list) or len(path) > MAX_GROUP_DEPTH:
        return
    for i, r in enumerate(rules):
        if not isinstance(r, dict):
            continue
        on = group_enabled and r.get("enabled", True) is not False
        if r.get("type") == "group":
            yield from iter_rules(r.get("children") or [], on, path + (i,))
        else:
            yield path + (i,), r, on


def rule_mode(r: dict) -> str:
    mode = r.get("mode")
    if mode is None and "remove" in r:
        mode = MODE_REMOVE if r["remove"] else MODE_ID
    return mode if mode in MODES else MODE_ID


def as_asset_id(v) -> int | None:
    """Parse an asset id from an int or a plain ASCII digit string, else None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v if 0 < v < 2**63 else None
    if isinstance(v, str) and _ID_RE.fullmatch(v.strip()):
        return int(v.strip())
    return None


def parse_target(t) -> tuple[str, object] | None:
    """Turn one replace_ids entry into ("id", 123) or ("type", 8), or None if unsupported."""
    n = as_asset_id(t)
    if n is not None:
        return ("id", n) if n > RESERVED_MAX else None
    if isinstance(t, str):
        key = t.strip().replace(" ", "").lower()
        if key in TYPE_BY_NAME:
            return ("type", TYPE_BY_NAME[key])
    return None  # slot keys like "123:1" and R15Animation style selectors


def local_path_problem(p: str) -> str | None:
    """Why a local_path can't be used, or None if it's fine.

    Network paths (\\\\server\\share, //server/share) are refused because opening them makes
    Windows send your login hash to that server. Device paths can hang or eat memory.
    """
    p = p.strip()
    if not p:
        return "empty path"
    if p.startswith(("\\\\", "//")) or "\\\\?\\" in p or "\\\\.\\" in p:
        return "network and device paths are not allowed"
    if "%" in p or p.startswith("~"):
        return "environment variables and ~ are not allowed"
    if _is_reserved(Path(p.replace("\\", "/")).name):
        return "Windows device names are not allowed"
    return None


def is_inside_configs(p: str) -> bool:
    try:
        return Path(p).resolve().is_relative_to(configs_dir().resolve())
    except (OSError, ValueError):
        return False


def url_problem(u: str) -> str | None:
    """Why a cdn_url can't be used, or None if it's fine."""
    try:
        parts = urlsplit(u.strip())
    except ValueError:
        return "not a valid URL"
    if parts.scheme != "https":
        return "only https:// links are allowed"
    host = (parts.hostname or "").lower()
    if not host:
        return "the link has no host"
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".lan")):
        return "links to your own PC or network are not allowed"
    try:
        ipaddress.ip_address(host)
        return "links to bare IP addresses are not allowed"
    except ValueError:
        pass
    return None


def resolve_local_path(p: str) -> str:
    """Fleasion style: "/Folder/file.png" means configs/Folder/file.png."""
    p = p.strip()
    if p.startswith("/") and not p.startswith("//") and "\\" not in p:
        parts = [x for x in p.split("/") if x]
        if parts and not any(x in (".", "..") for x in parts):
            candidate = configs_dir().joinpath(*parts)
            if candidate.exists() or not Path(p).exists():
                return str(candidate)
    return p


@dataclass
class Compiled:
    """Everything the proxy needs, flattened from all enabled configs."""

    by_id: dict[int, tuple[str, object]] = field(default_factory=dict)
    by_type: dict[int, tuple[str, object]] = field(default_factory=dict)
    skipped: int = 0  # targets we couldn't use
    problems: list[str] = field(default_factory=list)  # rules ignored because they're unsafe or broken


INVALID = "invalid"  # rule_action result for a rule that must be ignored


def rule_action(r: dict) -> tuple[str, object]:
    """(mode, value) for a rule. ("invalid", reason) means the rule is ignored.

    Like Fleasion, an id/local/cdn rule with an empty replacement removes the asset.
    """
    mode = rule_mode(r)
    if mode == MODE_ID:
        raw = r.get("with_id")
        if raw is None or str(raw).strip() == "":
            return (MODE_REMOVE, None)
        n = as_asset_id(raw)
        return (MODE_ID, n) if n is not None else (INVALID, f"with_id {raw!r} is not an asset id")
    if mode == MODE_LOCAL:
        p = str(r.get("local_path") or "").strip()
        if not p:
            return (MODE_REMOVE, None)
        problem = local_path_problem(p)
        return (INVALID, f"{p}: {problem}") if problem else (MODE_LOCAL, resolve_local_path(p))
    if mode == MODE_CDN:
        u = str(r.get("cdn_url") or "").strip()
        if not u:
            return (MODE_REMOVE, None)
        problem = url_problem(u)
        return (INVALID, f"{u}: {problem}") if problem else (MODE_CDN, u)
    return (MODE_REMOVE, None)


def compile_rules(config_datas: list[dict]) -> Compiled:
    out = Compiled()
    for data in config_datas:
        for _, rule, on in iter_rules(data.get("replacement_rules", [])):
            if not on:
                continue
            action = rule_action(rule)
            if action[0] == INVALID:
                out.problems.append(f"{rule.get('name', 'Rule')}: {action[1]}")
                continue
            targets = rule.get("replace_ids") or []
            if not isinstance(targets, list):
                targets = [targets]
            for t in targets:
                parsed = parse_target(t)
                if parsed is None:
                    out.skipped += 1
                elif parsed[0] == "id":
                    out.by_id[parsed[1]] = action  # later rules win, like Fleasion
                elif action[0] == MODE_ID:
                    out.skipped += 1  # can't swap a whole type to one id before we know the type
                else:
                    out.by_type[parsed[1]] = action
    return out


def compile_enabled(settings: Settings | None = None) -> Compiled:
    settings = settings or load_settings()
    names = [n for n in settings.enabled_configs if config_file(n).exists()]
    return compile_rules([read_config(n) for n in names])


def review_config(data: dict) -> list[str]:
    """Things a user should know before turning on a config someone else made."""
    notes, hosts = [], set()
    for _, rule, _on in iter_rules(data.get("replacement_rules", [])):
        name = rule.get("name", "Rule")
        kind, value = rule_action(rule)
        if kind == INVALID:
            notes.append(f"Ignored, unsafe or broken: {name}: {value}")
        elif kind == MODE_LOCAL and not is_inside_configs(value):
            notes.append(f"Uses a file outside the configs folder: {value}")
        elif kind == MODE_CDN:
            hosts.add(urlsplit(value).hostname)
    if hosts:
        notes.append("Downloads replacements from: " + ", ".join(sorted(hosts)))
    return notes
