"""Rule editing logic used by the Replacer tab, kept free of tkinter so it can be tested.

Covers: turning the "Replace With" text into a rule (same rules as Fleasion), table labels,
tree edits (groups, moves, enable/disable) and the undo/redo stack.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Iterable
from pathlib import Path

from . import config as cfgmod

Path_ = tuple[int, ...]  # index path into the rule tree, like (2, 0)

# Asset Types popup, grouped like Fleasion. Only types Proxion can actually match are listed.
ASSET_TYPE_CATEGORIES: dict[str, list[str]] = {
    "3D Models": ["Mesh", "MeshPart", "Model", "Package"],
    "Images / Textures": ["Image", "Decal", "TexturePack", "Face"],
    "Audio / Video": ["Audio", "Video"],
    "Animations": [
        "Animation",
        "EmoteAnimation",
        "IdleAnimation",
        "WalkAnimation",
        "RunAnimation",
        "JumpAnimation",
        "FallAnimation",
        "ClimbAnimation",
        "SwimAnimation",
        "DeathAnimation",
        "PoseAnimation",
        "MoodAnimation",
    ],
    "Avatar Parts": ["Head", "DynamicHead", "Torso", "LeftArm", "RightArm", "LeftLeg", "RightLeg"],
    "Clothing": [
        "TShirt",
        "Shirt",
        "Pants",
        "TShirtAccessory",
        "ShirtAccessory",
        "PantsAccessory",
        "JacketAccessory",
        "SweaterAccessory",
        "ShortsAccessory",
        "DressSkirtAccessory",
        "LeftShoeAccessory",
        "RightShoeAccessory",
    ],
    "Accessories": [
        "Hat",
        "HairAccessory",
        "FaceAccessory",
        "NeckAccessory",
        "ShoulderAccessory",
        "FrontAccessory",
        "BackAccessory",
        "WaistAccessory",
        "EyebrowAccessory",
        "EyelashAccessory",
        "Gear",
    ],
    "Scripts / Data": ["Lua", "Plugin", "FontFamily"],
}
ALL_TYPE_NAMES = {n.lower(): n for names in ASSET_TYPE_CATEGORIES.values() for n in names}
_SPLIT = re.compile(r"[,\s;]+")
_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")


# ---------------------------------------------------------------- fields <-> rule
def split_targets(text: str) -> list:
    """'123, Hat; 456' -> [123, 'Hat', 456]. Type names get their proper capitalisation."""
    out = []
    for tok in _SPLIT.split(text.strip()):
        if not tok:
            continue
        n = cfgmod.as_asset_id(tok)
        out.append(n if n is not None else ALL_TYPE_NAMES.get(tok.lower(), tok))
    return out


def join_targets(targets) -> str:
    targets = targets if isinstance(targets, list) else [targets]
    return ", ".join(map(str, targets))


def looks_like_path(text: str) -> bool:
    return "/" in text or "\\" in text or bool(_DRIVE.match(text))


def parse_replacement(text: str, file_exists=lambda p: Path(p).is_file()) -> tuple[str, object]:
    """Work out the mode from what was typed, like Fleasion does.

    empty or "remove" -> remove, http(s) link -> cdn, a number -> id, a path -> local.
    Returns (mode, value). Raises ValueError with a message for the user.
    """
    t = text.strip()
    if not t or t.lower() == "remove":
        return (cfgmod.MODE_REMOVE, None)
    if t.lower().startswith(("http://", "https://")):
        problem = cfgmod.url_problem(t)
        if problem:
            raise ValueError(f"Can't use that link: {problem}.")
        return (cfgmod.MODE_CDN, t)
    n = cfgmod.as_asset_id(t)
    if n is not None:
        if n <= 1:
            raise ValueError("Asset IDs 0 and 1 aren't real assets.")
        return (cfgmod.MODE_ID, n)
    if looks_like_path(t):
        problem = cfgmod.local_path_problem(t)
        if problem:
            raise ValueError(f"Can't use that file: {problem}.")
        if not file_exists(cfgmod.resolve_local_path(t)):
            raise ValueError(f"File not found: {t}")
        return (cfgmod.MODE_LOCAL, storage_path(t))
    raise ValueError("Replace With must be an asset ID, an https:// link, a file path, or empty to remove.")


def storage_path(p: str) -> str:
    """Files inside the configs folder are stored Fleasion style ("/Folder/file.png") so configs stay portable."""
    try:
        rel = Path(p).resolve().relative_to(cfgmod.configs_dir().resolve())
    except (OSError, ValueError):
        return p
    return "/" + "/".join(rel.parts)


def replacement_text(rule: dict) -> str:
    """What goes back into the Replace With box for a rule."""
    mode = cfgmod.rule_mode(rule)
    value = {
        cfgmod.MODE_ID: rule.get("with_id"),
        cfgmod.MODE_LOCAL: rule.get("local_path"),
        cfgmod.MODE_CDN: rule.get("cdn_url"),
    }.get(mode)
    return "" if value is None else str(value)


def make_rule(name: str, targets: list, mode: str, value, enabled: bool = True) -> dict:
    rule = {"name": name, "replace_ids": targets, "mode": mode, "enabled": enabled}
    field = {cfgmod.MODE_ID: "with_id", cfgmod.MODE_LOCAL: "local_path", cfgmod.MODE_CDN: "cdn_url"}.get(mode)
    if field:
        rule[field] = value
    return rule


def apply_fields(rule: dict, name: str, targets: list, mode: str, value) -> None:
    """Update a rule in place, keeping its enabled state and any keys we don't know about."""
    for k in ("with_id", "local_path", "cdn_url", "remove"):
        rule.pop(k, None)
    rule.update({k: v for k, v in make_rule(name, targets, mode, value).items() if k != "enabled"})


