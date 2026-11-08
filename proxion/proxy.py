"""Starts and stops mitmdump with the Proxion addon loaded."""

from __future__ import annotations

import os
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


def build_command(cfg: cfgmod.Config) -> list[str]:
    cmd = _mitmdump() + [
        "-s",
        str(ADDON),
        "--set",
        f"confdir={cfgmod.cert_dir()}",
        "--set",
        "flow_detail=0",
        "--set",
        "termlog_verbosity=warn",
    ]
    if cfg.proxy_mode == "local":
        cmd += ["--mode", f"local:{cfg.capture_process}"]
    else:
        cmd += ["--mode", "regular", "--listen-port", str(cfg.proxy_port)]
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
