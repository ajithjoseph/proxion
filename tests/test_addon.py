import json

import pytest
from mitmproxy import http
from mitmproxy.test import tflow, tutils

from proxion import config as cfgmod
from proxion.addon import FILE_PREFIX, Proxion


@pytest.fixture
def make(tmp_path):
    def _make(rules, name="Test"):
        cfgmod.write_config(name, {"replacement_rules": rules})
        s = cfgmod.load_settings()
        s.enabled_configs = [name]
        cfgmod.save_settings(s)
        return Proxion(log_file=tmp_path / "log.jsonl")

    return _make


def batch_flow(items):
    req = tutils.treq(
        host="assetdelivery.roblox.com",
        port=443,
        scheme=b"https",
        method=b"POST",
        path=b"/v1/assets/batch",
        content=json.dumps(items).encode(),
    )
    return tflow.tflow(req=req)


def respond(flow, results):
    flow.response = http.Response.make(200, json.dumps(results).encode(), {"Content-Type": "application/json"})


def roundtrip(p, items, results):
    f = batch_flow(items)
    p.request(f)
    sent = json.loads(f.request.get_text())
    respond(f, results)
    p.response(f)
    return sent, json.loads(f.response.get_text())


def ok(req_id, type_id=1, loc="https://c0.rbxcdn.com/x"):
    return {"requestId": req_id, "assetTypeId": type_id, "locations": [{"assetFormat": "source", "location": loc}]}


def test_id_swap(make):
    p = make([{"replace_ids": [111111], "mode": "id", "with_id": 999999}])
    sent, _ = roundtrip(
        p, [{"assetId": 111111, "requestId": "0"}, {"assetId": 222222, "requestId": "1"}], [ok("0"), ok("1")]
    )
    assert [i["assetId"] for i in sent] == [999999, 222222]


def test_remove(make):
    p = make([{"replace_ids": [111111], "mode": "remove"}])
    _, out = roundtrip(p, [{"assetId": 111111, "requestId": "a"}], [ok("a")])
    assert "locations" not in out[0] and out[0]["errors"][0]["code"] == 404


def test_legacy_remove_flag_and_missing_with_id(make):
    p = make([{"replace_ids": [111111], "remove": True}, {"replace_ids": [222222], "mode": "id"}])
    _, out = roundtrip(
        p, [{"assetId": 111111, "requestId": "0"}, {"assetId": 222222, "requestId": "1"}], [ok("0"), ok("1")]
    )
    assert "errors" in out[0] and "errors" in out[1]


def test_cdn_url(make):
    p = make([{"replace_ids": ["111111"], "mode": "cdn", "cdn_url": "https://example.com/sky.png"}])
    _, out = roundtrip(p, [{"assetId": 111111, "requestId": "0"}], [ok("0")])
    assert out[0]["locations"][0]["location"] == "https://example.com/sky.png"


def test_local_file_served(make, home):
    folder = cfgmod.configs_dir() / "Sky"
    folder.mkdir()
    (folder / "sky.png").write_bytes(b"\x89PNGfake")
    p = make([{"replace_ids": [111111], "mode": "local", "local_path": "/Sky/sky.png"}])  # Fleasion relative path
    _, out = roundtrip(p, [{"assetId": 111111, "requestId": "0"}], [ok("0")])
    location = out[0]["locations"][0]["location"]
    assert location.startswith(f"https://assetdelivery.roblox.com{FILE_PREFIX}")
    g = tflow.tflow(
        req=tutils.treq(
            host="assetdelivery.roblox.com",
            port=443,
            scheme=b"https",
            method=b"GET",
            path=location.split("roblox.com", 1)[1].encode(),
        )
    )
    p.request(g)
    assert g.response.status_code == 200 and g.response.content == b"\x89PNGfake"
    assert g.response.headers["Content-Type"] == "image/png"


