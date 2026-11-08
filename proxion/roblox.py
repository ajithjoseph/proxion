"""Roblox side helpers: find installs, trust Proxion's certificate, clear cache."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
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
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Roblox" / "Versions",
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


def _read_bundle(bundle: Path) -> str:
    # latin-1 maps every byte to one character, so writing back gives the exact same bytes
    return bundle.read_bytes().decode("latin-1") if bundle.exists() else ""


def _write_bundle(bundle: Path, text: str) -> None:
    tmp = bundle.with_name(bundle.name + ".proxion-tmp")
    tmp.write_bytes(text.encode("latin-1"))
    os.replace(tmp, bundle)  # a crash mid-write can't leave Roblox with a broken bundle


def install_cert() -> tuple[list[Path], list[str]]:
    """Append our CA to ssl/cacert.pem in each Roblox version folder.

    Roblox ships its own CA bundle and ignores the Windows store, which is why
    this step is needed. Roblox updates create new folders, so run it again
    after an update (the GUI does this every time you start the proxy).

    Returns (bundles patched, error messages for folders we couldn't write).
    """
    ca = ca_cert_file().read_text(encoding="ascii").strip()
    block = f"\n{MARKER}\n{ca}\n{MARKER}\n"
    patched, failed = [], []
    for vdir in version_dirs():
        bundle = vdir / "ssl" / "cacert.pem"
        try:
            bundle.parent.mkdir(exist_ok=True)
            text = _read_bundle(bundle)
            if ca in text:
                continue
            text = _strip_block(text)  # drop an older Proxion CA if there is one
            _write_bundle(bundle, text.rstrip("\n") + "\n" + block)
            patched.append(bundle)
        except OSError as e:
            failed.append(f"{vdir}: {e}")
    return patched, failed


def uninstall_cert() -> tuple[list[Path], list[str]]:
    cleaned, failed = [], []
    for vdir in version_dirs():
        bundle = vdir / "ssl" / "cacert.pem"
        try:
            text = _read_bundle(bundle)
            if MARKER in text:
                _write_bundle(bundle, _strip_block(text))
                cleaned.append(bundle)
        except OSError as e:
            failed.append(f"{vdir}: {e}")
    return cleaned, failed


def _strip_block(text: str) -> str:
    """Remove Proxion's CA blocks and nothing else, even if a block is cut off."""
    while MARKER in text:
        start = text.index(MARKER)
        end = text.find(MARKER, start + len(MARKER))
        if end != -1:
            end += len(MARKER)
        else:
            # Unmatched marker: drop only our own certificate after it, keep the real CAs.
            cert_end = text.find("-----END CERTIFICATE-----", start)
            end = cert_end + len("-----END CERTIFICATE-----") if cert_end != -1 else start + len(MARKER)
        text = text[:start].rstrip("\n") + "\n" + text[end:].lstrip("\n")
    return text


def is_running(names: tuple[str, ...] = PROCESS_NAMES) -> bool:
    if sys.platform != "win32":
        return False
    try:
        out = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout.lower()
    except OSError:
        return False
    return any(p.lower() in out for p in names)


def cache_paths() -> list[Path]:
    """Roblox's asset cache, the same set Fleasion clears, for the normal and Microsoft Store apps."""
    temp = Path(os.environ.get("TEMP", _local_appdata() / "Temp"))
    paths = [temp / "Roblox" / "http"]  # older HTTP cache
    for root in (_local_appdata() / "Roblox", _local_appdata() / "RobloxPCGDK"):
        paths += [root / "rbx-storage", root / "rbx-storage-sc", root / "rbx-storage.id"]
        paths += [root / f"rbx-storage.db{suffix}" for suffix in ("", "-wal", "-shm", "-journal")]
    return paths


def close_roblox() -> bool:
    """Force close the Roblox player. Returns True if it's no longer running."""
    if sys.platform != "win32":
        return not is_running()
    for name in PROCESS_NAMES[:1]:  # only the player, never Studio (unsaved work)
        subprocess.run(
            ["taskkill", "/F", "/IM", name],
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    for _ in range(20):
        if not is_running(PROCESS_NAMES[:1]):
            return True
        time.sleep(0.25)
    return False


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
