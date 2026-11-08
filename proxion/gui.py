"""Proxion desktop window (tkinter, ships with Python).

Tabs: Replacer (configs and profiles, laid out like Fleasion), Asset log, Setup & tools, Help.
"""

from __future__ import annotations

import contextlib
import json
import os
import queue
import subprocess
import sys
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import config as cfgmod
from . import help_text, roblox, rules
from .gui_dialogs import (
    AssetTypesDialog,
    EditIdsDialog,
    EditReplacementDialog,
    ScrapedGamesDialog,
    apply_types,
    browse_file,
    selected_types,
)
from .proxy import ProxyRunner

BG = "#16161d"
PANEL = "#1f1f29"
FG = "#e6e6f0"
ACCENT = "#7c5cff"
MUTED = "#8a8aa0"
GREEN = "#5be38a"
RED = "#ff6b6b"
MAX_LOG_ROWS = 5000  # assets kept in the Asset log tab
MAX_OUTPUT_LINES = 1000  # lines kept in the proxy output box
SORT_KEYS = {"#0": "name", "status": "status", "mode": "mode", "ids": "ids", "repl": "repl"}
HEADINGS = {"#0": "Profile Name", "status": "Status", "mode": "Mode", "ids": "Asset IDs", "repl": "Replacement"}


