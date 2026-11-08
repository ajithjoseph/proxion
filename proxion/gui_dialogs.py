"""Pop-up windows used by the main window."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
import webbrowser
from collections.abc import Callable
from tkinter import filedialog, messagebox, ttk

from . import prejsons, rules

PAD = 8


def _center(win: tk.Toplevel, parent: tk.Misc) -> None:
    win.transient(parent)
    win.update_idletasks()
    x = parent.winfo_rootx() + (parent.winfo_width() - win.winfo_width()) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - win.winfo_height()) // 3
    win.geometry(f"+{max(x, 0)}+{max(y, 0)}")


def browse_file(parent) -> str:
    return filedialog.askopenfilename(
        parent=parent,
        title="Replacement file",
        filetypes=[
            ("Common assets", "*.png *.jpg *.jpeg *.ogg *.mp3 *.wav *.mesh *.obj *.rbxm *.ktx *.ttf *.otf"),
            ("All files", "*.*"),
        ],
    )


class AssetTypesDialog(tk.Toplevel):
    """Tick asset types. Calls on_change(list of type names) whenever a box changes."""

    def __init__(self, parent, selected: set[str], on_change: Callable[[list[str]], None]):
        super().__init__(parent)
        self.title("Asset Types")
        self.on_change = on_change
        self.vars: dict[str, tk.BooleanVar] = {}
        self.cat_vars: dict[str, tk.BooleanVar] = {}
        body = ttk.Frame(self, padding=PAD)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Tick a type to replace every asset of that type.", style="Muted.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 6)
        )
        for i, (cat, names) in enumerate(rules.ASSET_TYPE_CATEGORIES.items()):
            box = ttk.Frame(body, padding=(0, 0, 12, 8))
            box.grid(row=1 + i // 4, column=i % 4, sticky="nw")
            cv = tk.BooleanVar(value=all(n in selected for n in names))
            self.cat_vars[cat] = cv
            ttk.Checkbutton(
                box, text=cat, variable=cv, style="Bold.TCheckbutton", command=lambda c=cat: self._cat(c)
            ).pack(anchor="w")
            for n in names:
                v = tk.BooleanVar(value=n in selected)
                self.vars[n] = v
                ttk.Checkbutton(box, text=n, variable=v, command=self._changed).pack(anchor="w", padx=(14, 0))
        bar = ttk.Frame(body)
        bar.grid(row=10, column=0, columnspan=4, sticky="ew", pady=(6, 0))
        ttk.Button(bar, text="Clear Filters", command=self._clear).pack(side="left")
        ttk.Button(bar, text="Done", style="Accent.TButton", command=self.destroy).pack(side="right")
        self.bind("<Escape>", lambda e: self.destroy())
        _center(self, parent)

    def _cat(self, cat: str) -> None:
        for n in rules.ASSET_TYPE_CATEGORIES[cat]:
            self.vars[n].set(self.cat_vars[cat].get())
        self._changed()

    def _clear(self) -> None:
        for v in (*self.vars.values(), *self.cat_vars.values()):
            v.set(False)
        self._changed()

    def _changed(self) -> None:
        for cat, names in rules.ASSET_TYPE_CATEGORIES.items():
            self.cat_vars[cat].set(all(self.vars[n].get() for n in names))
        self.on_change([n for n, v in self.vars.items() if v.get()])


def apply_types(text: str, types: list[str]) -> str:
    """Replace the type names in an Asset IDs string, keeping numbers and anything else."""
    keep = [t for t in rules.split_targets(text) if not (isinstance(t, str) and t.lower() in rules.ALL_TYPE_NAMES)]
    return rules.join_targets(keep + types)


def selected_types(text: str) -> set[str]:
    return {t for t in rules.split_targets(text) if isinstance(t, str) and t.lower() in rules.ALL_TYPE_NAMES}


class EditIdsDialog(tk.Toplevel):
    """One asset ID per line. Calls on_save(list) when saved."""

    def __init__(self, parent, name: str, targets: list, on_save: Callable[[list], None]):
        super().__init__(parent)
        self.title(f"Asset IDs: {name}")
        self.on_save = on_save
        body = ttk.Frame(self, padding=PAD)
        body.pack(fill="both", expand=True)
        self.count = ttk.Label(body, style="Muted.TLabel")
        self.count.pack(anchor="w")
        self.text = tk.Text(body, width=40, height=18, bg=parent.panel, fg=parent.fg, insertbackground=parent.fg)
        self.text.pack(fill="both", expand=True, pady=6)
        self.text.insert("1.0", "\n".join(map(str, targets)))
        self.text.bind("<KeyRelease>", lambda e: self._update_count())
        bar = ttk.Frame(body)
        bar.pack(fill="x")
        ttk.Button(bar, text="Copy All", command=self._copy).pack(side="left")
        ttk.Button(bar, text="Asset Types", command=self._types).pack(side="left", padx=4)
        ttk.Button(bar, text="Save and Close", style="Accent.TButton", command=self._save).pack(side="right")
        self._update_count()
        self.bind("<Escape>", lambda e: self.destroy())
        _center(self, parent)

    def _targets(self) -> list:
        return rules.split_targets(self.text.get("1.0", "end"))

    def _update_count(self) -> None:
        self.count.configure(text=f"{len(self._targets())} entries, one per line")

    def _copy(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(", ".join(map(str, self._targets())))

    def _types(self) -> None:
        def changed(types):
            self.text.delete("1.0", "end")
            self.text.insert("1.0", apply_types(", ".join(map(str, self._targets())), types).replace(", ", "\n"))
            self._update_count()

        AssetTypesDialog(self, selected_types(", ".join(map(str, self._targets()))), changed)

    def _save(self) -> None:
        targets = self._targets()
        if not targets:
            messagebox.showerror("Proxion", "Add at least one asset ID.", parent=self)
            return
        self.on_save(targets)
        self.destroy()


class EditReplacementDialog(tk.Toplevel):
    """Asset ID, https link, file path, or empty to remove."""

    def __init__(self, parent, name: str, current: str, on_save: Callable[[str], bool]):
        super().__init__(parent)
        self.title(f"Replacement: {name}")
        self.on_save = on_save
        body = ttk.Frame(self, padding=PAD)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Asset ID, https:// link, file, or empty to remove it").pack(anchor="w")
        row = ttk.Frame(body)
        row.pack(fill="x", pady=6)
        self.var = tk.StringVar(value=current)
        e = ttk.Entry(row, textvariable=self.var, width=60)
        e.pack(side="left", fill="x", expand=True)
        e.focus_set()
        ttk.Button(row, text="Browse...", command=self._browse).pack(side="left", padx=(4, 0))
        ttk.Button(body, text="Save", style="Accent.TButton", command=self._save).pack(anchor="e")
        self.bind("<Return>", lambda ev: self._save())
        self.bind("<Escape>", lambda ev: self.destroy())
        _center(self, parent)

    def _browse(self) -> None:
        p = browse_file(self)
        if p:
            self.var.set(p)

    def _save(self) -> None:
        if self.on_save(self.var.get()):
            self.destroy()


class ScrapedGamesDialog(tk.Toplevel):
    """Community asset dumps (Fleasion's CLOG list). Pick a game, open its assets, copy IDs into a rule."""

    def __init__(self, parent, on_ids: Callable[[list[int]], None], on_replacement: Callable[[str], None]):
        super().__init__(parent)
        self.title("Scraped games")
        self.geometry("720x480")
        self.parent = parent
        self.on_ids, self.on_replacement = on_ids, on_replacement
        self.games: list[prejsons.Game] = []
        self.results: queue.Queue = queue.Queue()

        body = ttk.Frame(self, padding=PAD)
        body.pack(fill="both", expand=True)
        top = ttk.Frame(body)
        top.pack(fill="x")
        ttk.Label(top, text="Search:").pack(side="left")
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *a: self._fill())
        ttk.Entry(top, textvariable=self.search, width=30).pack(side="left", padx=6)
        ttk.Button(top, text="Refresh", command=self._load).pack(side="left")
        self.status = ttk.Label(top, style="Muted.TLabel")
        self.status.pack(side="left", padx=10)

        cols = ("owner", "place")
        self.tv = ttk.Treeview(body, columns=cols, show="tree headings", selectmode="browse")
        self.tv.heading("#0", text="Game")
        self.tv.column("#0", width=300)
        self.tv.heading("owner", text="Credit")
        self.tv.column("owner", width=140)
        self.tv.heading("place", text="Place ID")
        self.tv.column("place", width=120)
        self.tv.pack(fill="both", expand=True, pady=6)
        self.tv.bind("<Double-1>", lambda e: self._open("assets"))

        bar = ttk.Frame(body)
        bar.pack(fill="x")
        ttk.Button(bar, text="Assets", style="Accent.TButton", command=lambda: self._open("assets")).pack(side="left")
        ttk.Button(bar, text="Replacements", command=lambda: self._open("replacements")).pack(side="left", padx=4)
        ttk.Button(bar, text="Game page", command=self._game_page).pack(side="left")
        ttk.Label(
            bar, text="Lists made by the community. Only IDs are used, nothing is run.", style="Muted.TLabel"
        ).pack(side="right")
        self.bind("<Escape>", lambda e: self.destroy())
        _center(self, parent)
        self._load()
        self.after(100, self._poll)

    # background loading, results come back through a queue
    def _run(self, kind: str, fn, *args) -> None:
        def work():
            try:
                self.results.put((kind, fn(*args), None))
            except Exception as e:  # shown to the user, never crashes the app
                self.results.put((kind, None, e))

        threading.Thread(target=work, daemon=True).start()

    def _poll(self) -> None:
        if not self.winfo_exists():
            return
        while not self.results.empty():
            kind, result, err = self.results.get()
            if kind == "clog":
                if err:
                    self.status.configure(text=f"Couldn't load the list: {err}")
                else:
                    data, cached = result
                    self.games = prejsons.parse_clog(data)
                    note = " (offline copy)" if cached else ""
                    self.status.configure(text=f"{len(self.games)} games{note}")
                    self._fill()
            elif kind.startswith("file:"):
                title = kind[5:]
                if err:
                    messagebox.showerror("Proxion", f"Couldn't open {title}: {err}", parent=self)
                else:
                    JsonViewer(self, title, result[0], self.on_ids, self.on_replacement)
        self.after(150, self._poll)

    def _load(self) -> None:
        self.status.configure(text="Loading…")
        self._run("clog", prejsons.fetch_json, prejsons.CLOG_URL)

    def _fill(self) -> None:
        q = self.search.get().lower().strip()
        self.tv.delete(*self.tv.get_children())
        for i, g in enumerate(self.games):
            if q and q not in g.name.lower() and q not in g.owner.lower() and q not in str(g.place_id):
                continue
            self.tv.insert("", "end", iid=str(i), text=g.name, values=(g.owner, g.place_id or "-"))

    def _selected(self) -> prejsons.Game | None:
        sel = self.tv.selection()
        return self.games[int(sel[0])] if sel else None

    def _open(self, which: str) -> None:
        g = self._selected()
        if not g:
            return
        url = g.assets_url if which == "assets" else g.replacements_url
        if not url:
            messagebox.showinfo("Proxion", f"{g.name} has no {which} list.", parent=self)
            return
        self._run(f"file:{g.name} {which}", prejsons.fetch_json, url)

    def _game_page(self) -> None:
        g = self._selected()
        if g and g.place_id:
            webbrowser.open(f"https://www.roblox.com/games/{int(g.place_id)}")


