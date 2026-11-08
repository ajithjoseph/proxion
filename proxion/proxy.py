"""Starts and stops mitmdump with the Proxion addon loaded."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path

from . import config as cfgmod

ADDON = Path(__file__).resolve().parent / "addon.py"


def _mitmdump() -> list[str]:
    if getattr(sys, "frozen", False):
        # Single exe build: Proxion.exe runs mitmdump itself (see __main__.py).
        return [sys.executable, "__mitmdump"]
    # Same Python that runs Proxion, so it always finds the right mitmproxy.
    return [sys.executable, "-c", "import sys; from mitmproxy.tools.main import mitmdump; sys.exit(mitmdump())"]


# Only asset traffic is decrypted. Logins, cookies and everything else Roblox sends
# pass through untouched, so a bug here can never see them.
INTERCEPT_HOSTS = r"^assetdelivery\.roblox\.com:\d+$"
PROCESS_NAME_RE = re.compile(r"[A-Za-z0-9_.\- ]{1,64}")


def build_command(cfg: cfgmod.Config) -> list[str]:
    cmd = _mitmdump() + [
        "-s",
        str(ADDON),
        "--set",
        f"confdir={cfgmod.cert_dir()}",
        "--set",
        f"allow_hosts={INTERCEPT_HOSTS}",
        "--set",
        "flow_detail=0",
        "--set",
        "termlog_verbosity=warn",
    ]
    if cfg.proxy_mode == "local":
        if not PROCESS_NAME_RE.fullmatch(cfg.capture_process):
            raise ValueError(f"invalid process name: {cfg.capture_process!r}")
        cmd += ["--mode", f"local:{cfg.capture_process}"]
    else:
        port = int(cfg.proxy_port)
        if not 1 <= port <= 65535:
            raise ValueError(f"invalid port: {port}")
        # localhost only: never an open proxy for the rest of the network
        cmd += ["--mode", "regular", "--set", "listen_host=127.0.0.1", "--listen-port", str(port)]
    return cmd


class ProxyRunner:
    def __init__(self, on_output: Callable[[str], None] | None = None):
        self.proc: subprocess.Popen | None = None
        self.on_output = on_output or (lambda s: None)

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self, cfg: cfgmod.Config) -> None:
        if self.running:
            return
        env = dict(os.environ, PROXION_HOME=str(cfgmod.app_dir()))
        self.proc = subprocess.Popen(
            build_command(cfg),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        proc = self.proc
        if proc is None or proc.stdout is None:
            return
        for line in proc.stdout:
            self.on_output(line.rstrip())
        self.on_output(f"[proxy exited with code {proc.wait()}]")

    def stop(self) -> None:
        if not self.running:
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
