"""Proxion desktop window (tkinter, ships with Python)."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import config as cfgmod
from . import roblox
from .proxy import ProxyRunner

BG = "#16161d"
PANEL = "#1f1f29"
FG = "#e6e6f0"
ACCENT = "#7c5cff"
MUTED = "#8a8aa0"


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Proxion")
        self.geometry("1000x660")
        self.minsize(760, 480)
        self.configure(bg=BG)

        self.cfg = cfgmod.load_settings()
        self.current = self.cfg.last_config
        self.data = cfgmod.empty_config()
        self.out_q: queue.Queue[str] = queue.Queue()
        self.runner = ProxyRunner(on_output=self.out_q.put)
        self.log_pos = 0
        self.seen: dict[int, dict] = {}

        self._style()
        self._build()
        self._switch_config(self.current)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(500, self._tick)

    # ---- look -----------------------------------------------------------
    def _style(self) -> None:
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=FG, fieldbackground=PANEL, bordercolor=PANEL)
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", background=PANEL, foreground=MUTED, padding=(14, 6))
        s.map("TNotebook.Tab", background=[("selected", ACCENT)], foreground=[("selected", "white")])
        s.configure("TButton", background=PANEL, foreground=FG, padding=(10, 5), borderwidth=0)
        s.map("TButton", background=[("active", "#2c2c3a")])
        s.configure("Accent.TButton", background=ACCENT, foreground="white")
        s.map("Accent.TButton", background=[("active", "#6a4ae8")])
        s.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG, rowheight=24, borderwidth=0)
        s.configure("Treeview.Heading", background=BG, foreground=MUTED, borderwidth=0)
        s.map("Treeview", background=[("selected", ACCENT)])
        s.configure("TLabel", background=BG, foreground=FG)
        s.configure("Muted.TLabel", foreground=MUTED)
        s.configure("TEntry", foreground=FG, insertcolor=FG)
        s.configure("TCheckbutton", background=BG, foreground=FG)
        s.configure("TRadiobutton", background=BG, foreground=FG)
        s.configure("TFrame", background=BG)
        s.configure("Small.TButton", padding=(8, 2))
        s.configure("TCombobox", fieldbackground=PANEL, background=PANEL, foreground=FG, arrowcolor=FG)
        s.map("TCombobox", fieldbackground=[("readonly", PANEL)], foreground=[("readonly", FG)],
              selectbackground=[("readonly", PANEL)], selectforeground=[("readonly", FG)])
        self.option_add("*TCombobox*Listbox.background", PANEL)
        self.option_add("*TCombobox*Listbox.foreground", FG)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)

    # ---- layout ---------------------------------------------------------
    def _build(self) -> None:
        top = ttk.Frame(self, padding=(14, 10))
        top.pack(fill="x")
        tk.Label(top, text="Proxion", bg=BG, fg=FG, font=("Segoe UI", 18, "bold")).pack(side="left")
        tk.Label(top, text="  Roblox asset replacer", bg=BG, fg=MUTED, font=("Segoe UI", 10)).pack(side="left")
        self.toggle_btn = ttk.Button(top, text="Start proxy", style="Accent.TButton", command=self._toggle)
        self.toggle_btn.pack(side="right")
        self.status = tk.Label(top, text="● stopped", bg=BG, fg="#ff6b6b", font=("Segoe UI", 10))
        self.status.pack(side="right", padx=12)

        nb = self.nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        nb.add(self._rules_tab(nb), text="Replacements")
        nb.add(self._log_tab(nb), text="Asset log")
        nb.add(self._tools_tab(nb), text="Setup & tools")

    def _rules_tab(self, parent) -> ttk.Frame:
        f = ttk.Frame(parent, padding=8)

        # config bar: pick which config to edit, turn it on/off, manage files
        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=(0, 4))
        ttk.Label(bar, text="Config").pack(side="left")
        self.v_config = tk.StringVar()
        self.config_cb = ttk.Combobox(bar, textvariable=self.v_config, state="readonly", width=26)
        self.config_cb.pack(side="left", padx=6)
        self.config_cb.bind("<<ComboboxSelected>>", lambda e: self._switch_config(self.v_config.get()))
        self.v_cfg_on = tk.BooleanVar()
        ttk.Checkbutton(bar, text="Turned on", variable=self.v_cfg_on, command=self._toggle_config).pack(side="left", padx=4)
        ttk.Button(bar, text="Folder", command=self._open_folder).pack(side="right", padx=2)
        ttk.Button(bar, text="Export…", command=self._export).pack(side="right", padx=2)
        ttk.Button(bar, text="Open config…", style="Accent.TButton", command=self._open_config).pack(side="right", padx=2)

        bar2 = ttk.Frame(f)
        bar2.pack(fill="x", pady=(0, 6))
        for text, cmd in (("New", self._new_config), ("Duplicate", self._dup_config),
                          ("Rename", self._rename_config), ("Delete", self._del_config)):
            ttk.Button(bar2, text=text, style="Small.TButton", command=cmd).pack(side="left", padx=(0, 4))
        self.active_lbl = ttk.Label(bar2, style="Muted.TLabel")
        self.active_lbl.pack(side="left", padx=10)

        body = ttk.Frame(f)
        body.pack(fill="both", expand=True)
        cols = ("on", "targets", "mode", "with")
        self.rules_tv = ttk.Treeview(body, columns=cols, show="tree headings", selectmode="browse")
        self.rules_tv.heading("#0", text="Name")
        self.rules_tv.column("#0", width=170)
        for c, w in zip(cols, (30, 150, 55, 150)):
            self.rules_tv.heading(c, text={"on": "", "with": "Replacement"}.get(c, c.title()))
            self.rules_tv.column(c, width=w, anchor="w")
        self.rules_tv.bind("<<TreeviewSelect>>", lambda e: self._load_selected())
        self.rules_tv.bind("<Double-1>", lambda e: self._toggle_selected())

        ed = ttk.Frame(body, padding=(12, 0, 0, 0))
        ed.pack(side="right", fill="y")
        self.rules_tv.pack(side="left", fill="both", expand=True)
        self.v_name = tk.StringVar()
        self.v_targets = tk.StringVar()
        self.v_mode = tk.StringVar(value=cfgmod.MODE_ID)
        self.v_repl = tk.StringVar()
        self.v_enabled = tk.BooleanVar(value=True)

        ttk.Label(ed, text="Name").pack(anchor="w")
        ttk.Entry(ed, textvariable=self.v_name, width=34).pack(fill="x", pady=(0, 8))
        ttk.Label(ed, text="Replace (asset IDs, or types like Hat, Decal)").pack(anchor="w")
        ttk.Entry(ed, textvariable=self.v_targets, width=34).pack(fill="x", pady=(0, 8))
        ttk.Label(ed, text="Replace with").pack(anchor="w")
        modes = ttk.Frame(ed)
        modes.pack(anchor="w", pady=(0, 4))
        for label, val in (("Asset ID", cfgmod.MODE_ID), ("File", cfgmod.MODE_LOCAL),
                           ("URL", cfgmod.MODE_CDN), ("Remove", cfgmod.MODE_REMOVE)):
            ttk.Radiobutton(modes, text=label, value=val, variable=self.v_mode, command=self._mode_changed).pack(side="left", padx=(0, 6))
        row = ttk.Frame(ed)
        row.pack(fill="x", pady=(0, 8))
        self.repl_entry = ttk.Entry(row, textvariable=self.v_repl)
        self.repl_entry.pack(side="left", fill="x", expand=True)
        self.browse_btn = ttk.Button(row, text="…", width=3, command=self._browse)
        self.browse_btn.pack(side="left", padx=(4, 0))
        ttk.Checkbutton(ed, text="Enabled", variable=self.v_enabled).pack(anchor="w", pady=(0, 10))

        ttk.Button(ed, text="Add rule", style="Accent.TButton", command=self._add_rule).pack(fill="x", pady=2)
        ttk.Button(ed, text="Update selected", command=self._update_rule).pack(fill="x", pady=2)
        ttk.Button(ed, text="Delete selected", command=self._delete_rule).pack(fill="x", pady=2)
        ttk.Button(ed, text="New group", command=self._add_group).pack(fill="x", pady=2)
        ttk.Label(ed, text="Select a group first to add rules into it.\nDouble click turns a rule on or off.\n"
                           "Clear the cache or rejoin so Roblox\ndownloads the assets again.",
                  style="Muted.TLabel", justify="left").pack(anchor="w", pady=(12, 0))
        self._mode_changed()
        return f

    def _log_tab(self, parent) -> ttk.Frame:
        f = ttk.Frame(parent, padding=8)
        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=(0, 6))
        self.v_filter = tk.StringVar()
        ttk.Label(bar, text="Filter").pack(side="left")
        e = ttk.Entry(bar, textvariable=self.v_filter, width=30)
        e.pack(side="left", padx=6)
        self.v_filter.trace_add("write", lambda *a: self._redraw_log())
        ttk.Button(bar, text="Use selected as target", command=self._log_to_rule).pack(side="right")
        ttk.Button(bar, text="Copy ID", command=self._copy_id).pack(side="right", padx=6)
        ttk.Button(bar, text="Clear log", command=self._clear_log).pack(side="right")

        cols = ("id", "type", "action", "replacement", "hits")
        self.log_tv = ttk.Treeview(f, columns=cols, show="headings")
        for c, w in zip(cols, (140, 120, 80, 260, 60)):
            self.log_tv.heading(c, text=c.title())
            self.log_tv.column(c, width=w, anchor="w")
        self.log_tv.pack(fill="both", expand=True)
        ttk.Label(f, text="Every asset Roblox loads while the proxy is on shows up here. Join a game to fill it.",
                  style="Muted.TLabel").pack(anchor="w", pady=(6, 0))
        return f

    def _tools_tab(self, parent) -> ttk.Frame:
        f = ttk.Frame(parent, padding=14)
        ttk.Label(f, text="Capture mode", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.v_pmode = tk.StringVar(value=self.cfg.proxy_mode)
        ttk.Radiobutton(f, text="Local capture: only grabs Roblox's traffic, nothing else on your PC (recommended)",
                        value="local", variable=self.v_pmode, command=self._save_settings).pack(anchor="w")
        ttk.Radiobutton(f, text="Regular proxy on a port (advanced, you route traffic to it yourself)",
                        value="regular", variable=self.v_pmode, command=self._save_settings).pack(anchor="w")
        row = ttk.Frame(f)
        row.pack(anchor="w", pady=6)
        ttk.Label(row, text="Process").pack(side="left")
        self.v_proc = tk.StringVar(value=self.cfg.capture_process)
        ttk.Entry(row, textvariable=self.v_proc, width=22).pack(side="left", padx=6)
        ttk.Label(row, text="Port").pack(side="left", padx=(10, 0))
        self.v_port = tk.StringVar(value=str(self.cfg.proxy_port))
        ttk.Entry(row, textvariable=self.v_port, width=7).pack(side="left", padx=6)
        ttk.Button(row, text="Save", command=self._save_settings).pack(side="left", padx=6)

        ttk.Separator(f).pack(fill="x", pady=12)
        ttk.Label(f, text="Roblox", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        btns = ttk.Frame(f)
        btns.pack(anchor="w", pady=6)
        ttk.Button(btns, text="Install certificate", command=self._install_cert).pack(side="left")
        ttk.Button(btns, text="Remove certificate", command=self._uninstall_cert).pack(side="left", padx=6)
        ttk.Button(btns, text="Clear Roblox cache", command=self._clear_cache).pack(side="left")

        ttk.Separator(f).pack(fill="x", pady=12)
        ttk.Label(f, text="Proxy output", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.out_txt = tk.Text(f, height=10, bg=PANEL, fg=MUTED, relief="flat", font=("Consolas", 9))
        self.out_txt.pack(fill="both", expand=True, pady=(6, 0))
        return f

    # ---- configs -------------------------------------------------------
    def _switch_config(self, name: str) -> None:
        if name not in cfgmod.list_configs():
            name = cfgmod.list_configs()[0]
        self.current = name
        self.data = cfgmod.read_config(name)
        self.cfg.last_config = name
        cfgmod.save_settings(self.cfg)
        self._refresh_configs()

    def _refresh_configs(self) -> None:
        names = cfgmod.list_configs()
        self.cfg.enabled_configs = [n for n in self.cfg.enabled_configs if n in names]
        self.config_cb.configure(values=names)
        self.v_config.set(self.current)
        self.v_cfg_on.set(self.current in self.cfg.enabled_configs)
        on = ", ".join(self.cfg.enabled_configs) or "none (turn a config on so the proxy uses it)"
        self.active_lbl.configure(text=f"Turned on: {on}")
        self._refresh_rules()

    def _toggle_config(self) -> None:
        en = [n for n in self.cfg.enabled_configs if n != self.current]
        if self.v_cfg_on.get():
            en.append(self.current)
        self.cfg.enabled_configs = en
        cfgmod.save_settings(self.cfg)
        self._refresh_configs()

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
        self._switch_config(cfgmod.duplicate_config(self.current))

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
        if not messagebox.askyesno("Proxion", f'Delete the config "{self.current}"?'):
            return
        try:
            cfgmod.delete_config(self.current, self.cfg)
        except ValueError as e:
            messagebox.showerror("Proxion", str(e))
            return
        self._switch_config(self.cfg.last_config)

    def _open_config(self) -> None:
        paths = filedialog.askopenfilenames(title="Open config (Proxion or Fleasion)",
                                            filetypes=[("Configs", "*.json"), ("All files", "*.*")])
        if paths:
            self.open_files(paths)

    def open_files(self, paths) -> None:
        """Copy config files into the configs folder, turn them on and show the last one."""
        opened, failed, last = [], [], None
        for p in paths:
            try:
                last = cfgmod.import_config(p)
            except (OSError, ValueError) as e:
                failed.append(f"{os.path.basename(p)}: {e}")
                continue
            if last not in self.cfg.enabled_configs:
                self.cfg.enabled_configs.append(last)
            data = cfgmod.read_config(last)
            n = sum(1 for _ in cfgmod.iter_rules(data["replacement_rules"]))
            skipped = cfgmod.compile_rules([data]).skipped
            note = f" ({skipped} target(s) Proxion can't use yet, they're kept in the file)" if skipped else ""
            opened.append(f"{last}: {n} rule(s){note}")
        if last:
            self._switch_config(last)
        msg = ""
        if opened:
            msg += "Opened and turned on:\n" + "\n".join(opened)
        if failed:
            msg += ("\n\n" if msg else "") + "Could not open:\n" + "\n".join(failed)
        (messagebox.showerror if failed and not opened else messagebox.showinfo)("Proxion", msg)

    def _export(self) -> None:
        p = filedialog.asksaveasfilename(defaultextension=".json", initialfile=f"{self.current}.json",
                                         filetypes=[("Config", "*.json")])
        if p:
            cfgmod.export_config(self.current, p)

    def _open_folder(self) -> None:
        d = str(cfgmod.configs_dir())
        try:
            if sys.platform == "win32":
                os.startfile(d)  # noqa: S606
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", d])
        except OSError:
            messagebox.showinfo("Proxion", f"Configs folder:\n{d}")

    # ---- rules ---------------------------------------------------------
    def _node(self, path: tuple) -> dict:
        items = self.data["replacement_rules"]
        node = None
        for i in path:
            node = items[i]
            items = node.setdefault("children", []) if node.get("type") == "group" else []
        return node

    def _parent_list(self, path: tuple) -> list:
        return self._node(path[:-1]).setdefault("children", []) if len(path) > 1 else self.data["replacement_rules"]

    def _refresh_rules(self) -> None:
        tv = self.rules_tv
        tv.delete(*tv.get_children())

        def add(parent_iid: str, items: list, path: tuple) -> None:
            for i, r in enumerate(items):
                if not isinstance(r, dict):
                    continue
                p = path + (i,)
                iid = "/".join(map(str, p))
                on = "✔" if r.get("enabled", True) is not False else "✖"
                if r.get("type") == "group":
                    tv.insert(parent_iid, "end", iid=iid, text=str(r.get("name", "Group")),
                              values=(on, "", "group", ""), open=r.get("expanded", True))
                    add(iid, r.get("children") or [], p)
                    continue
                mode = cfgmod.rule_mode(r)
                kind, value = cfgmod.rule_action(r)
                shown = "(removed)" if kind == cfgmod.MODE_REMOVE else {
                    cfgmod.MODE_ID: r.get("with_id"), cfgmod.MODE_LOCAL: r.get("local_path"),
                    cfgmod.MODE_CDN: r.get("cdn_url")}.get(mode, "")
                targets = ", ".join(map(str, r.get("replace_ids") or []))
                tv.insert(parent_iid, "end", iid=iid, text=str(r.get("name", "Rule")),
                          values=(on, targets, mode, shown))

        add("", self.data["replacement_rules"], ())

    def _selected_path(self) -> tuple | None:
        sel = self.rules_tv.selection()
        return tuple(int(x) for x in sel[0].split("/")) if sel else None

    def _form_rule(self) -> dict | None:
        raw = [t for t in self.v_targets.get().replace(",", " ").split() if t]
        if not raw:
            messagebox.showerror("Proxion", "Add at least one asset ID (or a type like Hat) to replace.")
            return None
        targets = [int(t) if t.isdigit() else t for t in raw]
        bad = [str(t) for t in targets if cfgmod.parse_target(t) is None]
        if bad and not messagebox.askyesno(
                "Proxion", "Proxion can't use these targets: " + ", ".join(bad) +
                "\n(IDs 1 to 80 and unknown names are ignored.)\n\nKeep them anyway?"):
            return None
        mode = self.v_mode.get()
        repl = self.v_repl.get().strip()
        if mode == cfgmod.MODE_ID and not repl.isdigit():
            messagebox.showerror("Proxion", "Replacement must be a numeric asset ID.")
            return None
        if mode in (cfgmod.MODE_LOCAL, cfgmod.MODE_CDN) and not repl:
            messagebox.showerror("Proxion", "Pick a file or enter a URL for the replacement.")
            return None
        rule = {"name": self.v_name.get().strip() or "Rule", "replace_ids": targets,
                "mode": mode, "enabled": self.v_enabled.get()}
        if mode == cfgmod.MODE_ID:
            rule["with_id"] = int(repl)
        elif mode == cfgmod.MODE_LOCAL:
            rule["local_path"] = repl
        elif mode == cfgmod.MODE_CDN:
            rule["cdn_url"] = repl
        return rule

    def _load_selected(self) -> None:
        path = self._selected_path()
        if path is None:
            return
        r = self._node(path)
        self.v_name.set(str(r.get("name", "")))
        self.v_enabled.set(r.get("enabled", True) is not False)
        if r.get("type") == "group":
            return
        self.v_targets.set(", ".join(map(str, r.get("replace_ids") or [])))
        mode = cfgmod.rule_mode(r)
        self.v_mode.set(mode)
        self.v_repl.set(str({cfgmod.MODE_ID: r.get("with_id"), cfgmod.MODE_LOCAL: r.get("local_path"),
                             cfgmod.MODE_CDN: r.get("cdn_url")}.get(mode) or ""))
        self._mode_changed()

    def _persist(self, select: tuple | None = None) -> None:
        cfgmod.write_config(self.current, self.data)
        self._refresh_rules()
        if select is not None:
            iid = "/".join(map(str, select))
            if self.rules_tv.exists(iid):
                self.rules_tv.selection_set(iid)
                self.rules_tv.see(iid)

    def _insert_target(self) -> tuple[list, tuple]:
        """Where a new item goes: inside the selected group, else next to the selection."""
        path = self._selected_path()
        if path is not None and self._node(path).get("type") == "group":
            return self._node(path).setdefault("children", []), path
        if path is not None and len(path) > 1:
            return self._parent_list(path), path[:-1]
        return self.data["replacement_rules"], ()

    def _add_rule(self) -> None:
        r = self._form_rule()
        if r:
            items, base = self._insert_target()
            items.append(r)
            self._persist(base + (len(items) - 1,))

    def _add_group(self) -> None:
        name = self._ask_name("Group name:")
        if name:
            items, base = self._insert_target()
            items.append({"type": "group", "name": name, "enabled": True, "expanded": True, "children": []})
            self._persist(base + (len(items) - 1,))

    def _update_rule(self) -> None:
        path = self._selected_path()
        if path is None:
            return
        node = self._node(path)
        if node.get("type") == "group":
            node["name"] = self.v_name.get().strip() or node.get("name", "Group")
            node["enabled"] = self.v_enabled.get()
            self._persist(path)
            return
        r = self._form_rule()
        if r:
            for k in ("with_id", "local_path", "cdn_url", "remove"):
                node.pop(k, None)
            node.update(r)  # keeps any extra keys Fleasion or other tools stored
            self._persist(path)

    def _delete_rule(self) -> None:
        path = self._selected_path()
        if path is None:
            return
        node = self._node(path)
        if node.get("type") == "group" and node.get("children") and not messagebox.askyesno(
                "Proxion", f'Delete the group "{node.get("name")}" and everything in it?'):
            return
        del self._parent_list(path)[path[-1]]
        self._persist()

    def _toggle_selected(self) -> None:
        path = self._selected_path()
        if path is not None:
            node = self._node(path)
            node["enabled"] = node.get("enabled", True) is False
            self._persist(path)

    def _mode_changed(self) -> None:
        m = self.v_mode.get()
        self.repl_entry.configure(state="disabled" if m == cfgmod.MODE_REMOVE else "normal")
        self.browse_btn.configure(state="normal" if m == cfgmod.MODE_LOCAL else "disabled")

    def _browse(self) -> None:
        p = filedialog.askopenfilename(title="Replacement file", filetypes=[
            ("Common assets", "*.png *.jpg *.jpeg *.ogg *.mp3 *.mesh *.obj *.rbxm *.ktx"), ("All files", "*.*")])
        if p:
            self.v_repl.set(p)

    # ---- asset log -----------------------------------------------------
    def _read_log(self) -> None:
        path = cfgmod.log_path()
        if not path.exists():
            return
        with open(path, encoding="utf-8") as f:
            f.seek(self.log_pos)
            lines = f.readlines()
            self.log_pos = f.tell()
        if not lines:
            return
        for line in lines:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            aid = e.get("assetId")
            cur = self.seen.setdefault(aid, {"type": "?", "hits": 0})
            if e.get("type") not in (None, "?"):
                cur["type"] = e["type"]
            cur["action"] = e.get("action", "none")
            cur["replacement"] = e.get("replacement")
            cur["hits"] += 1
        self._redraw_log()

    def _redraw_log(self) -> None:
        flt = self.v_filter.get().lower().strip()
        self.log_tv.delete(*self.log_tv.get_children())
        for aid, e in reversed(list(self.seen.items())):
            vals = (aid, e["type"], e.get("action", ""), e.get("replacement") or "", e["hits"])
            if flt and not any(flt in str(v).lower() for v in vals):
                continue
            self.log_tv.insert("", "end", values=vals)

    def _clear_log(self) -> None:
        self.seen.clear()
        try:
            cfgmod.log_path().write_text("")
        except OSError:
            pass
        self.log_pos = 0
        self._redraw_log()

    def _log_ids(self) -> list[str]:
        return [str(self.log_tv.item(i)["values"][0]) for i in self.log_tv.selection()]

    def _copy_id(self) -> None:
        ids = self._log_ids()
        if ids:
            self.clipboard_clear()
            self.clipboard_append(", ".join(ids))

    def _log_to_rule(self) -> None:
        ids = self._log_ids()
        if ids:
            self.v_targets.set(", ".join(ids))
            self.rules_tv.selection_remove(self.rules_tv.selection())
            self.nb.select(0)

    # ---- tools ---------------------------------------------------------
    def _save_settings(self) -> None:
        self.cfg.proxy_mode = self.v_pmode.get()
        self.cfg.capture_process = self.v_proc.get().strip() or "RobloxPlayerBeta"
        if self.v_port.get().isdigit():
            self.cfg.proxy_port = int(self.v_port.get())
        cfgmod.save_settings(self.cfg)

    def _install_cert(self, quiet: bool = False) -> None:
        try:
            patched = roblox.install_cert()
        except OSError as e:
            messagebox.showerror("Proxion", f"Could not install certificate: {e}")
            return
        if not roblox.version_dirs():
            if not quiet:
                messagebox.showwarning("Proxion", "No Roblox install found. Install Roblox, then try again.")
        elif not quiet:
            messagebox.showinfo("Proxion", f"Certificate installed in {len(patched)} new Roblox folder(s)."
                                if patched else "Certificate is already installed.")

    def _uninstall_cert(self) -> None:
        n = len(roblox.uninstall_cert())
        messagebox.showinfo("Proxion", f"Removed the certificate from {n} Roblox folder(s).")

    def _clear_cache(self) -> None:
        try:
            removed = roblox.clear_cache()
        except RuntimeError as e:
            messagebox.showwarning("Proxion", str(e))
            return
        messagebox.showinfo("Proxion", f"Cleared {len(removed)} cache location(s).")

    # ---- proxy ---------------------------------------------------------
    def _toggle(self) -> None:
        if self.runner.running:
            self.runner.stop()
        else:
            self._save_settings()
            self._install_cert(quiet=True)  # Roblox updates make new folders
            self.runner.start(self.cfg)
        self._update_status()

    def _update_status(self) -> None:
        if self.runner.running:
            self.status.configure(text="● running", fg="#5be38a")
            self.toggle_btn.configure(text="Stop proxy")
        else:
            self.status.configure(text="● stopped", fg="#ff6b6b")
            self.toggle_btn.configure(text="Start proxy")

    def _tick(self) -> None:
        while not self.out_q.empty():
            self.out_txt.insert("end", self.out_q.get() + "\n")
            self.out_txt.see("end")
        self._read_log()
        self._update_status()
        self.after(700, self._tick)

    def _on_close(self) -> None:
        self.runner.stop()
        self.destroy()


def main(open_paths: list[str] | None = None) -> None:
    app = App()
    if open_paths:  # files dragged onto Proxion.exe or opened with it
        app.after(300, lambda: app.open_files(open_paths))
    app.mainloop()
