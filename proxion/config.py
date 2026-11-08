"""Where Proxion keeps its files, plus loading and saving the replacement rules."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

APP_NAME = "Proxion"


def app_dir() -> Path:
    """Per-user folder for config, logs and the proxy certificate."""
    override = os.environ.get("PROXION_HOME")
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
    else:
        base = Path.home() / ".proxion"
    base.mkdir(parents=True, exist_ok=True)
    return base


def config_path() -> Path:
    return app_dir() / "config.json"


def log_path() -> Path:
    """JSON lines file the proxy writes every asset it sees to."""
    return app_dir() / "assets.jsonl"


def cert_dir() -> Path:
    d = app_dir() / "certs"
    d.mkdir(parents=True, exist_ok=True)
    return d


# Modes a rule can use
MODE_ID = "id"  # swap to another Roblox asset id
MODE_FILE = "file"  # serve a file from disk
MODE_REMOVE = "remove"  # tell Roblox the asset does not exist
MODES = (MODE_ID, MODE_FILE, MODE_REMOVE)


@dataclass
class Rule:
    name: str = "New rule"
    enabled: bool = True
    targets: list[int] = field(default_factory=list)  # asset ids to replace
    mode: str = MODE_ID
    replacement: str = ""  # asset id (MODE_ID) or file path (MODE_FILE)

    @classmethod
    def from_dict(cls, d: dict) -> "Rule":
        r = cls(
            name=str(d.get("name", "Rule")),
            enabled=bool(d.get("enabled", True)),
            targets=[int(t) for t in d.get("targets", []) if str(t).strip().isdigit()],
            mode=d.get("mode", MODE_ID),
            replacement=str(d.get("replacement", "")),
        )
        if r.mode not in MODES:
            r.mode = MODE_ID
        return r


@dataclass
class Config:
    rules: list[Rule] = field(default_factory=list)
    # Process name mitmproxy's local capture mode should grab (Windows/macOS).
    capture_process: str = "RobloxPlayerBeta"
    # "local" captures only Roblox's traffic. "regular" runs a normal HTTP proxy
    # on proxy_port that you point things at yourself.
    proxy_mode: str = "local"
    proxy_port: int = 8080

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> "Config":
        return cls(
            rules=[Rule.from_dict(r) for r in d.get("rules", [])],
            capture_process=d.get("capture_process", "RobloxPlayerBeta"),
            proxy_mode=d.get("proxy_mode", "local"),
            proxy_port=int(d.get("proxy_port", 8080)),
        )


def load(path: Path | None = None) -> Config:
    path = path or config_path()
    if not path.exists():
        return Config()
    try:
        return Config.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValueError, TypeError):
        # Keep the broken file around instead of silently wiping someone's rules.
        path.rename(path.with_suffix(".broken.json"))
        return Config()


def save(cfg: Config, path: Path | None = None) -> None:
    path = path or config_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(cfg.to_json(), encoding="utf-8")
    os.replace(tmp, path)  # atomic so the proxy never reads half a file
