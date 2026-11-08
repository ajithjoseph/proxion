"""Proxion desktop window (tkinter, ships with Python)."""

from __future__ import annotations

import json
import queue
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

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
        self.geometry("940x640")
        self.minsize(760, 480)
        self.configure(bg=BG)

        self.cfg = cfgmod.load()
        self.out_q: queue.Queue[str] = queue.Queue()
        self.runner = ProxyRunner(on_output=self.out_q.put)
        self.log_pos = 0
        self.seen: dict[int, dict] = {}

        self._style()
        self._build()
        self._refresh_rules()
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
        cols = ("on", "name", "targets", "mode", "replacement")
        self.rules_tv = ttk.Treeview(f, columns=cols, show="headings", selectmode="browse")
        for c, w in zip(cols, (30, 130, 150, 60, 160)):
            self.rules_tv.heading(c, text=c.title() if c != "on" else "")
            self.rules_tv.column(c, width=w, anchor="w")
        self.rules_tv.bind("<<TreeviewSelect>>", lambda e: self._load_selected())
        self.rules_tv.bind("<Double-1>", lambda e: self._toggle_selected())

        ed = ttk.Frame(f, padding=(12, 0, 0, 0))
        ed.pack(side="right", fill="y")
        self.rules_tv.pack(side="left", fill="both", expand=True)
        self.v_name = tk.StringVar()
        self.v_targets = tk.StringVar()
        self.v_mode = tk.StringVar(value=cfgmod.MODE_ID)
        self.v_repl = tk.StringVar()
        self.v_enabled = tk.BooleanVar(value=True)

        ttk.Label(ed, text="Name").pack(anchor="w")
        ttk.Entry(ed, textvariable=self.v_name, width=34).pack(fill="x", pady=(0, 8))
        ttk.Label(ed, text="Asset IDs to replace (comma or space separated)").pack(anchor="w")
        ttk.Entry(ed, textvariable=self.v_targets, width=34).pack(fill="x", pady=(0, 8))
        ttk.Label(ed, text="Replace with").pack(anchor="w")
        modes = ttk.Frame(ed)
        modes.pack(anchor="w", pady=(0, 4))
        for label, val in (("Asset ID", cfgmod.MODE_ID), ("Local file", cfgmod.MODE_FILE), ("Remove", cfgmod.MODE_REMOVE)):
            ttk.Radiobutton(modes, text=label, value=val, variable=self.v_mode, command=self._mode_changed).pack(side="left", padx=(0, 8))
        row = ttk.Frame(ed)
        row.pack(fill="x", pady=(0, 8))
        self.repl_entry = ttk.Entry(row, textvariable=self.v_repl)
        self.repl_entry.pack(side="left", fill="x", expand=True)
        self.browse_btn = ttk.Button(row, text="…", width=3, command=self._browse)
        self.browse_btn.pack(side="left", padx=(4, 0))
        ttk.Checkbutton(ed, text="Enabled", variable=self.v_enabled).pack(anchor="w", pady=(0, 10))

        ttk.Button(ed, text="Add as new rule", style="Accent.TButton", command=self._add_rule).pack(fill="x", pady=2)
        ttk.Button(ed, text="Update selected", command=self._update_rule).pack(fill="x", pady=2)
        ttk.Button(ed, text="Delete selected", command=self._delete_rule).pack(fill="x", pady=2)
        ttk.Separator(ed).pack(fill="x", pady=10)
        ttk.Button(ed, text="Import rules…", command=self._import).pack(fill="x", pady=2)
        ttk.Button(ed, text="Export rules…", command=self._export).pack(fill="x", pady=2)
        ttk.Label(ed, text="Changes apply instantly while the proxy\nruns. Clear the cache or rejoin so Roblox\ndownloads the assets again.",
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

    # ---- rules ---------------------------------------------------------
    def _refresh_rules(self) -> None:
        self.rules_tv.delete(*self.rules_tv.get_children())
        for i, r in enumerate(self.cfg.rules):
            repl = {"remove": "(removed)"}.get(r.mode, r.replacement)
            self.rules_tv.insert("", "end", iid=str(i), values=(
                "✔" if r.enabled else "✖", r.name, ", ".join(map(str, r.targets)), r.mode, repl))

    def _form_rule(self) -> cfgmod.Rule | None:
        raw = self.v_targets.get().replace(",", " ").split()
        bad = [t for t in raw if not t.isdigit()]
        if bad or not raw:
            messagebox.showerror("Proxion", "Asset IDs must be numbers, like 1234567890.")
            return None
        mode = self.v_mode.get()
        repl = self.v_repl.get().strip()
        if mode == cfgmod.MODE_ID and not repl.isdigit():
            messagebox.showerror("Proxion", "Replacement must be a numeric asset ID.")
            return None
        if mode == cfgmod.MODE_FILE and not repl:
            messagebox.showerror("Proxion", "Pick a file to use as the replacement.")
            return None
        return cfgmod.Rule(name=self.v_name.get().strip() or "Rule", enabled=self.v_enabled.get(),
                           targets=[int(t) for t in raw], mode=mode,
                           replacement="" if mode == cfgmod.MODE_REMOVE else repl)

    def _selected(self) -> int | None:
        sel = self.rules_tv.selection()
        return int(sel[0]) if sel else None

    def _load_selected(self) -> None:
        i = self._selected()
        if i is None:
            return
        r = self.cfg.rules[i]
        self.v_name.set(r.name)
        self.v_targets.set(", ".join(map(str, r.targets)))
        self.v_mode.set(r.mode)
        self.v_repl.set(r.replacement)
        self.v_enabled.set(r.enabled)
        self._mode_changed()

    def _persist(self) -> None:
        cfgmod.save(self.cfg)
        self._refresh_rules()

    def _add_rule(self) -> None:
        r = self._form_rule()
        if r:
            self.cfg.rules.append(r)
            self._persist()

    def _update_rule(self) -> None:
        i = self._selected()
        r = self._form_rule() if i is not None else None
        if r:
            self.cfg.rules[i] = r
            self._persist()
            self.rules_tv.selection_set(str(i))

    def _delete_rule(self) -> None:
        i = self._selected()
        if i is not None:
            del self.cfg.rules[i]
            self._persist()

    def _toggle_selected(self) -> None:
        i = self._selected()
        if i is not None:
            self.cfg.rules[i].enabled = not self.cfg.rules[i].enabled
            self._persist()
            self.rules_tv.selection_set(str(i))

    def _mode_changed(self) -> None:
        m = self.v_mode.get()
        self.repl_entry.configure(state="disabled" if m == cfgmod.MODE_REMOVE else "normal")
        self.browse_btn.configure(state="normal" if m == cfgmod.MODE_FILE else "disabled")

    def _browse(self) -> None:
        p = filedialog.askopenfilename(title="Replacement file", filetypes=[
            ("Common assets", "*.png *.jpg *.jpeg *.ogg *.mp3 *.mesh *.rbxm *.ktx"), ("All files", "*.*")])
        if p:
            self.v_repl.set(p)

    def _import(self) -> None:
        p = filedialog.askopenfilename(filetypes=[("Proxion rules", "*.json")])
        if not p:
            return
        try:
            data = json.loads(open(p, encoding="utf-8").read())
            rules = data.get("rules", data) if isinstance(data, dict) else data
            self.cfg.rules.extend(cfgmod.Rule.from_dict(r) for r in rules)
        except (OSError, ValueError, AttributeError, TypeError) as e:
            messagebox.showerror("Proxion", f"Could not import: {e}")
            return
        self._persist()

    def _export(self) -> None:
        p = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("Proxion rules", "*.json")])
        if p:
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"rules": [r.__dict__ for r in self.cfg.rules]}, f, indent=2)

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
        cfgmod.save(self.cfg)

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


def main() -> None:
    App().mainloop()
