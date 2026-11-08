"""mitmproxy addon that does the actual asset swapping.

How Roblox loads assets: the client POSTs a JSON list to
https://assetdelivery.roblox.com/v1/assets/batch like

    [{"assetId": 123, "requestId": "0", ...}, ...]

and gets back CDN locations for each one. Older code paths use
GET /v1/asset?id=123 which redirects to the CDN.

For each asset that matches a rule in an enabled config:
  * id:     the assetId in the request is swapped, so Roblox gets the other asset.
  * local:  the location points at a fake path this addon answers with the file.
  * cdn:    the location points at the rule's URL.
  * remove: Roblox is told the asset doesn't exist.
Rules can also target a whole asset type ("Hat", "Decal", ...). Those are
applied once the response says what type each asset is.

Every asset seen is appended to assets.jsonl so the GUI can show it.

Run with:  mitmdump -s proxion/addon.py --mode local:RobloxPlayerBeta
"""

from __future__ import annotations

import json
import mimetypes
import sys
import time
from pathlib import Path

from mitmproxy import http

# Make "import proxion" work when mitmdump loads this file directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from proxion import config as cfgmod  # noqa: E402

ASSET_HOST = "assetdelivery.roblox.com"
FILE_PREFIX = "/proxion-file/"
ASSET_TYPES = cfgmod.ASSET_TYPES


class Proxion:
    def __init__(self, compiler=None, log_file: Path | None = None):
        # compiler() returns a config.Compiled. Tests pass their own.
        self.compiler = compiler or cfgmod.compile_enabled
        self.log_file = log_file or cfgmod.log_path()
        self._stamp = None
        self._checked = 0.0
        self.rules = cfgmod.Compiled()
        self.files: dict[int, str] = {}  # key -> local path we promised to serve
        self.reload(force=True)

    # ---- rules ---------------------------------------------------------
    def _fingerprint(self):
        """mtimes of settings.json and every config, so edits apply live."""
        try:
            files = [cfgmod.settings_path(), *cfgmod.configs_dir().glob("*.json")]
            return tuple(sorted((str(f), f.stat().st_mtime_ns) for f in files if f.exists()))
        except OSError:
            return None

    def reload(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._checked < 0.5:
            return
        self._checked = now
        stamp = self._fingerprint() if self.compiler is cfgmod.compile_enabled else None
        if not force and stamp == self._stamp:
            return
        self._stamp = stamp
        try:
            self.rules = self.compiler()
        except Exception as e:  # a broken config must never kill the proxy
            print(f"[proxion] could not load configs: {e}")

    # ---- logging -------------------------------------------------------
    def _log(self, **entry) -> None:
        entry["time"] = time.time()
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            pass

    # ---- mitmproxy hooks -----------------------------------------------
    def request(self, flow: http.HTTPFlow) -> None:
        if flow.request.pretty_host != ASSET_HOST:
            return
        self.reload()
        path = flow.request.path
        base = path.split("?")[0].rstrip("/")

        if path.startswith(FILE_PREFIX):
            self._serve_file(flow)
        elif flow.request.method == "POST" and base == "/v1/assets/batch":
            self._rewrite_batch_request(flow)
        elif flow.request.method == "GET" and base == "/v1/asset":
            self._rewrite_single(flow)

    def response(self, flow: http.HTTPFlow) -> None:
        if flow.request.pretty_host != ASSET_HOST or flow.response is None:
            return
        batch = flow.metadata.get("proxion_batch")
        if batch is not None:
            self._rewrite_batch_response(flow, batch)

    # ---- batch endpoint ------------------------------------------------
    def _rewrite_batch_request(self, flow: http.HTTPFlow) -> None:
        try:
            items = json.loads(flow.request.get_text() or "[]")
        except (json.JSONDecodeError, ValueError):
            return
        if not isinstance(items, list):
            return

        tracked: dict[str, tuple[int, tuple | None]] = {}  # requestId -> (original id, action)
        changed = False
        for item in items:
            if not isinstance(item, dict) or "assetId" not in item:
                continue
            try:
                asset_id = int(item["assetId"])
            except (TypeError, ValueError):
                continue
            action = self.rules.by_id.get(asset_id)
            if action and action[0] == cfgmod.MODE_ID:
                item["assetId"] = action[1]
                changed = True
            tracked[str(item.get("requestId", ""))] = (asset_id, action)

        flow.metadata["proxion_batch"] = tracked
        if changed:
            flow.request.set_text(json.dumps(items))

    def _rewrite_batch_response(self, flow: http.HTTPFlow, tracked: dict) -> None:
        try:
            results = json.loads(flow.response.get_text() or "[]")
        except (json.JSONDecodeError, ValueError):
            return
        if not isinstance(results, list):
            return

        changed = False
        for res in results:
            if not isinstance(res, dict):
                continue
            original, action = tracked.get(str(res.get("requestId", "")), (None, None))
            type_id = res.get("assetTypeId")
            if action is None and isinstance(type_id, int):
                action = self.rules.by_type.get(type_id)  # whole-type rule
            if original is not None:
                self._log(assetId=original, typeId=type_id,
                          type=ASSET_TYPES.get(type_id, str(type_id) if type_id else "?"),
                          action=action[0] if action else "none",
                          replacement=action[1] if action else None)
            if not action or action[0] == cfgmod.MODE_ID:
                continue
            kind, value = action
            changed = True
            if kind == cfgmod.MODE_REMOVE:
                res.pop("locations", None)
                res["errors"] = [{"code": 404, "message": "Removed by Proxion"}]
            else:
                if kind == cfgmod.MODE_LOCAL:
                    key = original if original is not None else id(res)
                    self.files[key] = value
                    value = f"https://{ASSET_HOST}{FILE_PREFIX}{key}"
                res.pop("errors", None)
                res["locations"] = [{"assetFormat": "source", "location": value}]
        if changed:
            flow.response.set_text(json.dumps(results))

    # ---- legacy single asset endpoint ----------------------------------
    def _rewrite_single(self, flow: http.HTTPFlow) -> None:
        q = flow.request.query
        key = next((k for k in q.keys() if k.lower() == "id"), None)
        if key is None or not q[key].isdigit():
            return
        asset_id = int(q[key])
        action = self.rules.by_id.get(asset_id)
        self._log(assetId=asset_id, type="?", action=action[0] if action else "none",
                  replacement=action[1] if action else None)
        if not action:
            return
        kind, value = action
        if kind == cfgmod.MODE_ID:
            q[key] = str(value)
        elif kind == cfgmod.MODE_REMOVE:
            flow.response = http.Response.make(404, b"Removed by Proxion")
        else:
            if kind == cfgmod.MODE_LOCAL:
                self.files[asset_id] = value
                value = f"https://{ASSET_HOST}{FILE_PREFIX}{asset_id}"
            flow.response = http.Response.make(302, b"", {"Location": value})

    # ---- local files ---------------------------------------------------
    def _serve_file(self, flow: http.HTTPFlow) -> None:
        raw = flow.request.path[len(FILE_PREFIX):].split("?")[0]
        path = self.files.get(int(raw)) if raw.isdigit() else None
        if path is None:
            flow.response = http.Response.make(404, b"Unknown Proxion file")
            return
        try:
            data = Path(path).read_bytes()
        except OSError as e:
            flow.response = http.Response.make(404, f"Proxion could not read file: {e}".encode())
            return
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        flow.response = http.Response.make(200, data, {"Content-Type": ctype})


addons = [Proxion()] if "pytest" not in sys.modules else []
