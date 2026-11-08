"""Roblox side helpers: find installs, trust Proxion's certificate, clear cache."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import config as cfgmod

MARKER = "# --- Proxion CA ---"
PROCESS_NAMES = ("RobloxPlayerBeta.exe", "RobloxStudioBeta.exe")


def _local_appdata() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))


def version_dirs() -> list[Path]:
    """Every Roblox client folder we can find, including Bloxstrap and Fishstrap."""
    roots = [
        _local_appdata() / "Roblox" / "Versions",
        _local_appdata() / "Bloxstrap" / "Versions",
        _local_appdata() / "Fishstrap" / "Versions",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Roblox" / "Versions",
    ]
    extra = os.environ.get("PROXION_ROBLOX_VERSIONS")
    if extra:
        roots.append(Path(extra))
    found = []
    for root in roots:
        if not root.is_dir():
            continue
        for d in root.iterdir():
            if d.is_dir() and any((d / p).exists() for p in PROCESS_NAMES):
                found.append(d)
    return found


def ca_cert_file() -> Path:
    """Make sure the mitmproxy CA exists in our cert folder and return its path."""
    from mitmproxy import certs

    d = cfgmod.cert_dir()
    pem = d / "mitmproxy-ca-cert.pem"
    if not pem.exists():
        certs.CertStore.from_store(d, "mitmproxy", 2048)
    return pem


def install_cert() -> list[Path]:
    """Append our CA to ssl/cacert.pem in each Roblox version folder.

    Roblox ships its own CA bundle and ignores the Windows store, which is why
    this step is needed. Roblox updates create new folders, so run it again
    after an update (the GUI does this every time you start the proxy).
    """
    ca = ca_cert_file().read_text(encoding="ascii").strip()
    block = f"\n{MARKER}\n{ca}\n{MARKER}\n"
    patched = []
    for vdir in version_dirs():
        bundle = vdir / "ssl" / "cacert.pem"
        bundle.parent.mkdir(exist_ok=True)
        text = bundle.read_text(encoding="ascii", errors="ignore") if bundle.exists() else ""
        if ca in text:
            continue
        text = _strip_block(text)  # drop an older Proxion CA if there is one
        bundle.write_text(text.rstrip("\n") + "\n" + block, encoding="ascii")
        patched.append(bundle)
    return patched


def uninstall_cert() -> list[Path]:
    cleaned = []
    for vdir in version_dirs():
        bundle = vdir / "ssl" / "cacert.pem"
        if bundle.exists():
            text = bundle.read_text(encoding="ascii", errors="ignore")
            if MARKER in text:
                bundle.write_text(_strip_block(text), encoding="ascii")
                cleaned.append(bundle)
    return cleaned


def _strip_block(text: str) -> str:
    while MARKER in text:
        start = text.index(MARKER)
        end = text.find(MARKER, start + len(MARKER))
        if end == -1:
            text = text[:start]
            break
        text = text[:start].rstrip("\n") + "\n" + text[end + len(MARKER):].lstrip("\n")
    return text


def is_running() -> bool:
    if sys.platform != "win32":
        return False
    try:
        out = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout.lower()
    except OSError:
        return False
    return any(p.lower() in out for p in PROCESS_NAMES)


def cache_paths() -> list[Path]:
    temp = Path(os.environ.get("TEMP", _local_appdata() / "Temp"))
    rbx = _local_appdata() / "Roblox"
    return [
        temp / "Roblox" / "http",  # older HTTP cache
        rbx / "rbx-storage",  # newer content cache
        rbx / "rbx-storage.db",
        rbx / "rbx-storage.db-wal",
        rbx / "rbx-storage.db-shm",
    ]


def clear_cache() -> list[Path]:
    """Delete Roblox's asset cache so swapped assets get downloaded fresh."""
    if is_running():
        raise RuntimeError("Close Roblox first, the cache files are locked while it runs.")
    removed = []
    for p in cache_paths():
        try:
            if p.is_dir():
                shutil.rmtree(p)
                removed.append(p)
            elif p.exists():
                p.unlink()
                removed.append(p)
        except OSError:
            pass
    return removed