# ---------------------------------------------------------------- table labels
MODE_LABELS = {
    cfgmod.MODE_ID: "ID",
    cfgmod.MODE_CDN: "CDN",
    cfgmod.MODE_LOCAL: "Local",
    cfgmod.MODE_REMOVE: "Remove",
}


def is_group(node: dict) -> bool:
    return node.get("type") == "group"


def is_on(node: dict) -> bool:
    return node.get("enabled", True) is not False


def leaf_rules(nodes: list) -> list[dict]:
    return [r for _, r, _ in cfgmod.iter_rules(nodes)]


def row_values(node: dict) -> tuple[str, str, str, str]:
    """(Status, Mode, Asset IDs, Replacement) for the profiles table."""
    if is_group(node):
        leaves = leaf_rules(node.get("children") or [])
        on = [is_on(r) for r in leaves]
        status = "On" if on and all(on) else "Off" if on and not any(on) else "—"
        if not is_on(node):
            status = "Off"
        return status, "Group", f"{len(leaves)} profile{'s' if len(leaves) != 1 else ''}", "-"
    targets = node.get("replace_ids") or []
    n = len(targets) if isinstance(targets, list) else 1
    kind, value = cfgmod.rule_action(node)
    if kind == cfgmod.INVALID:
        shown = f"(ignored: {value})"
    elif kind == cfgmod.MODE_REMOVE:
        shown = "-"
    elif kind == cfgmod.MODE_CDN:
        shown = value if len(value) <= 40 else value[:37] + "..."
    elif kind == cfgmod.MODE_LOCAL:
        shown = Path(str(node.get("local_path", value)).replace("\\", "/")).name
    else:
        shown = str(value)
    mode = "Remove" if kind == cfgmod.MODE_REMOVE else MODE_LABELS.get(cfgmod.rule_mode(node), "ID")
    return ("On" if is_on(node) else "Off"), mode, f"{n} ID{'s' if n != 1 else ''}", shown


# ---------------------------------------------------------------- tree edits
def node_at(rules: list, path: Path_) -> dict:
    items, node = rules, None
    for i in path:
        node = items[i]
        items = node.setdefault("children", []) if is_group(node) else []
    return node


def children_of(rules: list, parent: Path_) -> list:
    return node_at(rules, parent).setdefault("children", []) if parent else rules


def remove_paths(rules: list, paths: Iterable[Path_]) -> list[dict]:
    """Delete nodes. Deepest/last first so earlier indexes stay valid. Returns what was removed."""
    removed = []
    for p in sorted(set(paths), reverse=True):
        if any(p[: len(q)] == q and p != q for q in paths):
            continue  # already gone with its parent group
        removed.append(children_of(rules, p[:-1]).pop(p[-1]))
    return removed


def set_enabled(rules: list, paths: Iterable[Path_], on: bool) -> None:
    """Turn profiles on or off. For a group, all profiles inside it change too, like Fleasion."""
    for p in paths:
        node = node_at(rules, p)
        node["enabled"] = on
        if is_group(node):
            for leaf in leaf_rules(node.get("children") or []):
                leaf["enabled"] = on
            for _, sub, _ in _iter_groups(node.get("children") or []):
                sub["enabled"] = on


def _iter_groups(nodes: list):
    for i, n in enumerate(nodes):
        if isinstance(n, dict) and is_group(n):
            yield i, n, None
            yield from _iter_groups(n.get("children") or [])


def create_group(rules: list, paths: list[Path_], name: str) -> Path_:
    """Put the selected siblings into a new group placed where the first one was."""
    parents = {p[:-1] for p in paths}
    if len(parents) != 1:
        raise ValueError("Pick profiles from the same level to group them.")
    parent = parents.pop()
    siblings = children_of(rules, parent)
    first = min(p[-1] for p in paths)
    moved = [siblings[p[-1]] for p in sorted(paths)]
    for p in sorted(paths, reverse=True):
        siblings.pop(p[-1])
    siblings.insert(first, {"type": "group", "name": name, "enabled": True, "expanded": True, "children": moved})
    return (*parent, first)


def move_node(rules: list, src: Path_, dest_parent: Path_, index: int) -> Path_:
    """Move a node to dest_parent at index. Returns its new path."""
    if dest_parent[: len(src)] == src:
        raise ValueError("Can't move a group into itself.")
    node = children_of(rules, src[:-1]).pop(src[-1])
    # removing src shifts later siblings (and anything under them) up by one
    if dest_parent[: len(src) - 1] == src[:-1] and len(dest_parent) >= len(src) and dest_parent[len(src) - 1] > src[-1]:
        dest_parent = (*dest_parent[: len(src) - 1], dest_parent[len(src) - 1] - 1, *dest_parent[len(src) :])
    target = children_of(rules, dest_parent)
    if dest_parent == src[:-1] and index > src[-1]:
        index -= 1
    index = max(0, min(index, len(target)))
    target.insert(index, node)
    return (*dest_parent, index)


# ---------------------------------------------------------------- undo
class UndoStack:
    """Snapshots of a config's rule list. 50 levels, redo cleared on every new change."""

    def __init__(self, limit: int = 50):
        self.limit = limit
        self._undo: list[list] = []
        self._redo: list[list] = []

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()

    def push(self, rules: list) -> None:
        """Call BEFORE changing rules, with the current state."""
        self._undo.append(copy.deepcopy(rules))
        del self._undo[: -self.limit]
        self._redo.clear()

    def undo(self, current: list) -> list | None:
        if not self._undo:
            return None
        self._redo.append(copy.deepcopy(current))
        return self._undo.pop()

    def redo(self, current: list) -> list | None:
        if not self._redo:
            return None
        self._undo.append(copy.deepcopy(current))
        return self._redo.pop()

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)
