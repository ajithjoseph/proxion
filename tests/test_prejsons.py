import json

import pytest

from proxion import prejsons

CLOG = {
    "games": {
        "Arsenal": {
            "Owner": "Sky",
            "id": 286090429,
            "github": "https://raw.githubusercontent.com/x/ORIGINAL.json",
            "replacement": "https://raw.githubusercontent.com/x/REPLACEMENT.json",
        },
        "Prison Life": {
            "Owner": "Sky",
            "id": 155615604,
            "github": "https://a.example/o.json",
            "Replacement": "https://a.example/r.json",
        },
        "T4T Modpack": {"Owner": "T4T", "id": None, "github": None, "Replacement": "https://b.example/r.json"},
        "Evil": {
            "Owner": "x",
            "id": "²",
            "github": "http://insecure.example/o.json",
            "replacement": "file:///etc/passwd",
        },
        "Broken": "not a dict",
    }
}


def test_parse_clog():
    games = {g.name: g for g in prejsons.parse_clog(CLOG)}
    assert set(games) == {"Arsenal", "Prison Life", "T4T Modpack", "Evil"}
    assert games["Arsenal"].place_id == 286090429 and games["Arsenal"].owner == "Sky"
    assert games["Prison Life"].replacements_url == "https://a.example/r.json"  # capital R works
    assert games["T4T Modpack"].assets_url is None and games["T4T Modpack"].place_id is None
    assert (
        games["Evil"].assets_url is None and games["Evil"].replacements_url is None and games["Evil"].place_id is None
    )


def test_leaf_values_and_ids():
    dump = {"gunsounds": {"Pistols": {"Deagle": {"Fire1": "14861034952", "Fire2": "7656488588"}}}, "x": [5, True, None]}
    leaves = prejsons.leaf_values(dump["gunsounds"])
    assert leaves == ["14861034952", "7656488588"]
    assert prejsons.asset_ids([*leaves, "14861034952", "5", "abc", "²"]) == [14861034952, 7656488588]


def test_fetch_json_caches_and_falls_back():
    calls = []

    def ok(url):
        calls.append(url)
        return json.dumps(CLOG).encode()

    def offline(url):
        raise OSError("no network")

    data, cached = prejsons.fetch_json("https://example.com/c.json", downloader=ok)
    assert not cached and "games" in data
    data, cached = prejsons.fetch_json("https://example.com/c.json", downloader=offline)
    assert cached and "games" in data
    with pytest.raises(OSError):
        prejsons.fetch_json("https://example.com/other.json", downloader=offline)


def test_download_refuses_bad_urls():
    for url in ("http://example.com/x", "https://localhost/x", "file:///etc/passwd"):
        with pytest.raises(ValueError):
            prejsons.download(url)