def test_type_rule_removes_all_hats(make):
    p = make([{"replace_ids": ["Hat"], "mode": "remove"}])
    _, out = roundtrip(
        p,
        [{"assetId": 111111, "requestId": "0"}, {"assetId": 222222, "requestId": "1"}],
        [ok("0", type_id=8), ok("1", type_id=1)],
    )
    assert "errors" in out[0] and "locations" in out[1]


def test_groups_and_disabled(make):
    p = make(
        [
            {"type": "group", "name": "G", "children": [{"replace_ids": [111111], "mode": "id", "with_id": 999999}]},
            {
                "type": "group",
                "name": "Off",
                "enabled": False,
                "children": [{"replace_ids": [222222], "mode": "remove"}],
            },
            {"replace_ids": [333333], "mode": "remove", "enabled": False},
        ]
    )
    sent, out = roundtrip(
        p,
        [{"assetId": a, "requestId": str(i)} for i, a in enumerate((111111, 222222, 333333))],
        [ok("0"), ok("1"), ok("2")],
    )
    assert sent[0]["assetId"] == 999999
    assert all("locations" in r for r in out)


def test_only_enabled_configs_used(make):
    cfgmod.write_config("Other", {"replacement_rules": [{"replace_ids": [222222], "mode": "remove"}]})
    p = make([])
    _, out = roundtrip(p, [{"assetId": 222222, "requestId": "0"}], [ok("0")])
    assert "locations" in out[0]


def test_later_config_wins(make):
    cfgmod.write_config("A", {"replacement_rules": [{"replace_ids": [111111], "mode": "id", "with_id": 1000001}]})
    cfgmod.write_config("B", {"replacement_rules": [{"replace_ids": [111111], "mode": "id", "with_id": 1000002}]})
    s = cfgmod.load_settings()
    s.enabled_configs = ["A", "B"]
    cfgmod.save_settings(s)
    p = Proxion()
    sent, _ = roundtrip(p, [{"assetId": 111111, "requestId": "0"}], [ok("0")])
    assert sent[0]["assetId"] == 1000002


def test_live_reload(make):
    import os
    import time

    p = make([])
    cfgmod.write_config("Test", {"replacement_rules": [{"replace_ids": [111111], "mode": "id", "with_id": 999999}]})
    f = cfgmod.config_file("Test")
    os.utime(f, (time.time() + 5, time.time() + 5))
    p._checked = 0
    sent, _ = roundtrip(p, [{"assetId": 111111, "requestId": "0"}], [ok("0")])
    assert sent[0]["assetId"] == 999999


def test_logs_seen_assets(make, tmp_path):
    p = make([])
    roundtrip(p, [{"assetId": 555555, "requestId": "0"}], [ok("0", type_id=3)])
    entry = json.loads((tmp_path / "log.jsonl").read_text().splitlines()[0])
    assert entry["assetId"] == 555555 and entry["type"] == "Audio" and entry["action"] == "none"


def test_single_asset_endpoint(make):
    p = make([{"replace_ids": [111111], "mode": "id", "with_id": 999999}])
    f = tflow.tflow(
        req=tutils.treq(
            host="assetdelivery.roblox.com", port=443, scheme=b"https", method=b"GET", path=b"/v1/asset/?id=111111"
        )
    )
    p.request(f)
    assert f.request.query["id"] == "999999"


def test_other_hosts_untouched(make):
    p = make([{"replace_ids": [111111], "mode": "id", "with_id": 999999}])
    body = json.dumps([{"assetId": 111111}]).encode()
    f = tflow.tflow(req=tutils.treq(host="example.com", method=b"POST", path=b"/v1/assets/batch", content=body))
    p.request(f)
    assert f.request.content == body


def test_broken_config_does_not_crash(make):
    p = make([])
    cfgmod.config_file("Test").write_text("{not json")
    p._checked = 0
    p.reload(force=True)
    roundtrip(p, [{"assetId": 111111, "requestId": "0"}], [ok("0")])
