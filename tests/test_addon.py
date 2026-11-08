import json

import pytest
from mitmproxy import http
from mitmproxy.test import tflow, tutils

from proxion import config as cfgmod
from proxion.addon import FILE_PREFIX, Proxion


@pytest.fixture
def make(tmp_path):
    def _make(rules):
        cfg_file = tmp_path / "config.json"
        cfgmod.save(cfgmod.Config(rules=[cfgmod.Rule(**r) for r in rules]), cfg_file)
        return Proxion(cfg_file, tmp_path / "log.jsonl")
    return _make


def batch_flow(items):
    req = tutils.treq(host="assetdelivery.roblox.com", port=443, scheme=b"https",
                      method=b"POST", path=b"/v1/assets/batch",
                      content=json.dumps(items).encode())
    return tflow.tflow(req=req)


def respond(flow, results):
    flow.response = http.Response.make(200, json.dumps(results).encode(), {"Content-Type": "application/json"})


def test_id_swap_rewrites_request(make):
    p = make([{"targets": [111], "mode": "id", "replacement": "999"}])
    f = batch_flow([{"assetId": 111, "requestId": "0"}, {"assetId": 222, "requestId": "1"}])
    p.request(f)
    sent = json.loads(f.request.get_text())
    assert sent[0]["assetId"] == 999
    assert sent[1]["assetId"] == 222


def test_remove_returns_error(make):
    p = make([{"targets": [111], "mode": "remove"}])
    f = batch_flow([{"assetId": 111, "requestId": "a"}])
    p.request(f)
    respond(f, [{"requestId": "a", "assetTypeId": 1, "locations": [{"location": "https://c0.rbxcdn.com/x"}]}])
    p.response(f)
    out = json.loads(f.response.get_text())
    assert "locations" not in out[0]
    assert out[0]["errors"][0]["code"] == 404


def test_file_rule_points_to_local_and_serves_bytes(make, tmp_path):
    img = tmp_path / "sky.png"
    img.write_bytes(b"\x89PNGfake")
    p = make([{"targets": [111], "mode": "file", "replacement": str(img)}])
    f = batch_flow([{"assetId": 111, "requestId": "0"}])
    p.request(f)
    respond(f, [{"requestId": "0", "assetTypeId": 1, "locations": [{"location": "https://c0.rbxcdn.com/x"}]}])
    p.response(f)
    loc = json.loads(f.response.get_text())[0]["locations"][0]["location"]
    assert loc == f"https://assetdelivery.roblox.com{FILE_PREFIX}111"

    g = tflow.tflow(req=tutils.treq(host="assetdelivery.roblox.com", port=443, scheme=b"https",
                                    method=b"GET", path=f"{FILE_PREFIX}111".encode()))
    p.request(g)
    assert g.response.status_code == 200
    assert g.response.content == b"\x89PNGfake"
    assert g.response.headers["Content-Type"] == "image/png"


def test_logs_seen_assets(make, tmp_path):
    p = make([])
    f = batch_flow([{"assetId": 5, "requestId": "0"}])
    p.request(f)
    respond(f, [{"requestId": "0", "assetTypeId": 3, "locations": []}])
    p.response(f)
    entry = json.loads((tmp_path / "log.jsonl").read_text().splitlines()[0])
    assert entry["assetId"] == 5 and entry["type"] == "Audio" and entry["action"] == "none"


def test_disabled_rule_ignored(make):
    p = make([{"targets": [111], "mode": "id", "replacement": "999", "enabled": False}])
    f = batch_flow([{"assetId": 111, "requestId": "0"}])
    p.request(f)
    assert json.loads(f.request.get_text())[0]["assetId"] == 111


def test_single_asset_endpoint(make):
    p = make([{"targets": [111], "mode": "id", "replacement": "999"}])
    f = tflow.tflow(req=tutils.treq(host="assetdelivery.roblox.com", port=443, scheme=b"https",
                                    method=b"GET", path=b"/v1/asset/?id=111"))
    p.request(f)
    assert f.request.query["id"] == "999"


def test_config_reload_on_change(make, tmp_path):
    p = make([])
    import os, time
    cfgmod.save(cfgmod.Config(rules=[cfgmod.Rule(targets=[1], mode="id", replacement="2")]), tmp_path / "config.json")
    os.utime(tmp_path / "config.json", (time.time() + 5, time.time() + 5))
    f = batch_flow([{"assetId": 1, "requestId": "0"}])
    p.request(f)
    assert json.loads(f.request.get_text())[0]["assetId"] == 2


def test_other_hosts_untouched(make):
    p = make([{"targets": [111], "mode": "id", "replacement": "999"}])
    body = json.dumps([{"assetId": 111}]).encode()
    f = tflow.tflow(req=tutils.treq(host="example.com", method=b"POST", path=b"/v1/assets/batch", content=body))
    p.request(f)
    assert f.request.content == body
