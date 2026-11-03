"""Site Mockup Maker by Raddito - simple window. Paste links, pick options, press Make Mockups."""
import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox, filedialog
import json

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mockup_maker as mm  # noqa: E402

SETTINGS = HERE / "settings.txt"
URLS = HERE / "urls.txt"
STATE = HERE / "_data" / "app_state.json"

import styles  # noqa: E402

SCENES = [(k, f"{v[0]}  ({v[1][0]}x{v[1][1]})") for k, v in styles.STYLES.items()]
AUTO = "Each style's own size"
PRESETS = ["1920x1080", "1600x1200", "1200x900", "1080x1350", "1080x1080", "2000x2000", "2560x1440", "590x300"]
BGS = [("auto", "Match website (soft)"), ("brand", "Match website (strong color)"),
       ("site", "Website's page color"), ("white", "White"), ("custom", "My own color...")]

BG_UI = "#F3F4F8"
INK = "#1B2030"
MUTED = "#5E6678"
ACCENT = "#4F46E5"


def read_settings_text():
    try:
        return SETTINGS.read_text(encoding="utf-8-sig")
    except OSError:
        return ""


def set_setting(text, key, value):
    pat = re.compile(rf"^{re.escape(key)}\s*=.*$", re.M)
    line = f"{key} = {value}"
    return pat.sub(line, text, count=1) if pat.search(text) else text.rstrip() + "\n" + line + "\n"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Site Mockup Maker by Raddito")
        self.geometry("1300x860")
        self.minsize(1100, 700)
        self.configure(bg=BG_UI)
        self.proc = None
        self.q = queue.Queue()
        cfg = mm.load_settings(SETTINGS)
        self.cfg = cfg

        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure(".", background=BG_UI, foreground=INK, font=("Segoe UI", 10))
        st.configure("H.TLabel", font=("Segoe UI Semibold", 11), foreground=INK)
        st.configure("Muted.TLabel", foreground=MUTED, font=("Segoe UI", 9))
        st.configure("TCheckbutton", background=BG_UI)
        st.configure("TRadiobutton", background=BG_UI)
        st.configure("Go.TButton", font=("Segoe UI Semibold", 12), foreground="white", background=ACCENT, padding=(18, 10))
        st.map("Go.TButton", background=[("active", "#4338CA"), ("disabled", "#A5A8C8")])
        st.configure("TButton", padding=(10, 6))

        root = ttk.Frame(self, padding=16)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=3)
        root.columnconfigure(1, weight=2)
        root.rowconfigure(1, weight=1)

        # ---- left: links
        left = ttk.Frame(root)
        left.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 16))
        left.rowconfigure(2, weight=1)
        left.columnconfigure(0, weight=1)
        st0 = self.load_state()
        head = ttk.Frame(left); head.grid(row=0, column=0, sticky="ew")
        ttk.Label(head, text="1.  Make mockups from", style="H.TLabel").pack(side="left")
        self.mode = tk.StringVar(value=st0.get("mode", "links"))
        ttk.Radiobutton(head, text="Website links", value="links", variable=self.mode,
                        command=self.switch_mode).pack(side="left", padx=(12, 4))
        ttk.Radiobutton(head, text="My screenshots", value="shots", variable=self.mode,
                        command=self.switch_mode).pack(side="left", padx=4)
        self.hint = ttk.Label(left, text="", style="Muted.TLabel", wraplength=560, justify="left")
        self.hint.grid(row=1, column=0, sticky="w", pady=(4, 6))

        # links box
        self.links_box = ttk.Frame(left)
        self.links_box.rowconfigure(0, weight=1); self.links_box.columnconfigure(0, weight=1)
        self.links = tk.Text(self.links_box, height=10, wrap="none", font=("Consolas", 10), relief="solid", bd=1,
                             highlightthickness=0, padx=8, pady=6)
        self.links.grid(row=0, column=0, sticky="nsew")
        self.links.insert("1.0", self.load_links())

        # screenshots box
        self.shots_box = ttk.Frame(left)
        self.shots_box.rowconfigure(1, weight=1); self.shots_box.columnconfigure(0, weight=1)
        bt = ttk.Frame(self.shots_box); bt.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(bt, text="Add folder...", command=self.add_folder).pack(side="left")
        ttk.Button(bt, text="Add image files...", command=self.add_files).pack(side="left", padx=6)
        ttk.Button(bt, text="Remove selected", command=self.remove_sel).pack(side="left")
        ttk.Button(bt, text="Clear", command=lambda: self.paths.delete(0, "end")).pack(side="left", padx=6)
        self.paths = tk.Listbox(self.shots_box, height=8, relief="solid", bd=1, selectmode="extended",
                                font=("Segoe UI", 9), highlightthickness=0, activestyle="none")
        self.paths.grid(row=1, column=0, sticky="nsew")
        for pth in st0.get("paths", []):
            if Path(pth).exists():
                self.paths.insert("end", pth)
        self.switch_mode()

        ttk.Label(left, text="Progress", style="H.TLabel").grid(row=3, column=0, sticky="w", pady=(14, 4))
        self.bar = ttk.Progressbar(left, mode="determinate")
        self.bar.grid(row=4, column=0, sticky="ew")
        self.log = tk.Text(left, height=9, font=("Consolas", 9), relief="solid", bd=1, bg="#FBFBFD",
                           fg=INK, state="disabled", padx=8, pady=6)
        self.log.grid(row=5, column=0, sticky="nsew", pady=(6, 0))
        left.rowconfigure(5, weight=1)

        # ---- right: options
        right = ttk.Frame(root)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        r = 0
        ttk.Label(right, text="2.  Mockup size", style="H.TLabel").grid(row=r, column=0, sticky="w"); r += 1
        sz = ttk.Frame(right); sz.grid(row=r, column=0, sticky="ew", pady=(4, 0)); r += 1
        cur = cfg.get("size", "auto").split(",")[0].strip().lower()
        m = re.match(r"^(\d+)x(\d+)$", cur)
        self.size_mode = tk.StringVar(value="custom" if m else "own")
        self.w_var = tk.StringVar(value=m.group(1) if m else "2000")
        self.h_var = tk.StringVar(value=m.group(2) if m else "2000")
        ttk.Radiobutton(sz, text="Each style's own size (as in the samples)", value="own",
                        variable=self.size_mode).grid(row=0, column=0, columnspan=6, sticky="w")
        ttk.Radiobutton(sz, text="My custom size for ALL styles:", value="custom",
                        variable=self.size_mode).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ent = ttk.Frame(sz); ent.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(4, 0))
        we = ttk.Entry(ent, textvariable=self.w_var, width=6); we.pack(side="left")
        ttk.Label(ent, text=" x ").pack(side="left")
        he = ttk.Entry(ent, textvariable=self.h_var, width=6); he.pack(side="left")
        ttk.Label(ent, text=" px").pack(side="left")
        for e in (we, he):
            e.bind("<Key>", lambda ev: self.size_mode.set("custom"))
        ttk.Label(sz, text="or pick:").grid(row=1, column=2, padx=(12, 4), pady=(4, 0))
        cb = ttk.Combobox(sz, values=PRESETS, state="readonly", width=11)
        cb.grid(row=1, column=3, pady=(4, 0))

        def pick(_e=None):
            w, h = cb.get().split("x")
            self.w_var.set(w); self.h_var.set(h); self.size_mode.set("custom")
        cb.bind("<<ComboboxSelected>>", pick)
        ttk.Label(right, text="With a custom size, every mockup (all styles you tick) comes out exactly this size.",
                  style="Muted.TLabel").grid(row=r, column=0, sticky="w", pady=(4, 0)); r += 1
        zf = ttk.Frame(right); zf.grid(row=r, column=0, sticky="ew", pady=(8, 0)); r += 1
        ttk.Label(zf, text="Device size").pack(side="left")
        self.zoom = tk.IntVar(value=int(float(cfg.get("zoom", 100))))
        ttk.Scale(zf, from_=60, to=150, variable=self.zoom, command=lambda v: self.zoom_lbl.config(
            text=f"{int(float(v))}%")).pack(side="left", fill="x", expand=True, padx=8)
        self.zoom_lbl = ttk.Label(zf, text=f"{self.zoom.get()}%", width=5)
        self.zoom_lbl.pack(side="left")

        ttk.Label(right, text="3.  Styles to make", style="H.TLabel").grid(row=r, column=0, sticky="w", pady=(16, 2)); r += 1
        chosen = [s.strip() for s in cfg.get("scenes", mm.DEFAULT_SCENES).split(",")]
        self.scene_vars = {}
        grid = ttk.Frame(right); grid.grid(row=r, column=0, sticky="ew"); r += 1
        half = (len(SCENES) + 1) // 2
        for i, (key, label) in enumerate(SCENES):
            v = tk.BooleanVar(value=key in chosen)
            self.scene_vars[key] = v
            ttk.Checkbutton(grid, text=label, variable=v).grid(row=i % half, column=i // half, sticky="w", pady=1, padx=(0, 14))
        bf = ttk.Frame(right); bf.grid(row=r, column=0, sticky="w", pady=(4, 0)); r += 1
        ttk.Button(bf, text="Select all", command=lambda: [v.set(True) for v in self.scene_vars.values()]).pack(side="left")
        ttk.Button(bf, text="Select none", command=lambda: [v.set(False) for v in self.scene_vars.values()]).pack(side="left", padx=6)
        ttk.Button(bf, text="Edit panel text...", command=self.edit_text).pack(side="left")

        ttk.Label(right, text="4.  Background & look", style="H.TLabel").grid(row=r, column=0, sticky="w", pady=(16, 2)); r += 1
        bgf = ttk.Frame(right); bgf.grid(row=r, column=0, sticky="ew"); r += 1
        cur_bg = cfg.get("bg", "auto")
        self.bg_var = tk.StringVar(value=dict(BGS).get(cur_bg, "My own color..."))
        self.bg_custom = tk.StringVar(value=cur_bg if cur_bg.startswith("#") else "#EEF2FF")
        ttk.Combobox(bgf, textvariable=self.bg_var, values=[b for _, b in BGS], state="readonly", width=26).pack(side="left")
        ttk.Entry(bgf, textvariable=self.bg_custom, width=18).pack(side="left", padx=8)
        lf = ttk.Frame(right); lf.grid(row=r, column=0, sticky="ew", pady=(6, 0)); r += 1
        self.finish = tk.StringVar(value=cfg.get("finish", "black"))
        ttk.Label(lf, text="Devices:").pack(side="left")
        ttk.Radiobutton(lf, text="Black", value="black", variable=self.finish).pack(side="left", padx=6)
        ttk.Radiobutton(lf, text="Silver", value="silver", variable=self.finish).pack(side="left")
        pf = ttk.Frame(right); pf.grid(row=r, column=0, sticky="ew", pady=(6, 0)); r += 1
        ttk.Label(pf, text="Max pages per website").pack(side="left")
        self.src = tk.StringVar(value=cfg.get("page_source", "menu"))
        sf = ttk.Frame(right); sf.grid(row=r, column=0, sticky="w", pady=(6, 0)); r += 1
        ttk.Label(sf, text="Pages:").pack(side="left")
        ttk.Radiobutton(sf, text="Only pages in the menu", value="menu", variable=self.src).pack(side="left", padx=6)
        ttk.Radiobutton(sf, text="All pages of the website", value="all", variable=self.src).pack(side="left")
        self.max_pages = tk.IntVar(value=int(cfg.get("max_pages", 60)))
        ttk.Spinbox(pf, from_=1, to=300, textvariable=self.max_pages, width=5).pack(side="left", padx=8)
        self.reuse = tk.BooleanVar(value=False)
        ttk.Checkbutton(right, text="Reuse screenshots already taken (fast, for new styles/sizes)",
                        variable=self.reuse).grid(row=r, column=0, sticky="w", pady=(6, 0)); r += 1
        self.shots_only = tk.BooleanVar(value=False)
        self.shots_mobile = tk.BooleanVar(value=False)
        so = ttk.Frame(right); so.grid(row=r, column=0, sticky="w", pady=(6, 0)); r += 1
        ttk.Checkbutton(so, text="Only take website screenshots (all pages, no mockups)",
                        variable=self.shots_only).pack(side="left")
        self.shots_tablet = tk.BooleanVar(value=False)
        ttk.Checkbutton(so, text="+ tablet", variable=self.shots_tablet).pack(side="left", padx=(10, 0))
        ttk.Checkbutton(so, text="+ phone", variable=self.shots_mobile).pack(side="left", padx=10)
        ttk.Label(right, text="Presentation title text (style 11):").grid(row=r, column=0, sticky="w", pady=(8, 0)); r += 1
        tf = ttk.Frame(right); tf.grid(row=r, column=0, sticky="ew"); r += 1
        self.t_small = tk.StringVar(value=cfg.get("title_small", "Fully editable"))
        self.t_big = tk.StringVar(value=cfg.get("title_big", "Website template"))
        ttk.Entry(tf, textvariable=self.t_small, width=18).pack(side="left")
        ttk.Entry(tf, textvariable=self.t_big, width=22).pack(side="left", padx=6)

        # ---- bottom buttons
        bot = ttk.Frame(root)
        bot.grid(row=1, column=1, sticky="sew")
        self.go = ttk.Button(bot, text="Make Mockups", style="Go.TButton", command=self.start)
        self.go.pack(fill="x", pady=(16, 6))
        row = ttk.Frame(bot); row.pack(fill="x")
        self.stop_btn = ttk.Button(row, text="Stop", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left")
        ttk.Button(row, text="Open finished mockups", command=self.open_out).pack(side="right")
        self.status = ttk.Label(bot, text="Ready.", style="Muted.TLabel")
        self.status.pack(anchor="w", pady=(6, 0))

        self.after(150, self.poll)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------------------------------------------
    def load_links(self):
        try:
            lines = [l for l in URLS.read_text(encoding="utf-8-sig").splitlines() if l.strip() and not l.strip().startswith("#")]
        except OSError:
            lines = []
        return "\n".join(lines) + ("\n" if lines else "")

    def load_state(self):
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def save_state(self):
        try:
            STATE.parent.mkdir(exist_ok=True)
            STATE.write_text(json.dumps({"mode": self.mode.get(), "paths": list(self.paths.get(0, "end"))}), encoding="utf-8")
        except Exception:
            pass

    def switch_mode(self):
        if self.mode.get() == "links":
            self.shots_box.grid_forget()
            self.links_box.grid(row=2, column=0, sticky="nsew")
            self.hint.configure(text="One link per line. Optional name first:  Lumen Dental | https://demo.site.com/dental/")
        else:
            self.links_box.grid_forget()
            self.shots_box.grid(row=2, column=0, sticky="nsew")
            self.hint.configure(text="Add one folder per website (the folder name becomes the website name), or a folder "
                                     "that holds several website folders. Name files 01_Home.png, 02_About_Us.png ... to set "
                                     "the order. Add _Mobile (01_Home_Mobile.png) or _Tablet for phone and tablet screens.")

    def add_folder(self):
        d = filedialog.askdirectory(title="Choose a folder of website screenshots")
        if d and d not in self.paths.get(0, "end"):
            self.paths.insert("end", d)

    def add_files(self):
        fs = filedialog.askopenfilenames(title="Choose screenshots of one website",
                                         filetypes=[("Images", "*.png *.jpg *.jpeg *.webp"), ("All files", "*.*")])
        for f in fs:
            if f not in self.paths.get(0, "end"):
                self.paths.insert("end", f)

    def remove_sel(self):
        for i in reversed(self.paths.curselection()):
            self.paths.delete(i)

    def edit_text(self):
        win = tk.Toplevel(self)
        win.title("Edit panel text")
        win.geometry("700x720")
        win.configure(bg=BG_UI)
        ttk.Label(win, text="Text used on the mockups. Items: one per line. Saved for every run.",
                  style="Muted.TLabel").pack(anchor="w", padx=14, pady=(12, 6))
        bar = ttk.Frame(win); bar.pack(side="bottom", fill="x", padx=14, pady=10)
        cv = tk.Canvas(win, bg=BG_UI, highlightthickness=0)
        sb = ttk.Scrollbar(win, orient="vertical", command=cv.yview)
        inner = ttk.Frame(cv)
        inner.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.create_window((0, 0), window=inner, anchor="nw", width=620)
        cv.configure(yscrollcommand=sb.set)
        cv.pack(side="left", fill="both", expand=True, padx=(14, 0)); sb.pack(side="left", fill="y")
        cv.bind_all("<MouseWheel>", lambda e: cv.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        cur = styles.load_text()
        widgets = {}
        for key, label in styles.TEXT_LABELS.items():
            ttk.Label(inner, text=label).pack(anchor="w", pady=(8, 0))
            val = cur.get(key, "")
            if isinstance(styles.DEFAULT_TEXT.get(key), list):
                w = tk.Text(inner, height=max(2, min(8, len(val))), width=70, wrap="word")
                w.insert("1.0", "\n".join(val))
            else:
                w = ttk.Entry(inner, width=70); w.insert(0, val)
            w.pack(anchor="w", fill="x")
            widgets[key] = w

        def save():
            out = {}
            for key, w in widgets.items():
                if isinstance(w, tk.Text):
                    out[key] = [l.strip() for l in w.get("1.0", "end").splitlines() if l.strip()]
                else:
                    out[key] = w.get().strip()
            styles.save_text(out)
            cv.unbind_all("<MouseWheel>")
            win.destroy()

        def reset():
            for key, w in widgets.items():
                d = styles.DEFAULT_TEXT.get(key, "")
                if isinstance(w, tk.Text):
                    w.delete("1.0", "end"); w.insert("1.0", "\n".join(d))
                else:
                    w.delete(0, "end"); w.insert(0, d)
        ttk.Button(bar, text="Save", style="Go.TButton", command=save).pack(side="right")
        ttk.Button(bar, text="Back to original text", command=reset).pack(side="left")

    def chosen_size(self):
        if self.size_mode.get() == "own":
            return "auto"
        v = f"{self.w_var.get().strip()}x{self.h_var.get().strip()}"
        mm.parse_sizes(v)  # raises ValueError if wrong
        return v

    def out_dir(self):
        o = self.cfg.get("out")
        return Path(o) if o else mm.desktop_dir() / "Mockups"

    def open_out(self):
        d = self.out_dir()
        d.mkdir(parents=True, exist_ok=True)
        os.startfile(str(d)) if os.name == "nt" else subprocess.Popen(["xdg-open", str(d)])

    def write_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    # ------------------------------------------------------------
    def start(self):
        shots_mode = self.mode.get() == "shots"
        links = [l.strip() for l in self.links.get("1.0", "end").splitlines() if l.strip()]
        paths = list(self.paths.get(0, "end"))
        if shots_mode:
            found = mm.image_sites(paths) if paths else []
            if not found:
                messagebox.showinfo("Site Mockup Maker by Raddito", "Add a folder or image files with your screenshots (PNG, JPG or WebP).")
                return
            n_sites = len(found)
        else:
            if not links:
                messagebox.showinfo("Site Mockup Maker by Raddito", "Paste at least one website link in box 1.")
                return
            n_sites = len(links)
        self.save_state()
        scenes = [k for k, v in self.scene_vars.items() if v.get()]
        if self.shots_only.get() and shots_mode:
            messagebox.showinfo("Site Mockup Maker by Raddito", "Screenshots only works with website links (box 1). Switch to 'Website links'.")
            return
        if not scenes and not self.shots_only.get():
            messagebox.showinfo("Site Mockup Maker by Raddito", "Tick at least one style in box 3.")
            return
        try:
            size = self.chosen_size()
        except ValueError:
            messagebox.showerror("Site Mockup Maker by Raddito", "Custom size must be numbers between 200 and 8000, like 2400 x 1600.")
            return
        bg_label = self.bg_var.get()
        bg = {b: k for k, b in BGS}.get(bg_label, "auto")
        if bg == "custom":
            bg = self.bg_custom.get().replace(" ", "")
            if not re.match(r"^#[0-9a-fA-F]{6}(,#[0-9a-fA-F]{6})?$", bg):
                messagebox.showerror("Site Mockup Maker by Raddito", "Own color must look like #EEF2FF or #EEF2FF,#C7D2FE")
                return

        if not shots_mode:
            URLS.write_text("\n".join(links) + "\n", encoding="utf-8")
        txt = read_settings_text()
        for k, v in (("size", size), ("scenes", ", ".join(scenes)), ("background", bg), ("device_color", self.finish.get()),
                     ("device_size", str(int(self.zoom.get()))), ("max_pages", str(int(self.max_pages.get()))), ("page_source", self.src.get()),
                     ("title_small", self.t_small.get()), ("title_big", self.t_big.get()),
                     # one size for everything: clear any per-style sizes
                     *[(f"size_{k}", "") for k, _ in SCENES]):
            txt = set_setting(txt, k, v)
        SETTINGS.write_text(txt, encoding="utf-8")
        self.cfg = mm.load_settings(SETTINGS)

        py = Path(sys.executable)
        if py.name.lower() == "pythonw.exe":
            py = py.with_name("python.exe")
        flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
        self.log.configure(state="normal"); self.log.delete("1.0", "end"); self.log.configure(state="disabled")
        self.total_sites, self.done_sites = n_sites, 0
        self.bar.configure(maximum=max(1, self.total_sites), value=0)
        if shots_mode:
            args = [str(py), "-u", str(HERE / "mockup_maker.py"), "--images", *paths]
        else:
            args = [str(py), "-u", str(HERE / "mockup_maker.py"), str(URLS)] + (["--reuse"] if self.reuse.get() else []) \
                + (["--shots-only"] + (["--shots-mobile"] if self.shots_mobile.get() else []) + (["--shots-tablet"] if self.shots_tablet.get() else []) if self.shots_only.get() else [])
        self.proc = subprocess.Popen(args, cwd=str(HERE),
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                     text=True, encoding="utf-8", errors="replace", creationflags=flags,
                                     env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        threading.Thread(target=self.reader, daemon=True).start()
        self.go.configure(state="disabled", text="Working...")
        self.stop_btn.configure(state="normal")
        self.status.configure(text=f"Making mockups for {n_sites} website(s)...")

    def reader(self):
        for line in self.proc.stdout:
            self.q.put(line)
        self.q.put(None)

    def poll(self):
        try:
            while True:
                line = self.q.get_nowait()
                if line is None:
                    self.finished()
                    break
                self.write_log(line)
                m = re.search(r"\[(\d+)/(\d+)\]", line)
                if m:
                    self.bar.configure(value=int(m.group(1)) - 1)
                    self.status.configure(text=f"Website {m.group(1)} of {m.group(2)}...")
                if line.strip().startswith("Done") or " Done:" in line:
                    self.bar.configure(value=self.bar["maximum"])
        except queue.Empty:
            pass
        self.after(150, self.poll)

    def finished(self):
        code = self.proc.poll() if self.proc else 0
        self.proc = None
        self.go.configure(state="normal", text="Make Mockups")
        self.stop_btn.configure(state="disabled")
        if code == 0:
            self.bar.configure(value=self.bar["maximum"])
            self.status.configure(text="Done. Click 'Open finished mockups'.")
            if messagebox.askyesno("Site Mockup Maker by Raddito", "Mockups are ready. Open the folder now?"):
                self.open_out()
        else:
            self.status.configure(text="Stopped. See the progress box for details.")

    def stop(self):
        if self.proc:
            self.proc.terminate()

    def on_close(self):
        self.save_state()
        if self.proc and not messagebox.askyesno("Site Mockup Maker by Raddito", "Mockups are still being made. Stop and close?"):
            return
        self.stop()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
