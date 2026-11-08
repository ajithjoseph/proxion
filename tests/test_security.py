"""Regression tests for the security review fixes."""

import json

import pytest
from mitmproxy.test import tflow, tutils

from proxion import config as cfgmod
from proxion import proxy
from proxion.addon import FILE_PREFIX, Proxion


def enable(rules, name="Test"):
    cfgmod.write_config(name, {"replacement_rules": rules})
    s = cfgmod.load_settings()
    s.enabled_configs = [name]
    cfgmod.save_settings(s)


# ---- proxy command -------------------------------------------------------------
def test_regular_mode_listens_on_localhost_only():
    s = cfgmod.Settings(proxy_mode="regular", proxy_port=8080)
    cmd = proxy.build_command(s)
    assert "listen_host=127.0.0.1" in cmd


def test_only_asset_host_is_intercepted():
    cmd = proxy.build_command(cfgmod.Settings())
    allow = next(a for a in cmd if a.startswith("allow_hosts="))
    import re

    rx = allow.split("=", 1)[1]
    assert re.search(rx, "assetdelivery.roblox.com:443")
    assert not re.search(rx, "auth.roblox.com:443")
    assert not re.search(rx, "assetdelivery.roblox.com.evil.com:443")


@pytest.mark.parametrize("bad", ["Roblox; calc", "a" * 100, "x\nnewline"])
def test_bad_process_name_rejected(bad):
    with pytest.raises(ValueError):
        proxy.build_command(cfgmod.Settings(capture_process=bad))


# ---- configs from strangers ----------------------------------------------------
@pytest.mark.parametrize(
    "path",
    [r"\\attacker\share\a.png", "//attacker/share/a.png", r"\\.\PhysicalDrive0", r"%USERPROFILE%\a.png", "NUL"],
)
def test_dangerous_local_paths_are_ignored(path):
    c = cfgmod.compile_rules([{"replacement_rules": [{"replace_ids": [111111], "mode": "local", "local_path": path}]}])
    assert 111111 not in c.by_id
    assert c.problems


@pytest.mark.parametrize(
    "url",
    ["http://example.com/a.png", "https://127.0.0.1/a", "https://localhost/a", "https://10.0.0.5/a", "file:///C:/x"],
)
def test_dangerous_urls_are_ignored(url):
    c = cfgmod.compile_rules([{"replacement_rules": [{"replace_ids": [111111], "mode": "cdn", "cdn_url": url}]}])
    assert 111111 not in c.by_id


def test_unicode_and_huge_digit_ids_do_not_crash():
    rules = [
        {"replace_ids": ["²", "9" * 5000, 111111], "mode": "id", "with_id": "²"},
        {"replace_ids": ["²", 222222], "mode": "id", "with_id": 333333},
        {"replace_ids": 444444, "mode": "remove"},  # not even a list
    ]
    c = cfgmod.compile_rules([{"replacement_rules": rules}])
    assert 111111 not in c.by_id  # broken with_id: rule ignored, not crashed
    assert c.by_id[222222] == ("id", 333333)
    assert c.by_id[444444] == ("remove", None)


def test_deeply_nested_config_rejected(tmp_path):
    src = tmp_path / "deep.json"
    src.write_text("[" * 100000 + "]" * 100000)
    with pytest.raises(ValueError):
        cfgmod.import_config(src)


def test_huge_file_rejected(tmp_path):
    src = tmp_path / "big.json"
    with open(src, "wb") as f:
        f.seek(cfgmod.MAX_CONFIG_BYTES + 1)
        f.write(b"\0")
    with pytest.raises(ValueError):
        cfgmod.import_config(src)


@pytest.mark.parametrize("stem", ["CON", "nul", "COM1", "lpt9"])
def test_windows_device_names_not_used_for_configs(tmp_path, stem):
    src = tmp_path / f"{stem}.json"
    src.write_text("[]")
    name = cfgmod.import_config(src)
    assert name.lower() != stem.lower()
    with pytest.raises(ValueError):
        cfgmod.check_name(stem)


def test_review_lists_outside_files_and_hosts():
    data = {
        "replacement_rules": [
            {"replace_ids": [111111], "mode": "local", "local_path": r"C:\Users\me\secret.png"},
            {"replace_ids": [222222], "mode": "cdn", "cdn_url": "https://tracker.example/x.png"},
            {"replace_ids": [333333], "mode": "local", "local_path": "/Pack/ok.png"},
        ]
    }
    notes = "\n".join(cfgmod.review_config(data))
    assert "secret.png" in notes and "tracker.example" in notes and "ok.png" not in notes


# ---- file serving --------------------------------------------------------------
def _batch(p, asset_id):
    f = tflow.tflow(
        req=tutils.treq(
            host="assetdelivery.roblox.com",
            port=443,
            scheme=b"https",
            method=b"POST",
            path=b"/v1/assets/batch",
            content=json.dumps([{"assetId": asset_id, "requestId": "0"}]).encode(),
        )
    )
    p.request(f)
    from mitmproxy import http

    f.response = http.Response.make(200, json.dumps([{"requestId": "0", "assetTypeId": 1, "locations": []}]).encode())
    p.response(f)
    return json.loads(f.response.get_text())[0]["locations"][0]["location"]


def _get(p, url, scheme=b"https", method=b"GET"):
    path = url.split("roblox.com", 1)[1].encode()
    g = tflow.tflow(req=tutils.treq(host="assetdelivery.roblox.com", port=443, scheme=scheme, method=method, path=path))
    p.request(g)
    return g.response


def test_file_urls_use_random_tokens_and_https_get_only(tmp_path):
    f = tmp_path / "a.png"
    f.write_bytes(b"PNG")
    enable([{"replace_ids": [111111], "mode": "local", "local_path": str(f)}])
    p = Proxion(log_file=tmp_path / "log.jsonl")
    url = _batch(p, 111111)
    assert "111111" not in url and url.startswith(f"https://assetdelivery.roblox.com{FILE_PREFIX}")
    assert _get(p, url).content == b"PNG"
    assert _get(p, url, scheme=b"http").status_code == 404
    assert _get(p, url, method=b"POST").status_code == 404
    assert _get(p, f"https://assetdelivery.roblox.com{FILE_PREFIX}111111").status_code == 404
    assert _batch(p, 111111) == url  # same file, same token: the map doesn't grow


def test_directories_are_not_served(tmp_path):
    enable([{"replace_ids": [111111], "mode": "local", "local_path": str(tmp_path)}])
    p = Proxion(log_file=tmp_path / "log.jsonl")
    assert _get(p, _batch(p, 111111)).status_code == 404


def test_log_rotates(tmp_path, monkeypatch):
    import proxion.addon as addon_mod

    monkeypatch.setattr(addon_mod, "MAX_LOG_BYTES", 1000)
    enable([])
    log = tmp_path / "log.jsonl"
    p = Proxion(log_file=log)
    for i in range(1000):
        p._log(assetId=i)
    assert log.stat().st_size < 50_000
    assert (tmp_path / "log.jsonl.1").exists()
