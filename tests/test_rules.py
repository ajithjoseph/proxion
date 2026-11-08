import pytest

from proxion import config as cfgmod
from proxion import rules


# ---- Replace With parsing (same detection as Fleasion) -------------------------
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", ("remove", None)),
        ("  remove ", ("remove", None)),
        ("123456789", ("id", 123456789)),
        ("https://raw.githubusercontent.com/a/b/font.ttf", ("cdn", "https://raw.githubusercontent.com/a/b/font.ttf")),
    ],
)
def test_parse_replacement(text, expected):
    assert rules.parse_replacement(text) == expected


@pytest.mark.parametrize("text", ["1", "0", "http://insecure.com/x", "https://127.0.0.1/x", "hello", r"\\evil\x.png"])
def test_parse_replacement_rejects(text):
    with pytest.raises(ValueError):
        rules.parse_replacement(text)


def test_parse_replacement_files(tmp_path):
    f = tmp_path / "sky.png"
    f.write_bytes(b"x")
    assert rules.parse_replacement(str(f)) == ("local", str(f))
    with pytest.raises(ValueError, match="not found"):
        rules.parse_replacement(str(tmp_path / "missing.png"))
    inside = cfgmod.configs_dir() / "Pack" / "a.png"
    inside.parent.mkdir()
    inside.write_bytes(b"x")
    assert rules.parse_replacement(str(inside)) == ("local", "/Pack/a.png")  # stored Fleasion style


def test_split_and_join_targets():
    assert rules.split_targets("123456, hat;  decal 789012") == [123456, "Hat", "Decal", 789012]
    assert rules.join_targets([1, "Hat"]) == "1, Hat"


def test_asset_type_categories_are_real_types():
    for names in rules.ASSET_TYPE_CATEGORIES.values():
        for n in names:
            assert cfgmod.parse_target(n) is not None, n


# ---- table labels --------------------------------------------------------------
def test_row_values():
    assert rules.row_values({"replace_ids": [111111, 222222], "mode": "id", "with_id": 9}) == (
        "On",
        "ID",
        "2 IDs",
        "9",
    )
    long = "https://example.com/" + "x" * 60
    assert rules.row_values({"replace_ids": [1], "mode": "cdn", "cdn_url": long, "enabled": False})[0::3] == (
        "Off",
        long[:37] + "...",
    )
    assert rules.row_values({"replace_ids": [1], "mode": "local", "local_path": "/Pack/sky.png"})[3] == "sky.png"
    assert rules.row_values({"replace_ids": [1], "mode": "id"})[1] == "Remove"
    group = {"type": "group", "children": [{"enabled": True}, {"enabled": False}]}
    assert rules.row_values(group)[:3] == ("—", "Group", "2 profiles")


# ---- tree edits ----------------------------------------------------------------
def tree():
    return [
        {"name": "a"},
        {"type": "group", "name": "G", "children": [{"name": "g1"}, {"name": "g2"}]},
        {"name": "b"},
        {"name": "c"},
    ]


def names(nodes):
    return [n.get("name") for n in nodes]


def test_remove_paths_handles_nested_and_order():
    t = tree()
    rules.remove_paths(t, [(0,), (1, 1), (3,)])
    assert names(t) == ["G", "b"] and names(t[0]["children"]) == ["g1"]
    t = tree()
    rules.remove_paths(t, [(1,), (1, 0)])  # child of a removed group is skipped
    assert names(t) == ["a", "b", "c"]


def test_set_enabled_group_cascades():
    t = tree()
    rules.set_enabled(t, [(1,)], False)
    assert t[1]["enabled"] is False and all(c["enabled"] is False for c in t[1]["children"])


def test_create_group():
    t = tree()
    new = rules.create_group(t, [(2,), (3,)], "BC")
    assert new == (2,) and names(t) == ["a", "G", "BC"] and names(t[2]["children"]) == ["b", "c"]
    with pytest.raises(ValueError):
        rules.create_group(tree(), [(0,), (1, 0)], "x")


@pytest.mark.parametrize(
    ("src", "dest", "index", "top", "inside"),
    [
        ((0,), (), 4, ["G", "b", "c", "a"], ["g1", "g2"]),  # to the end
        ((3,), (), 0, ["c", "a", "G", "b"], ["g1", "g2"]),  # to the top
        ((0,), (1,), 2, ["G", "b", "c"], ["g1", "g2", "a"]),  # into a later group
        ((1, 0), (), 0, ["g1", "a", "G", "b", "c"], ["g2"]),  # out of a group
        ((3,), (1,), 0, ["a", "G", "b"], ["c", "g1", "g2"]),  # into an earlier group
    ],
)
def test_move_node(src, dest, index, top, inside):
    t = tree()
    new = rules.move_node(t, src, dest, index)
    assert names(t) == top
    group = next(n for n in t if n.get("type") == "group")
    assert names(group["children"]) == inside
    assert rules.node_at(t, new) is not None


def test_move_group_into_itself_refused():
    with pytest.raises(ValueError):
        rules.move_node(tree(), (1,), (1,), 0)


def test_apply_fields_keeps_enabled_and_unknown_keys():
    r = {"name": "x", "replace_ids": [1], "mode": "id", "with_id": 5, "enabled": False, "custom": 1}
    rules.apply_fields(r, "y", [2], "cdn", "https://example.com/a")
    assert r == {
        "name": "y",
        "replace_ids": [2],
        "mode": "cdn",
        "cdn_url": "https://example.com/a",
        "enabled": False,
        "custom": 1,
    }


# ---- undo ----------------------------------------------------------------------
def test_undo_redo():
    u = rules.UndoStack(limit=3)
    state = [1]
    for v in (2, 3, 4, 5):
        u.push(state)
        state = [*state, v]
    assert state == [1, 2, 3, 4, 5]
    state = u.undo(state)
    assert state == [1, 2, 3, 4]
    state = u.redo(state)
    assert state == [1, 2, 3, 4, 5]
    for _ in range(3):
        state = u.undo(state)
    assert state == [1, 2] and u.undo(state) is None  # only 3 levels kept
    u.push(state)
    assert not u.can_redo  # a new change clears redo