def _short(text: str, limit: int = 60) -> str:
    """Shorten a long path in the middle so both ends stay readable."""
    return text if len(text) <= limit else text[: limit // 2 - 1] + "…" + text[-(limit // 2) :]


def _iid(path: tuple) -> str:
    return "/".join(map(str, path))


def _path(iid: str) -> tuple:
    return tuple(int(x) for x in iid.split("/"))


class App(tk.Tk):
    panel, fg = PANEL, FG  # used by dialogs

    def __init__(self) -> None:
        super().__init__()
        self.title("Proxion")
        self.geometry("1060x720")
        self.minsize(860, 560)
        self.configure(bg=BG)

        self.cfg = cfgmod.load_settings()
        self.current = self.cfg.last_config
        self.data = cfgmod.empty_config()
        self.undo = rules.UndoStack()
        self.sort: tuple[str, bool] | None = None
        self._disk_stamp = None
        self._configs_stamp: tuple = ()
        self._drag: dict | None = None
        self._enabled_vars: dict[str, tk.BooleanVar] = {}
        self.out_q: queue.Queue[str] = queue.Queue()
        self.runner = ProxyRunner(on_output=self.out_q.put)
        self.log_pos = 0
        self.seen: dict[int, dict] = {}

        self._style()
        self._build()
        self._switch_config(self.current)
        self._bind_keys()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(500, self._tick)
        if not self.cfg.seen_welcome:
            self.after(400, self._welcome)

    # ================================================================ look
    def _style(self) -> None:
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=FG, fieldbackground=PANEL, bordercolor="#2c2c3a")
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", background=PANEL, foreground=MUTED, padding=(14, 6))
        s.map("TNotebook.Tab", background=[("selected", ACCENT)], foreground=[("selected", "white")])
        s.configure("TButton", background=PANEL, foreground=FG, padding=(10, 4), borderwidth=0)
        s.map("TButton", background=[("active", "#2c2c3a"), ("disabled", BG)], foreground=[("disabled", MUTED)])
        s.configure("Accent.TButton", background=ACCENT, foreground="white")
        s.map("Accent.TButton", background=[("active", "#6a4ae8")])
        s.configure("TMenubutton", background=PANEL, foreground=FG, padding=(10, 4), arrowcolor=FG)
        s.map("TMenubutton", background=[("active", "#2c2c3a")])
        s.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG, rowheight=24, borderwidth=0)
        s.configure("Treeview.Heading", background=BG, foreground=MUTED, borderwidth=0)
        s.map("Treeview", background=[("selected", ACCENT)])
        s.configure("TLabel", background=BG, foreground=FG)
        s.configure("Muted.TLabel", foreground=MUTED)
        s.configure("Bold.TLabel", font=("Segoe UI", 10, "bold"))
        s.configure("Title.TLabel", font=("Segoe UI", 12, "bold"))
        s.configure("TLabelframe", background=BG, bordercolor="#2c2c3a")
        s.configure("TLabelframe.Label", background=BG, foreground=FG, font=("Segoe UI", 10, "bold"))
        s.configure("TEntry", foreground=FG, insertcolor=FG)
        s.configure("TCheckbutton", background=BG, foreground=FG)
        s.configure("Bold.TCheckbutton", background=BG, foreground=FG, font=("Segoe UI", 10, "bold"))
        s.configure("TRadiobutton", background=BG, foreground=FG)
        s.configure("TFrame", background=BG)
        s.configure(
            "Vertical.TScrollbar", background=PANEL, troughcolor=BG, bordercolor=BG, arrowcolor=MUTED, gripcount=0
        )
        s.map("Vertical.TScrollbar", background=[("active", "#2c2c3a")])
        s.configure("TCombobox", fieldbackground=PANEL, background=PANEL, foreground=FG, arrowcolor=FG)
        s.map("TCombobox", fieldbackground=[("readonly", PANEL)], foreground=[("readonly", FG)])
        self.option_add("*TCombobox*Listbox.background", PANEL)
        self.option_add("*TCombobox*Listbox.foreground", FG)
        self.option_add("*Menu.background", PANEL)
        self.option_add("*Menu.foreground", FG)
        self.option_add("*Menu.activeBackground", ACCENT)
        self.option_add("*Menu.selectColor", FG)

    def _build(self) -> None:
        top = ttk.Frame(self, padding=(14, 10))
        top.pack(fill="x")
        tk.Label(top, text="Proxion", bg=BG, fg=FG, font=("Segoe UI", 18, "bold")).pack(side="left")
        tk.Label(top, text="  Roblox asset replacer", bg=BG, fg=MUTED, font=("Segoe UI", 10)).pack(side="left")
        self.toggle_btn = ttk.Button(top, text="Start proxy", style="Accent.TButton", command=self._toggle)
        self.toggle_btn.pack(side="right")
        self.status = tk.Label(top, text="● stopped", bg=BG, fg=RED, font=("Segoe UI", 10))
        self.status.pack(side="right", padx=12)

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.tab_replacer = self._replacer_tab(self.nb)
        self.tab_log = self._log_tab(self.nb)
        self.tab_tools = self._tools_tab(self.nb)
        self.tab_help = self._help_tab(self.nb)
        self.nb.add(self.tab_replacer, text="Replacer")
        self.nb.add(self.tab_log, text="Asset log")
        self.nb.add(self.tab_tools, text="Setup & tools")
        self.nb.add(self.tab_help, text="Help")

    # ================================================================ Replacer tab
    def _replacer_tab(self, parent) -> ttk.Frame:
        f = ttk.Frame(parent, padding=8)

        conf = ttk.Labelframe(f, text="Configuration", padding=8)
        conf.pack(fill="x")
        ttk.Label(conf, text="Editing:").pack(side="left")
        self.edit_dot = tk.Label(conf, text="●", bg=BG, fg=GREEN, font=("Segoe UI", 11))
        self.edit_dot.pack(side="left", padx=(6, 0))
        self.edit_mb = ttk.Menubutton(conf, width=20)
        self.edit_menu = tk.Menu(self.edit_mb, tearoff=False, postcommand=self._fill_edit_menu)
        self.edit_mb["menu"] = self.edit_menu
        self.edit_mb.pack(side="left", padx=(2, 14))
        ttk.Label(conf, text="Enabled:").pack(side="left")
        self.enabled_mb = ttk.Menubutton(conf, width=20)
        self.enabled_menu = tk.Menu(self.enabled_mb, tearoff=False, postcommand=self._fill_enabled_menu)
        self.enabled_mb["menu"] = self.enabled_menu
        self.enabled_mb.pack(side="left", padx=(6, 14))
        for text, cmd in (
            ("New", self._new_config),
            ("Duplicate", self._dup_config),
            ("Rename", self._rename_config),
            ("Delete", self._del_config),
        ):
            ttk.Button(conf, text=text, width=len(text) + 2, command=cmd).pack(side="left", padx=2)

        head = ttk.Frame(f)
        head.pack(fill="x", pady=(8, 2))
        ttk.Label(head, text="Replacement Profiles:", style="Bold.TLabel").pack(side="left", anchor="s")
        ttk.Button(head, text="Export…", command=self._export).pack(side="right", padx=2)
        ttk.Button(head, text="Import config…", style="Accent.TButton", command=self._open_config).pack(
            side="right", padx=2
        )
        table = ttk.Frame(f)
        table.pack(fill="both", expand=True)
        cols = ("status", "mode", "ids", "repl")
        self.tv = ttk.Treeview(table, columns=cols, show="tree headings", selectmode="extended")
        self.tv.heading("#0", text=HEADINGS["#0"], command=lambda: self._sort_by("#0"))
        self.tv.column("#0", width=300, minwidth=160)
        for c, w in (("status", 60), ("mode", 70), ("ids", 90), ("repl", 340)):
            self.tv.heading(c, text=HEADINGS[c], command=lambda c=c: self._sort_by(c))
            self.tv.column(c, width=w, minwidth=50, anchor="w", stretch=c == "repl")
        self.tv.tag_configure("off", foreground=MUTED)
        self.tv.tag_configure("group", font=("Segoe UI", 10, "bold"))
        sb = ttk.Scrollbar(table, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=sb.set)
        self.tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tv.bind("<Button-3>", self._context_menu)
        self.tv.bind("<Button-2>", self._context_menu)  # macOS right click
        self.tv.bind("<Double-1>", lambda e: self._load_selected())
        self.tv.bind("<ButtonPress-1>", self._drag_start, add="+")
        self.tv.bind("<B1-Motion>", self._drag_motion, add="+")
        self.tv.bind("<ButtonRelease-1>", self._drag_end, add="+")
        self.tv.bind("<<TreeviewOpen>>", lambda e: self._remember_open(True))
        self.tv.bind("<<TreeviewClose>>", lambda e: self._remember_open(False))
        self.empty_hint = tk.Label(
            self.tv,
            text="No profiles yet. Fill in the boxes below and click Add New,\n"
            "or click Import config… to open one someone shared.",
            bg=PANEL,
            fg=MUTED,
            justify="center",
        )

        form = ttk.Labelframe(f, text="Add/Edit Profile", padding=8)
        form.pack(fill="x", pady=(8, 0))
        form.columnconfigure(1, weight=1)
        self.v_name, self.v_ids, self.v_repl = tk.StringVar(), tk.StringVar(), tk.StringVar()
        entries = []
        ttk.Label(form, text="Profile Name:").grid(row=0, column=0, sticky="w", pady=2)
        entries.append(ttk.Entry(form, textvariable=self.v_name))
        entries[-1].grid(row=0, column=1, columnspan=2, sticky="ew", pady=2)
        ttk.Label(form, text="Asset IDs:").grid(row=1, column=0, sticky="w", pady=2)
        entries.append(ttk.Entry(form, textvariable=self.v_ids))
        entries[-1].grid(row=1, column=1, sticky="ew", pady=2)
        ttk.Button(form, text="Asset Types", command=self._asset_types).grid(row=1, column=2, sticky="ew", padx=(6, 0))
        ttk.Label(form, text="Replace With:").grid(row=2, column=0, sticky="w", pady=2)
        entries.append(ttk.Entry(form, textvariable=self.v_repl))
        entries[-1].grid(row=2, column=1, sticky="ew", pady=2)
        ttk.Button(form, text="Browse...", command=self._browse).grid(row=2, column=2, sticky="ew", padx=(6, 0))
        ttk.Label(
            form,
            text="Replace With: an asset ID, an https:// link, a file, or leave it empty to remove the asset.",
            style="Muted.TLabel",
        ).grid(row=3, column=1, sticky="w")
        for e in entries:
            e.bind("<Return>", lambda ev: self._add_profile())
        btns = ttk.Frame(form)
        btns.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        ttk.Button(btns, text="Add New", style="Accent.TButton", command=self._add_profile).pack(side="left")
        ttk.Button(btns, text="Load Selected", command=self._load_selected).pack(side="left", padx=4)
        ttk.Button(btns, text="Update Selected", command=self._update_profile).pack(side="left")
        ttk.Button(btns, text="Scraped games...", command=self._scraped_games).pack(side="right")

        bottom = ttk.Frame(f)
        bottom.pack(fill="x", pady=(8, 0))
        self.redo_btn = ttk.Button(bottom, text="Redo (Ctrl+Y)", command=self._redo)
        self.redo_btn.pack(side="right", padx=2)
        self.undo_btn = ttk.Button(bottom, text="Undo (Ctrl+Z)", command=self._undo)
        self.undo_btn.pack(side="right", padx=2)
        ttk.Button(bottom, text="Open Configs", command=self._open_folder).pack(side="right", padx=2)
        ttk.Button(bottom, text="Clear Cache", command=self._clear_cache).pack(side="right", padx=2)
        ttk.Button(bottom, text="?", width=3, command=lambda: self._info("Replacer", help_text.KEYBINDS)).pack(
            side="right", padx=2
        )
        # packed last so it gets whatever room the buttons leave, and is clipped rather than pushing them off
        self.path_lbl = ttk.Label(bottom, style="Muted.TLabel")
        self.path_lbl.pack(side="left", fill="x", expand=True)
        return f

    def _bind_keys(self) -> None:
        def on_replacer(fn):
            def handler(event):
                in_entry = isinstance(event.widget, tk.Entry | ttk.Entry | tk.Text)
                if self.nb.select() == str(self.tab_replacer) and not in_entry:
                    fn()
                    return "break"
                return None

            return handler

        self.bind_all("<Control-z>", on_replacer(self._undo))
        self.bind_all("<Control-y>", on_replacer(self._redo))
        self.tv.bind("<Delete>", lambda e: self._delete_selected())
        self.tv.bind("<Control-a>", lambda e: (self.tv.selection_set(self._all_iids()), "break")[1])

    # ---------------------------------------------------------------- configs
    def _switch_config(self, name: str) -> None:
        names = cfgmod.list_configs()
        if not names:  # every config was deleted outside Proxion
            cfgmod.write_config("Default", cfgmod.empty_config())
            names = ["Default"]
        if name not in names:
            name = names[0]
        self.current = name
        self.data = cfgmod.read_config(name)
        self.undo.clear()
        self.cfg.last_config = name
        cfgmod.save_settings(self.cfg)
        self._remember_disk()
        self._refresh_all()

    def _remember_disk(self) -> None:
        f = cfgmod.config_file(self.current)
        self._disk_stamp = f.stat().st_mtime_ns if f.exists() else None
        self._configs_stamp = tuple(cfgmod.list_configs())

    def _refresh_all(self) -> None:
        names = cfgmod.list_configs()
        self.cfg.enabled_configs = [n for n in self.cfg.enabled_configs if n in names]
        on = self.current in self.cfg.enabled_configs
        self.edit_mb.configure(text=self.current)
        self.edit_dot.configure(fg=GREEN if on else RED)
        en = self.cfg.enabled_configs
        self.enabled_mb.configure(
            text="No Configs Enabled" if not en else en[0] if len(en) == 1 else f"{len(en)} configs enabled"
        )
        self.path_lbl.configure(text=f"Configs: {_short(str(cfgmod.configs_dir()))}")
        self._refresh_rules()

    def _fill_edit_menu(self) -> None:
        self.edit_menu.delete(0, "end")
        for n in cfgmod.list_configs():
            mark = "● " if n in self.cfg.enabled_configs else "○ "
            self.edit_menu.add_command(label=mark + n, command=lambda n=n: self._switch_config(n))

    def _fill_enabled_menu(self) -> None:
        self.enabled_menu.delete(0, "end")
        names = cfgmod.list_configs()
        self.cfg.enabled_configs = [n for n in self.cfg.enabled_configs if n in names]
        self._enabled_vars = {}
        for n in names:
            v = tk.BooleanVar(value=n in self.cfg.enabled_configs)
            self._enabled_vars[n] = v
            self.enabled_menu.add_checkbutton(label=n, variable=v, command=lambda n=n: self._set_enabled_config(n))

    def _set_enabled_config(self, name: str, on: bool | None = None) -> None:
        if on is None:
            on = self._enabled_vars[name].get()
        en = [n for n in self.cfg.enabled_configs if n != name]
        if on:
            en.append(name)
        self.cfg.enabled_configs = en
        cfgmod.save_settings(self.cfg)
        self._refresh_all()

    def _ask_name(self, title: str, initial: str = "") -> str | None:
        name = simpledialog.askstring("Proxion", title, initialvalue=initial, parent=self)
        return name.strip() if name and name.strip() else None

    def _new_config(self) -> None:
        name = self._ask_name("Name for the new config:")
        if name:
            try:
                self._switch_config(cfgmod.create_config(name))
            except (ValueError, FileExistsError) as e:
                messagebox.showerror("Proxion", str(e))

    def _dup_config(self) -> None:
        name = self._ask_name("Name for the copy:", f"Copy of {self.current}")
        if not name:
            return
        try:
            new = cfgmod.create_config(name)
        except (ValueError, FileExistsError) as e:
            messagebox.showerror("Proxion", str(e))
            return
        cfgmod.write_config(new, cfgmod.read_config(self.current))
        self._switch_config(new)

    def _rename_config(self) -> None:
        name = self._ask_name(f'Rename "{self.current}" to:', self.current)
        if name and name != self.current:
            try:
                new = cfgmod.rename_config(self.current, name, self.cfg)
            except (ValueError, FileExistsError, OSError) as e:
                messagebox.showerror("Proxion", str(e))
                return
            self._switch_config(new)

    def _del_config(self) -> None:
        if not messagebox.askyesno("Proxion", f'Delete the config "{self.current}"? This can\'t be undone.'):
            return
        try:
            cfgmod.delete_config(self.current, self.cfg)
        except ValueError as e:
            messagebox.showerror("Proxion", str(e))
            return
        self._switch_config(self.cfg.last_config)

    def _open_config(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Import config (Proxion or Fleasion)", filetypes=[("Configs", "*.json"), ("All files", "*.*")]
        )
        if paths:
            self.open_files(paths)

    def open_files(self, paths) -> None:
        """Copy config files into the configs folder and show the last one.

        A config is turned on right away unless it uses files outside the configs folder
        or downloads from the web. Then the user sees what it does and decides.
        """
        opened, failed, last = [], [], None
        for p in paths:
            try:
                last = cfgmod.import_config(p)
            except (OSError, ValueError) as e:
                failed.append(f"{os.path.basename(p)}: {e}")
                continue
            data = cfgmod.read_config(last)
            n = sum(1 for _ in cfgmod.iter_rules(data["replacement_rules"]))
            compiled = cfgmod.compile_rules([data])
            notes = cfgmod.review_config(data)
            turn_on = not notes or messagebox.askyesno(
                "Proxion",
                f'Before turning on "{last}", check what it does:\n\n'
                + "\n".join(f"• {x}" for x in notes[:15])
                + ("\n• …" if len(notes) > 15 else "")
                + "\n\nOnly turn it on if you trust where you got it. Turn it on now?",
            )
            if turn_on and last not in self.cfg.enabled_configs:
                self.cfg.enabled_configs.append(last)
            note = (
                f" ({compiled.skipped} target(s) Proxion can't use yet, they're kept in the file)"
                if compiled.skipped
                else ""
            )
            opened.append(f"{last}: {n} profile(s){note}{'' if turn_on else ' (left turned off)'}")
        if last:
            self._switch_config(last)
        msg = ""
        if opened:
            msg += "Opened:\n" + "\n".join(opened)
        if failed:
            msg += ("\n\n" if msg else "") + "Could not open:\n" + "\n".join(failed)
        (messagebox.showerror if failed and not opened else messagebox.showinfo)("Proxion", msg)

    def _export(self) -> None:
        p = filedialog.asksaveasfilename(
            defaultextension=".json", initialfile=f"{self.current}.json", filetypes=[("Config", "*.json")]
        )
        if p:
            cfgmod.export_config(self.current, p)

    def _open_folder(self) -> None:
        self._open_path(str(cfgmod.configs_dir()))

    def _open_path(self, d: str) -> None:
        try:
            if sys.platform == "win32":
                os.startfile(d)  # noqa: S606 (our own folder)
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", d])
        except OSError:
            messagebox.showinfo("Proxion", f"Folder:\n{d}")

    # ---------------------------------------------------------------- profiles table
    @property
    def rules(self) -> list:
        return self.data["replacement_rules"]

    def _all_iids(self) -> list[str]:
        out: list[str] = []

        def walk(i):
            for c in self.tv.get_children(i):
                out.append(c)
                walk(c)

        walk("")
        return out

    def _sort_key(self, node: dict):
        col = SORT_KEYS[self.sort[0]] if self.sort else None
        status, mode, ids, repl = rules.row_values(node)
        if col == "name":
            return str(node.get("name", "")).lower()
        if col == "ids":
            first = ids.split()[0]
            return int(first) if first.isdigit() else 0
        return {"status": status, "mode": mode, "repl": repl.lower()}[col]

    def _refresh_rules(self) -> None:
        sel = set(self.tv.selection())
        self.tv.delete(*self.tv.get_children())

        def add(parent_iid: str, items: list, path: tuple) -> None:
            entries = [(i, n) for i, n in enumerate(items) if isinstance(n, dict)]
            if self.sort:
                entries.sort(key=lambda e: self._sort_key(e[1]), reverse=self.sort[1])
            for i, node in entries:
                p = (*path, i)
                status, mode, ids, repl = rules.row_values(node)
                tags = (["off"] if status == "Off" else []) + (["group"] if rules.is_group(node) else [])
                default = "Group" if rules.is_group(node) else "Profile"
                self.tv.insert(
                    parent_iid,
                    "end",
                    iid=_iid(p),
                    text=str(node.get("name") or default),
                    values=(status, mode, ids, repl),
                    open=node.get("expanded", True),
                    tags=tags,
                )
                if rules.is_group(node):
                    add(_iid(p), node.get("children") or [], p)

        add("", self.rules, ())
        keep = [i for i in sel if self.tv.exists(i)]
        if keep:
            self.tv.selection_set(keep)
        if self.tv.get_children():
            self.empty_hint.place_forget()
        else:
            self.empty_hint.place(relx=0.5, rely=0.45, anchor="center")
        self.undo_btn.state(["!disabled"] if self.undo.can_undo else ["disabled"])
        self.redo_btn.state(["!disabled"] if self.undo.can_redo else ["disabled"])

    def _sort_by(self, col: str) -> None:
        if self.sort and self.sort[0] == col:
            self.sort = None if self.sort[1] else (col, True)  # ascending, descending, then file order
        else:
            self.sort = (col, False)
        arrow = {col: " ▼" if self.sort[1] else " ▲"} if self.sort else {}
        for c, t in HEADINGS.items():
            self.tv.heading(c, text=t + arrow.get(c, ""))
        self._refresh_rules()

    def _selected_paths(self) -> list[tuple]:
        return [_path(i) for i in self.tv.selection()]

    def _change(self, fn, select: list[tuple] | None = None):
        """Every edit goes through here: snapshot for undo, apply, save, redraw."""
        self.undo.push(self.rules)
        result = fn()
        self._save_current()
        self._refresh_rules()
        if select:
            iids = [_iid(p) for p in select if self.tv.exists(_iid(p))]
            if iids:
                self.tv.selection_set(iids)
                self.tv.see(iids[0])
        return result

    def _save_current(self) -> None:
        cfgmod.write_config(self.current, self.data)
        self._remember_disk()

    def _undo(self) -> None:
        prev = self.undo.undo(self.rules)
        if prev is not None:
            self.data["replacement_rules"] = prev
            self._save_current()
            self._refresh_all()

    def _redo(self) -> None:
        nxt = self.undo.redo(self.rules)
        if nxt is not None:
            self.data["replacement_rules"] = nxt
            self._save_current()
            self._refresh_all()

    def _remember_open(self, is_open: bool) -> None:
        iid = self.tv.focus()
        if iid:
            node = rules.node_at(self.rules, _path(iid))
            if rules.is_group(node):
                node["expanded"] = is_open
                self._save_current()  # UI state only, not an undo step

    # ---------------------------------------------------------------- add / edit form
    def _read_form(self) -> tuple[str, list, str, object] | None:
        targets = rules.split_targets(self.v_ids.get())
        if not targets:
            messagebox.showerror("Proxion", "Add at least one asset ID (or a type like Hat) to replace.")
            return None
        bad = [str(t) for t in targets if cfgmod.parse_target(t) is None]
        if bad and not messagebox.askyesno(
            "Proxion",
            "Proxion can't use these entries: "
            + ", ".join(bad[:20])
            + "\n(IDs 1 to 80 and unknown names are ignored.)\n\nKeep them anyway?",
        ):
            return None
        try:
            mode, value = rules.parse_replacement(self.v_repl.get())
        except ValueError as e:
            messagebox.showerror("Proxion", str(e))
            return None
        return self.v_name.get().strip(), targets, mode, value

    def _insert_point(self) -> tuple[list, tuple]:
        """New profiles go into the selected group, else next to the selection, else at the end."""
        paths = self._selected_paths()
        if paths:
            p = paths[0]
            node = rules.node_at(self.rules, p)
            if rules.is_group(node):
                return node.setdefault("children", []), p
            return rules.children_of(self.rules, p[:-1]), p[:-1]
        return self.rules, ()

    def _add_profile(self) -> None:
        form = self._read_form()
        if not form:
            return
        name, targets, mode, value = form
        items, parent = self._insert_point()
        name = name or f"Profile {len(rules.leaf_rules(self.rules)) + 1}"
        self._change(lambda: items.append(rules.make_rule(name, targets, mode, value)), [(*parent, len(items))])
        for v in (self.v_name, self.v_ids, self.v_repl):
            v.set("")

    def _load_selected(self) -> None:
        paths = self._selected_paths()
        if not paths:
            return
        node = rules.node_at(self.rules, paths[0])
        if rules.is_group(node):
            return
        self.v_name.set(str(node.get("name", "")))
        self.v_ids.set(rules.join_targets(node.get("replace_ids") or []))
        self.v_repl.set(rules.replacement_text(node))

    def _update_profile(self) -> None:
        paths = self._selected_paths()
        if not paths:
            messagebox.showinfo("Proxion", "Select a profile in the list first (Load Selected copies it here).")
            return
        node = rules.node_at(self.rules, paths[0])
        if rules.is_group(node):
            messagebox.showinfo("Proxion", "That's a group. Right-click it to rename it.")
            return
        form = self._read_form()
        if form:
            name, targets, mode, value = form
            name = name or str(node.get("name", "Profile"))
            self._change(lambda: rules.apply_fields(node, name, targets, mode, value), [paths[0]])

    def _asset_types(self) -> None:
        AssetTypesDialog(
            self, selected_types(self.v_ids.get()), lambda t: self.v_ids.set(apply_types(self.v_ids.get(), t))
        )

    def _browse(self) -> None:
        p = browse_file(self)
        if p:
            self.v_repl.set(p)

    def _scraped_games(self) -> None:
        def add_ids(ids):
            current = rules.split_targets(self.v_ids.get())
            self.v_ids.set(rules.join_targets(current + [i for i in ids if i not in current]))

        ScrapedGamesDialog(self, add_ids, self.v_repl.set)

    # ---------------------------------------------------------------- right-click menu
    def _context_menu(self, event) -> None:
        row = self.tv.identify_row(event.y)
        if row and row not in self.tv.selection():
            self.tv.selection_set(row)
        paths = self._selected_paths()
        m = tk.Menu(self, tearoff=False)
        if not paths:
            m.add_command(label="Add a profile with the boxes below", state="disabled")
        elif len(paths) > 1:
            m.add_command(label="Enable Selected", command=lambda: self._set_on(paths, True))
            m.add_command(label="Disable Selected", command=lambda: self._set_on(paths, False))
            if len({p[:-1] for p in paths}) == 1:
                m.add_command(label="Create Group", command=lambda: self._group(paths))
            m.add_separator()
            m.add_command(label="Delete Selected", command=self._delete_selected)
        else:
            p = paths[0]
            node = rules.node_at(self.rules, p)
            on = rules.is_on(node)
            kind = "Group" if rules.is_group(node) else "Profile"
            m.add_command(label=f"{'Disable' if on else 'Enable'} {kind}", command=lambda: self._set_on(paths, not on))
            m.add_command(label=f"Rename {kind}", command=lambda: self._rename_node(p))
            if kind == "Profile":
                m.add_command(label="Edit Asset IDs", command=lambda: self._edit_ids(p))
                m.add_command(label="Edit Replacement", command=lambda: self._edit_replacement(p))
                m.add_command(label="Load into boxes", command=self._load_selected)
                m.add_command(label="Create Group", command=lambda: self._group(paths))
            m.add_separator()
            m.add_command(label=f"Delete {kind}", command=self._delete_selected)
        m.tk_popup(event.x_root, event.y_root)

    def _set_on(self, paths, on: bool) -> None:
        self._change(lambda: rules.set_enabled(self.rules, paths, on), paths)

    def _group(self, paths) -> None:
        if len({p[:-1] for p in paths}) != 1:
            messagebox.showerror("Proxion", "Pick profiles from the same level to group them.")
            return
        name = self._ask_name("Group name:", "New Group")
        if name:
            new = self._change(lambda: rules.create_group(self.rules, paths, name))
            if self.tv.exists(_iid(new)):
                self.tv.selection_set(_iid(new))

    def _rename_node(self, p) -> None:
        node = rules.node_at(self.rules, p)
        name = self._ask_name("New name:", str(node.get("name", "")))
        if name:
            self._change(lambda: node.__setitem__("name", name), [p])

    def _edit_ids(self, p) -> None:
        node = rules.node_at(self.rules, p)
        targets = node.get("replace_ids") or []
        EditIdsDialog(
            self,
            str(node.get("name", "Profile")),
            targets if isinstance(targets, list) else [targets],
            lambda t: self._change(lambda: node.__setitem__("replace_ids", t), [p]),
        )

    def _edit_replacement(self, p) -> None:
        node = rules.node_at(self.rules, p)

        def save(text: str) -> bool:
            try:
                mode, value = rules.parse_replacement(text)
            except ValueError as e:
                messagebox.showerror("Proxion", str(e))
                return False
            targets = node.get("replace_ids") or []
            self._change(lambda: rules.apply_fields(node, str(node.get("name", "")), targets, mode, value), [p])
            return True

        EditReplacementDialog(self, str(node.get("name", "Profile")), rules.replacement_text(node), save)

    def _delete_selected(self) -> None:
        paths = self._selected_paths()
        if not paths:
            return
        nodes = [rules.node_at(self.rules, p) for p in paths]
        if any(rules.is_group(n) and n.get("children") for n in nodes) and not messagebox.askyesno(
            "Proxion", "Delete the selected group(s) and everything inside them?"
        ):
            return
        self._change(lambda: rules.remove_paths(self.rules, paths))

    # ---------------------------------------------------------------- drag and drop
    def _drag_start(self, event) -> None:
        row = self.tv.identify_row(event.y)
        self._drag = {"row": row, "y": event.y, "active": False} if row else None

    def _drag_motion(self, event) -> None:
        if not self._drag or self.sort:  # reordering a sorted view would be confusing
            return
        if not self._drag["active"] and abs(event.y - self._drag["y"]) > 6:
            self._drag["active"] = True
            self.tv.configure(cursor="fleur")

    def _drag_end(self, event) -> None:
        drag, self._drag = self._drag, None
        self.tv.configure(cursor="")
        if not drag or not drag["active"]:
            return
        src = _path(drag["row"])
        target = self.tv.identify_row(event.y)
        if not target:
            dest_parent, index = (), len(self.rules)  # empty space: end of the top level
        else:
            tp = _path(target)
            tnode = rules.node_at(self.rules, tp)
            _x, y, _w, h = self.tv.bbox(target)
            frac = (event.y - y) / max(h, 1)
            if rules.is_group(tnode) and 0.25 < frac < 0.75:
                dest_parent, index = tp, len(tnode.get("children") or [])
            else:
                dest_parent, index = tp[:-1], tp[-1] + (1 if frac >= 0.5 else 0)
        if dest_parent[: len(src)] == src or (dest_parent == src[:-1] and index in (src[-1], src[-1] + 1)):
            return  # into itself, or dropped where it already is
        new = self._change(lambda: rules.move_node(self.rules, src, dest_parent, index))
        if self.tv.exists(_iid(new)):
            self.tv.selection_set(_iid(new))

    # ================================================================ Asset log tab
    def _log_tab(self, parent) -> ttk.Frame:
        f = ttk.Frame(parent, padding=8)
        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=(0, 6))
        ttk.Label(bar, text="Search:").pack(side="left")
        self.v_filter = tk.StringVar()
        ttk.Entry(bar, textvariable=self.v_filter, width=26).pack(side="left", padx=6)
        self.v_filter.trace_add("write", lambda *a: self._redraw_log())
        ttk.Label(bar, text="Type:").pack(side="left", padx=(8, 0))
        self.v_type = tk.StringVar(value="All Types")
        cb = ttk.Combobox(
            bar,
            textvariable=self.v_type,
            state="readonly",
            width=18,
            values=["All Types", *rules.ASSET_TYPE_CATEGORIES],
        )
        cb.pack(side="left", padx=6)
        cb.bind("<<ComboboxSelected>>", lambda e: self._redraw_log())
        self.log_count = ttk.Label(bar, style="Muted.TLabel")
        self.log_count.pack(side="left", padx=8)
        ttk.Button(bar, text="?", width=3, command=lambda: self._info("Asset log", help_text.LOG_HELP)).pack(
            side="right"
        )
        ttk.Button(bar, text="Clear log", command=self._clear_log).pack(side="right", padx=4)

        cols = ("id", "type", "action", "replacement", "hits")
        self.log_tv = ttk.Treeview(f, columns=cols, show="headings")
        for c, w in zip(cols, (150, 130, 80, 280, 60), strict=True):
            self.log_tv.heading(c, text={"id": "Asset ID"}.get(c, c.title()))
            self.log_tv.column(c, width=w, anchor="w")
        self.log_tv.pack(fill="both", expand=True)
        self.log_tv.bind("<Button-3>", self._log_menu)
        self.log_tv.bind("<Button-2>", self._log_menu)
        ttk.Label(
            f,
            text="Every asset Roblox loads while the proxy is on shows up here. Right-click one to replace it.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(6, 0))
        return f

    def _read_log(self) -> None:
        path = cfgmod.log_path()
        if not path.exists():
            return
        if path.stat().st_size < self.log_pos:  # the proxy rotated the log
            self.log_pos = 0
        with open(path, "rb") as f:
            f.seek(self.log_pos)
            chunk = f.read(2 * 1024 * 1024)  # at most 2 MB per tick so the window stays responsive
        complete = chunk[: chunk.rfind(b"\n") + 1]  # a half-written line waits for the next tick
        self.log_pos += len(complete)
        lines = complete.decode("utf-8", errors="replace").splitlines()
        if not lines:
            return
        for line in lines:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            aid = e.get("assetId")
            cur = self.seen.pop(aid, None) or {"type": "?", "hits": 0}
            self.seen[aid] = cur  # move to the end: newest last
            if e.get("type") not in (None, "?"):
                cur["type"] = e["type"]
            cur["action"] = e.get("action", "none")
            cur["replacement"] = e.get("replacement")
            cur["hits"] += 1
        while len(self.seen) > MAX_LOG_ROWS:  # forget the oldest assets
            del self.seen[next(iter(self.seen))]
        self._redraw_log()

    def _redraw_log(self) -> None:
        flt = self.v_filter.get().lower().strip()
        allowed = set(rules.ASSET_TYPE_CATEGORIES.get(self.v_type.get(), []))
        self.log_tv.delete(*self.log_tv.get_children())
        shown = 0
        for aid, e in reversed(list(self.seen.items())):
            if allowed and e["type"] not in allowed:
                continue
            vals = (aid, e["type"], e.get("action", ""), e.get("replacement") or "", e["hits"])
            if flt and not any(flt in str(v).lower() for v in vals):
                continue
            self.log_tv.insert("", "end", values=vals)
            shown += 1
        self.log_count.configure(text=f"{shown} of {len(self.seen)} assets")

    def _clear_log(self) -> None:
        self.seen.clear()
        with contextlib.suppress(OSError):
            cfgmod.log_path().write_text("")
        self.log_pos = 0
        self._redraw_log()

    def _log_ids(self) -> list[str]:
        return [str(self.log_tv.item(i)["values"][0]) for i in self.log_tv.selection()]

    def _log_menu(self, event) -> None:
        row = self.log_tv.identify_row(event.y)
        if row and row not in self.log_tv.selection():
            self.log_tv.selection_set(row)
        ids = [i for i in self._log_ids() if cfgmod.as_asset_id(i) is not None]
        if not ids:
            return
        m = tk.Menu(self, tearoff=False)
        m.add_command(label=f"Replace ({len(ids)})", command=lambda: self._log_replace(ids))
        m.add_command(label="Replace with", command=lambda: self._log_replace_with(ids[0]))
        m.add_separator()
        m.add_command(label="Copy Asset ID", command=lambda: self._copy(", ".join(ids)))
        aid = cfgmod.as_asset_id(ids[0])
        m.add_command(
            label="Open asset page", command=lambda: webbrowser.open(f"https://create.roblox.com/store/asset/{aid}")
        )
        m.tk_popup(event.x_root, event.y_root)

    def _log_replace(self, ids: list[str]) -> None:
        current = rules.split_targets(self.v_ids.get())
        new = [cfgmod.as_asset_id(i) for i in ids]
        self.v_ids.set(rules.join_targets(current + [i for i in new if i not in current]))
        self.nb.select(self.tab_replacer)

    def _log_replace_with(self, aid: str) -> None:
        self.v_repl.set(aid)
        self.nb.select(self.tab_replacer)

    def _copy(self, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)

    # ================================================================ Setup & tools tab
    def _tools_tab(self, parent) -> ttk.Frame:
        f = ttk.Frame(parent, padding=14)
        head = ttk.Frame(f)
        head.pack(fill="x")
        ttk.Label(head, text="Capture mode", style="Title.TLabel").pack(side="left")
        ttk.Button(head, text="?", width=3, command=lambda: self._info("Setup & tools", help_text.SETUP_HELP)).pack(
            side="right"
        )
        self.v_pmode = tk.StringVar(value=self.cfg.proxy_mode)
        ttk.Radiobutton(
            f,
            text="Local capture: only grabs Roblox's traffic, nothing else on your PC (recommended)",
            value="local",
            variable=self.v_pmode,
            command=self._save_settings,
        ).pack(anchor="w")
        ttk.Radiobutton(
            f,
            text="Regular proxy on a port, this PC only (advanced, you route traffic to it yourself)",
            value="regular",
            variable=self.v_pmode,
            command=self._save_settings,
        ).pack(anchor="w")
        row = ttk.Frame(f)
        row.pack(anchor="w", pady=6)
        ttk.Label(row, text="Process").pack(side="left")
        self.v_proc = tk.StringVar(value=self.cfg.capture_process)
        ttk.Entry(row, textvariable=self.v_proc, width=22).pack(side="left", padx=6)
        ttk.Label(row, text="Port").pack(side="left", padx=(10, 0))
        self.v_port = tk.StringVar(value=str(self.cfg.proxy_port))
        ttk.Entry(row, textvariable=self.v_port, width=7).pack(side="left", padx=6)
        ttk.Button(row, text="Save", command=self._save_settings).pack(side="left", padx=6)
        self.v_clear_start = tk.BooleanVar(value=self.cfg.clear_cache_on_start)
        ttk.Checkbutton(
            f,
            text="Clear Roblox's cache when the proxy starts (only if Roblox is closed)",
            variable=self.v_clear_start,
            command=self._save_settings,
        ).pack(anchor="w")

        ttk.Separator(f).pack(fill="x", pady=12)
        ttk.Label(f, text="Roblox", style="Title.TLabel").pack(anchor="w")
        btns = ttk.Frame(f)
        btns.pack(anchor="w", pady=6)
        ttk.Button(btns, text="Install certificate", command=self._install_cert).pack(side="left")
        ttk.Button(btns, text="Remove certificate", command=self._uninstall_cert).pack(side="left", padx=6)
        ttk.Button(btns, text="Clear Roblox cache", command=self._clear_cache).pack(side="left")
        ttk.Button(btns, text="Open Proxion folder", command=lambda: self._open_path(str(cfgmod.app_dir()))).pack(
            side="left", padx=6
        )

        ttk.Separator(f).pack(fill="x", pady=12)
        ttk.Label(f, text="Proxy output", style="Title.TLabel").pack(anchor="w")
        self.out_txt = tk.Text(f, height=10, bg=PANEL, fg=MUTED, relief="flat", font=("Consolas", 9))
        self.out_txt.pack(fill="both", expand=True, pady=(6, 0))
        return f

    def _save_settings(self) -> None:
        self.cfg.proxy_mode = self.v_pmode.get()
        self.cfg.capture_process = self.v_proc.get().strip() or "RobloxPlayerBeta"
        if self.v_port.get().isdigit():
            self.cfg.proxy_port = int(self.v_port.get())
        self.cfg.clear_cache_on_start = self.v_clear_start.get()
        cfgmod.save_settings(self.cfg)

    def _install_cert(self, quiet: bool = False) -> None:
        try:
            patched, failed = roblox.install_cert()
        except OSError as e:
            messagebox.showerror("Proxion", f"Could not install certificate: {e}")
            return
        if failed:
            messagebox.showwarning(
                "Proxion",
                "Could not install the certificate in:\n" + "\n".join(failed) + "\n\nTry running Proxion as admin.",
            )
        if not roblox.version_dirs():
            if not quiet:
                messagebox.showwarning("Proxion", "No Roblox install found. Install Roblox, then try again.")
        elif not quiet:
            messagebox.showinfo(
                "Proxion",
                f"Certificate installed in {len(patched)} new Roblox folder(s)."
                if patched
                else "Certificate is already installed.",
            )

    def _uninstall_cert(self) -> None:
        cleaned, failed = roblox.uninstall_cert()
        msg = f"Removed the certificate from {len(cleaned)} Roblox folder(s)."
        if failed:
            msg += "\n\nCould not clean:\n" + "\n".join(failed)
        messagebox.showinfo("Proxion", msg)

    def _clear_cache(self) -> None:
        if roblox.is_running():
            if not messagebox.askyesno(
                "Proxion", "Roblox is open, so its cache is locked.\n\nClose Roblox now and clear the cache?"
            ):
                return
            if not roblox.close_roblox() or roblox.is_running():
                messagebox.showwarning("Proxion", "Couldn't close Roblox. Close it (and Roblox Studio) and try again.")
                return
        try:
            removed = roblox.clear_cache()
        except RuntimeError as e:
            messagebox.showwarning("Proxion", str(e))
            return
        messagebox.showinfo("Proxion", f"Cache cleared ({len(removed)} location(s)). Join your game again.")

    # ================================================================ Help tab
    def _help_tab(self, parent) -> ttk.Frame:
        f = ttk.Frame(parent, padding=(14, 10))
        canvas = tk.Canvas(f, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(f, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def wheel(event):
            if self.nb.select() == str(self.tab_help):
                delta = -1 if (getattr(event, "delta", 0) > 0 or event.num == 4) else 1
                canvas.yview_scroll(delta * 3, "units")

        self.bind_all("<MouseWheel>", wheel, add="+")
        self.bind_all("<Button-4>", wheel, add="+")
        self.bind_all("<Button-5>", wheel, add="+")

        ttk.Label(inner, text="Getting started", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            inner,
            text="Follow these steps in order. Each step has a button that does it for you.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(0, 8))
        actions = {
            "install_cert": self._install_cert,
            "start": lambda: None if self.runner.running else self._toggle(),
            "import": self._open_config,
            "replacer": lambda: self.nb.select(self.tab_replacer),
            "scraped": lambda: (self.nb.select(self.tab_replacer), self._scraped_games()),
            "log": lambda: self.nb.select(self.tab_log),
            "clear_cache": self._clear_cache,
        }
        for n, (title, body, buttons) in enumerate(help_text.STEPS, 1):
            box = ttk.Frame(inner, padding=(0, 4))
            box.pack(fill="x")
            tk.Label(box, text=str(n), bg=ACCENT, fg="white", width=3, font=("Segoe UI", 11, "bold")).pack(
                side="left", anchor="n", padx=(0, 10)
            )
            col = ttk.Frame(box)
            col.pack(side="left", fill="x", expand=True)
            ttk.Label(col, text=title, style="Bold.TLabel").pack(anchor="w")
            ttk.Label(col, text=body, wraplength=760, justify="left").pack(anchor="w")
            if buttons:
                row = ttk.Frame(col)
                row.pack(anchor="w", pady=(4, 0))
                for label, action in buttons:
                    ttk.Button(row, text=label, command=actions[action]).pack(side="left", padx=(0, 6))

        ttk.Separator(inner).pack(fill="x", pady=12)
        ttk.Label(inner, text="Something not working?", style="Title.TLabel").pack(anchor="w", pady=(0, 4))
        for title, body in help_text.TROUBLESHOOTING:
            ttk.Label(inner, text=title, style="Bold.TLabel").pack(anchor="w", pady=(4, 0))
            ttk.Label(inner, text=body, wraplength=780, justify="left").pack(anchor="w")

        ttk.Separator(inner).pack(fill="x", pady=12)
        links = ttk.Frame(inner)
        links.pack(anchor="w", pady=(0, 10))
        ttk.Button(links, text="Open the full user guide", command=lambda: webbrowser.open(help_text.GUIDE_URL)).pack(
            side="left"
        )
        ttk.Button(links, text="Keybinds", command=lambda: self._info("Replacer", help_text.KEYBINDS)).pack(
            side="left", padx=6
        )
        ttk.Button(links, text="Show welcome again", command=self._welcome).pack(side="left")
        return f

    def _welcome(self) -> None:
        self.nb.select(self.tab_help)
        messagebox.showinfo("Welcome to Proxion", help_text.WELCOME)
        self.cfg.seen_welcome = True
        cfgmod.save_settings(self.cfg)

    def _info(self, title: str, text: str) -> None:
        win = tk.Toplevel(self)
        win.title(title)
        win.configure(bg=BG)
        win.transient(self)
        tk.Label(win, text=text, bg=BG, fg=FG, justify="left", font=("Consolas", 10), padx=16, pady=14).pack()
        ttk.Button(win, text="OK", command=win.destroy).pack(pady=(0, 12))
        win.bind("<Escape>", lambda e: win.destroy())
        win.bind("<Return>", lambda e: win.destroy())

    # ================================================================ proxy
    def _toggle(self) -> None:
        if self.runner.running:
            self.runner.stop()
        else:
            self._save_settings()
            self._install_cert(quiet=True)  # Roblox updates make new folders
            if self.cfg.clear_cache_on_start and not roblox.is_running():
                with contextlib.suppress(RuntimeError, OSError):
                    roblox.clear_cache()
            try:
                self.runner.start(self.cfg)
            except (OSError, ValueError) as e:
                messagebox.showerror("Proxion", f"Could not start the proxy: {e}")
        self._update_status()

    def _update_status(self) -> None:
        if self.runner.running:
            self.status.configure(text="● running", fg=GREEN)
            self.toggle_btn.configure(text="Stop proxy")
        else:
            self.status.configure(text="● stopped", fg=RED)
            self.toggle_btn.configure(text="Start proxy")

    def _watch_configs(self) -> None:
        """Pick up config files changed or dropped into the folder outside Proxion, like Fleasion."""
        names = tuple(cfgmod.list_configs())
        f = cfgmod.config_file(self.current)
        stamp = f.stat().st_mtime_ns if f.exists() else None
        if stamp != self._disk_stamp:
            self._switch_config(self.current)  # reloads and clears undo, the history no longer matches the file
        elif names != self._configs_stamp:
            self._configs_stamp = names
            self._refresh_all()

    def _tick(self) -> None:
        while not self.out_q.empty():
            self.out_txt.insert("end", self.out_q.get() + "\n")
            self.out_txt.see("end")
        lines = int(self.out_txt.index("end-1c").split(".")[0])
        if lines > MAX_OUTPUT_LINES:
            self.out_txt.delete("1.0", f"{lines - MAX_OUTPUT_LINES}.0")
        self._read_log()
        self._update_status()
        with contextlib.suppress(OSError):
            self._watch_configs()
        self.after(700, self._tick)

    def _on_close(self) -> None:
        self.runner.stop()
        self.destroy()


def main(open_paths: list[str] | None = None) -> None:
    app = App()
    if open_paths:  # files dragged onto Proxion.exe or opened with it
        app.after(300, lambda: app.open_files(open_paths))
    app.mainloop()