class JsonViewer(tk.Toplevel):
    """Browse an asset dump and send selected IDs to the Replacer."""

    MAX_NODES = 50_000

    def __init__(self, parent, title: str, data, on_ids, on_replacement):
        super().__init__(parent)
        self.title(title)
        self.geometry("620x560")
        self.on_ids, self.on_replacement = on_ids, on_replacement
        self.values: dict[str, object] = {}
        self.matches: list[str] = []
        self.match_i = -1

        body = ttk.Frame(self, padding=PAD)
        body.pack(fill="both", expand=True)
        top = ttk.Frame(body)
        top.pack(fill="x")
        ttk.Label(top, text="Search:").pack(side="left")
        self.search = tk.StringVar()
        e = ttk.Entry(top, textvariable=self.search, width=24)
        e.pack(side="left", padx=4)
        e.bind("<Return>", lambda ev: self._find(1))
        ttk.Button(top, text="↓", width=3, command=lambda: self._find(1)).pack(side="left")
        ttk.Button(top, text="↑", width=3, command=lambda: self._find(-1)).pack(side="left", padx=2)
        ttk.Button(top, text="Expand All", command=lambda: self._expand(True)).pack(side="left", padx=(8, 2))
        ttk.Button(top, text="Collapse All", command=lambda: self._expand(False)).pack(side="left")

        frame = ttk.Frame(body)
        frame.pack(fill="both", expand=True, pady=6)
        self.tv = ttk.Treeview(frame, show="tree", selectmode="extended")
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=sb.set)
        self.tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.count = 0
        self._add("", "(root)", data)

        bar = ttk.Frame(body)
        bar.pack(fill="x")
        ttk.Label(bar, text="Use selected as:").pack(side="left")
        ttk.Button(bar, text="IDs to Replace", style="Accent.TButton", command=self._use_ids).pack(side="left", padx=4)
        ttk.Button(bar, text="Replacement ID", command=self._use_replacement).pack(side="left")
        self.info = ttk.Label(bar, style="Muted.TLabel")
        self.info.pack(side="right")
        if self.count >= self.MAX_NODES:
            self.info.configure(text=f"Showing the first {self.MAX_NODES} entries")
        self.bind("<Escape>", lambda ev: self.destroy())

    def _add(self, parent: str, key: str, node) -> None:
        if self.count >= self.MAX_NODES:
            return
        self.count += 1
        if isinstance(node, dict | list):
            items = node.items() if isinstance(node, dict) else enumerate(node)
            iid = self.tv.insert(parent, "end", text=f"{key}  ({len(node)})", open=parent == "")
            self.values[iid] = node
            for k, v in items:
                self._add(iid, str(k), v)
        else:
            iid = self.tv.insert(parent, "end", text=f"{key}: {node}")
            self.values[iid] = node

    def _selected_leaves(self) -> list[str]:
        out: list[str] = []
        for iid in self.tv.selection():
            out += prejsons.leaf_values(self.values.get(iid))
        return out

    def _use_ids(self) -> None:
        ids = prejsons.asset_ids(self._selected_leaves())
        if not ids:
            messagebox.showinfo("Proxion", "No asset IDs in the selection.", parent=self)
            return
        self.on_ids(ids)
        self.info.configure(text=f"Added {len(ids)} ID(s) to Asset IDs")

    def _use_replacement(self) -> None:
        leaves = self._selected_leaves()
        if not leaves:
            return
        self.on_replacement(leaves[0])
        self.info.configure(text=f"Replace With set to {leaves[0]}")

    def _expand(self, open_: bool) -> None:
        def walk(iid):
            for c in self.tv.get_children(iid):
                self.tv.item(c, open=open_)
                walk(c)

        walk("")

    def _find(self, step: int) -> None:
        q = self.search.get().lower().strip()
        if not q:
            return
        if not self.matches or self.matches[0] != q:
            hits = [iid for iid in self.values if q in self.tv.item(iid, "text").lower()]
            self.matches = [q, *hits]
            self.match_i = -1
        hits = self.matches[1:]
        if not hits:
            self.info.configure(text="No matches")
            return
        self.match_i = (self.match_i + step) % len(hits)
        iid = hits[self.match_i]
        self.tv.see(iid)
        self.tv.selection_set(iid)
        self.info.configure(text=f"{self.match_i + 1} of {len(hits)}")
