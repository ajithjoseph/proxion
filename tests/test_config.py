import json

import pytest

from proxion import config as cfgmod

FLEASION = {
    "replacement_rules": [
        {
            "name": "Sword texture",
            "replace_ids": [123456789, "7547298786:1"],
            "mode": "id",
            "with_id": 987654321,
            "enabled": True,
        },
        {"name": "Hide hats", "replace_ids": ["Hat"], "mode": "remove", "enabled": True},
        {
            "type": "group",
            "name": "Folder",
            "expanded": True,
            "children": [
                {
                    "name": "Custom mesh",
                    "replace_ids": [111111],
                    "mode": "local",
                    "local_path": "/StickObj/stick.obj",
                    "enabled": True,
                },
            ],
        },
    ]
}


def test_import_fleasion_config_utf16(tmp_path):
    src = tmp_path / "Phantom Forces.json"
    src.write_bytes(json.dumps(FLEASION).encode("utf-16"))  # Notepad style file
    name = cfgmod.import_config(src)
    assert name == "Phantom Forces"
    data = cfgmod.read_config(name)
    assert data == FLEASION
    c = cfgmod.compile_rules([data])
    assert c.by_id[123456789] == ("id", 987654321)
    assert c.by_type[8] == ("remove", None)
    assert c.by_id[111111][0] == "local"
    assert c.by_id[111111][1].endswith("stick.obj")
    assert c.skipped == 1  # the slot key


def test_import_bare_list_and_name_clash(tmp_path):
    src = tmp_path / "x.json"
    src.write_text(json.dumps([{"replace_ids": [111111], "mode": "remove"}]))
    assert cfgmod.import_config(src) == "x"
    assert cfgmod.import_config(src) == "x (2)"
    assert cfgmod.read_config("x")["replacement_rules"][0]["mode"] == "remove"


def test_import_rejects_garbage(tmp_path):
    src = tmp_path / "bad.json"
    src.write_bytes(b"\x00\x01not json at all")
    with pytest.raises(ValueError):
        cfgmod.import_config(src)


def test_config_management():
    s = cfgmod.load_settings()
    assert cfgmod.list_configs() == ["Default"]
    cfgmod.create_config("PF")
    s.enabled_configs = ["Default", "PF"]
    new = cfgmod.rename_config("PF", "Phantom", s)
    assert new == "Phantom" and s.enabled_configs == ["Default", "Phantom"]
    dup = cfgmod.duplicate_config("Phantom")
    assert dup == "Phantom copy"
    with pytest.raises(ValueError):
        cfgmod.create_config("bad/name")
    cfgmod.delete_config("Phantom", s)
    assert "Phantom" not in s.enabled_configs


def test_migrates_old_proxion_rules(home):
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.json").write_text(
        json.dumps(
            {
                "rules": [
                    {"name": "sky", "targets": [111111], "mode": "id", "replacement": "999999"},
                    {"name": "f", "targets": [222222], "mode": "file", "replacement": "C:/a.png"},
                ],
                "proxy_port": 9000,
            }
        )
    )
    s = cfgmod.load_settings()
    assert s.proxy_port == 9000
    rules = cfgmod.read_config("Default")["replacement_rules"]
    assert rules[0]["with_id"] == "999999" and rules[1]["local_path"] == "C:/a.png"
    assert cfgmod.compile_enabled(s).by_id[111111] == ("id", 999999)
