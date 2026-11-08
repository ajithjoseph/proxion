"""mitmproxy addon that does the actual asset swapping.

How Roblox loads assets: the client POSTs a JSON list to
https://assetdelivery.roblox.com/v1/assets/batch like

    [{"assetId": 123, "requestId": "0", ...}, ...]

and gets back CDN locations for each one. Older code paths also use
GET /v1/asset?id=123 which redirects to the CDN.

Proxion hooks both:
  * "id" rules rewrite the assetId in the request, so Roblox is handed the
    replacement asset's CDN link instead.
  * "file" rules point the location at a fake path on assetdelivery that this
    addon answers itself with the bytes of a local file.
  * "remove" rules answer with a 404 style error for that asset.

Every asset seen is appended to assets.jsonl so the GUI can show it.

Run with:  mitmdump -s proxion/addon.py --mode local:RobloxPlayerBeta
"""

from __future__ import annotations

import json
import mimetypes
import os
import sys
import time
from pathlib import Path

from mitmproxy import http

# Make "import proxion" work when mitmdump loads this file directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from proxion import config as cfgmod  # noqa: E402

ASSET_HOST = "assetdelivery.roblox.com"
FILE_PREFIX = "/proxion-file/"

ASSET_TYPES = {
    1: "Image", 2: "TShirt", 3: "Audio", 4: "Mesh", 5: "Lua", 8: "Hat",
    10: "Model", 11: "Shirt", 12: "Pants", 13: "Decal", 17: "Head",
    18: "Face", 19: "Gear", 24: "Animation", 38: "Plugin", 39: "SolidModel",
    40: "MeshPart", 41: "HairAccessory", 61: "EmoteAnimation", 62: "Video",
    63: "TexturePack", 73: "FontFamily",
}


class Proxion:
    def __init__(self, config_file: Path | None = None, log_file: Path | None = None):
        self.config_file = config_file or cfgmod.config_path()
        self.log_file = log_file or cfgmod.log_path()
        self._mtime = -1.0
        self.id_map: dict[int, int] = {}
        self.file_map: dict[int, str] = {}
        self.remove: set[int] = set()
        self.reload()

    # ---- rules ---------------------------------------------------------
    def reload(self, force: bool = False) -> None:
        """Re-read config.json if it changed, so edits apply without a restart."""
        try:
            mtime = self.config_file.stat().st_mtime
        except FileNotFoundError:
            mtime = 0.0
        if not force and mtime == self._mtime:
            return
        self._mtime = mtime
        cfg = cfgmod.load(self.config_file)
        id_map, file_map, remove = {}, {}, set()
        for rule in cfg.rules:
            if not rule.enabled:
                continue
            for target in rule.targets:
                if rule.mode == cfgmod.MODE_ID and rule.replacement.strip().isdigit():
                    id_map[target] = int(rule.replacement)
                elif rule.mode == cfgmod.MODE_FILE and rule.replacement:
                    file_map[target] = rule.replacement
                elif rule.mode == cfgmod.MODE_REMOVE:
                    remove.add(target)
        self.id_map, self.file_map, self.remove = id_map, file_map, remove

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

        if path.startswith(FILE_PREFIX):
            self._serve_file(flow)
        elif flow.request.method == "POST" and path.split("?")[0].rstrip("/") == "/v1/assets/batch":
            self._rewrite_batch_request(flow)
        elif flow.request.method == "GET" and path.split("?")[0].rstrip("/") == "/v1/asset":
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

        # requestId -> (original id, action, value)
        tracked: dict[str, tuple[int, str, object]] = {}
        changed = False
        for item in items:
            if not isinstance(item, dict) or "assetId" not in item:
                continue
            try:
                asset_id = int(item["assetId"])
            except (TypeError, ValueError):
                continue
            req_id = str(item.get("requestId", ""))
            action = None
            if asset_id in self.remove:
                action = ("remove", None)
            elif asset_id in self.file_map:
                action = ("file", self.file_map[asset_id])
            elif asset_id in self.id_map:
                item["assetId"] = self.id_map[asset_id]
                changed = True
                action = ("id", self.id_map[asset_id])
            tracked[req_id] = (asset_id, *(action or ("none", None)))

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
            req_id = str(res.get("requestId", ""))
            original, action, value = tracked.get(req_id, (None, "none", None))
            type_id = res.get("assetTypeId")
            if original is not None:
                self._log(
                    assetId=original,
                    typeId=type_id,
                    type=ASSET_TYPES.get(type_id, str(type_id) if type_id else "?"),
                    action=action,
                    replacement=value,
                )
            if action == "remove":
                res.pop("locations", None)
                res["errors"] = [{"code": 404, "message": "Removed by Proxion"}]
                changed = True
            elif action == "file":
                url = f"https://{ASSET_HOST}{FILE_PREFIX}{original}"
                res.pop("errors", None)
                res["locations"] = [{"assetFormat": "source", "location": url}]
                changed = True
        if changed:
            flow.response.set_text(json.dumps(results))

    # ---- legacy single asset endpoint ----------------------------------
    def _rewrite_single(self, flow: http.HTTPFlow) -> None:
        q = flow.request.query
        key = next((k for k in q.keys() if k.lower() == "id"), None)
        if key is None or not q[key].isdigit():
            return
        asset_id = int(q[key])
        if asset_id in self.remove:
            self._log(assetId=asset_id, type="?", action="remove", replacement=None)
            flow.response = http.Response.make(404, b"Removed by Proxion")
        elif asset_id in self.file_map:
            self._log(assetId=asset_id, type="?", action="file", replacement=self.file_map[asset_id])
            flow.response = http.Response.make(
                302, b"", {"Location": f"https://{ASSET_HOST}{FILE_PREFIX}{asset_id}"}
            )
        elif asset_id in self.id_map:
            self._log(assetId=asset_id, type="?", action="id", replacement=self.id_map[asset_id])
            q[key] = str(self.id_map[asset_id])
        else:
            self._log(assetId=asset_id, type="?", action="none", replacement=None)

    # ---- local files ---------------------------------------------------
    def _serve_file(self, flow: http.HTTPFlow) -> None:
        raw = flow.request.path[len(FILE_PREFIX):].split("?")[0]
        if not raw.isdigit() or int(raw) not in self.file_map:
            flow.response = http.Response.make(404, b"Unknown Proxion file")
            return
        path = os.path.expandvars(os.path.expanduser(self.file_map[int(raw)]))
        try:
            data = Path(path).read_bytes()
        except OSError as e:
            flow.response = http.Response.make(404, f"Proxion could not read file: {e}".encode())
            return
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        flow.response = http.Response.make(200, data, {"Content-Type": ctype})


addons = [Proxion()] if __name__ != "__main__" and "pytest" not in sys.modules else []
