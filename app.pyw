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

try:
    from PIL import Image, ImageTk
except Exception:      # preview panel simply stays hidden
    Image = ImageTk = None

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mockup_maker as mm  # noqa: E402

SETTINGS = HERE / "settings.txt"
URLS = HERE / "urls.txt"
STATE = HERE / "_data" / "app_state.json"
PREVIEWS = HERE / "previews"
THUMB = 66      # gallery thumbnail size
THUMB_BG = "#EDEFF5"
PV = 250        # preview box size in pixels

import styles  # noqa: E402

SCENES = [(k, f"{v[0]}  ({v[1][0]}x{v[1][1]})") for k, v in styles.STYLES.items()]
AUTO = "Each style's own size"
PRESETS = ["1920x1080", "1600x1200", "1200x900", "1080x1350", "1080x1080", "2000x2000", "2560x1440", "590x300"]
BGS = [("auto", "Match website (soft)"), ("brand", "Match website (strong color)"),
       ("site", "Website's page color"), ("white", "White"), ("custom", "My own color...")]

BG_UI = "#F4F5F9"
CARD = "#FFFFFF"
BORDER = "#E2E5EE"
ACCENT_SOFT = "#EEF0FF"
INK = "#151A2D"
MUTED = "#667085"
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
        self.geometry("1360x900")
        self.minsize(1240, 800)
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
        FONT = "Segoe UI"
        st.configure(".", background=BG_UI, foreground=INK, font=(FONT, 10))
        st.configure("TFrame", background=BG_UI)
        st.configure("TLabel", background=BG_UI, foreground=INK)
        st.configure("Card.TFrame", background=CARD)
        st.configure("Card.TLabel", background=CARD, foreground=INK)
        st.configure("H.TLabel", font=(FONT, 12, "bold"), foreground=INK, background=CARD)
        st.configure("Title.TLabel", font=(FONT, 17, "bold"), foreground=INK, background=BG_UI)
        st.configure("Sub.TLabel", font=(FONT, 10), foreground=MUTED, background=BG_UI)
        st.configure("Muted.TLabel", foreground=MUTED, font=(FONT, 9), background=CARD)
        st.configure("Status.TLabel", foreground=MUTED, font=(FONT, 9), background=BG_UI)
        st.configure("Card.TCheckbutton", background=CARD, foreground=INK)
        st.configure("Card.TRadiobutton", background=CARD, foreground=INK)
        for sty in ("Card.TCheckbutton", "Card.TRadiobutton"):
            st.map(sty, background=[("active", CARD)])
        st.configure("TEntry", fieldbackground="white", bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, padding=5)
        st.configure("TCombobox", fieldbackground="white", bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, padding=4)
        st.configure("TSpinbox", fieldbackground="white", bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, padding=4)
        st.configure("TButton", padding=(12, 7), background="#FFFFFF", bordercolor=BORDER, lightcolor="#FFFFFF", darkcolor="#FFFFFF")
        st.map("TButton", background=[("active", ACCENT_SOFT), ("disabled", "#F1F2F6")], foreground=[("disabled", "#A0A6B5")])
        st.configure("Small.TButton", padding=(8, 5), background="#FFFFFF", bordercolor=BORDER, lightcolor="#FFFFFF", darkcolor="#FFFFFF")
        st.map("Small.TButton", background=[("active", ACCENT_SOFT)])
        st.configure("Go.TButton", font=(FONT, 13, "bold"), foreground="white", background=ACCENT, padding=(20, 12),
                     bordercolor=ACCENT, lightcolor=ACCENT, darkcolor=ACCENT)
        st.map("Go.TButton", background=[("active", "#4338CA"), ("disabled", "#B9BBE0")], foreground=[("disabled", "white")])
        st.configure("Seg.Toolbutton", padding=(14, 6), background="#EEF0F6", foreground=MUTED, bordercolor="#EEF0F6",
                     font=(FONT, 10, "bold"))
        st.map("Seg.Toolbutton", background=[("selected", ACCENT), ("active", ACCENT_SOFT)],
               foreground=[("selected", "white")], bordercolor=[("selected", ACCENT)])
        st.configure("Horizontal.TProgressbar", troughcolor="#E8EAF2", background=ACCENT, bordercolor="#E8EAF2",
                     lightcolor=ACCENT, darkcolor=ACCENT, thickness=8)
        st.configure("Horizontal.TScale", background=CARD, troughcolor="#E1E4EE")

        def card(parent, title=None, sub=None, pad=16):
            """A white panel with a thin border. Returns the inner frame to put things in."""
            outer = tk.Frame(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
            inner = ttk.Frame(outer, style="Card.TFrame", padding=pad)
            inner.pack(fill="both", expand=True)
            if title:
                hd = ttk.Frame(inner, style="Card.TFrame"); hd.pack(fill="x", pady=(0, 8))
                ttk.Label(hd, text=title, style="H.TLabel").pack(side="left")
                if sub:
                    ttk.Label(hd, text=sub, style="Muted.TLabel").pack(side="left", padx=(10, 0), pady=(3, 0))
                inner.head = hd
            return outer, inner
        self.card = card

        root = ttk.Frame(self, padding=(22, 16, 22, 16))
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=0, minsize=420)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(1, weight=1)

        # ---- header
        top = ttk.Frame(root); top.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        logo = tk.Label(top, text="SM", bg=ACCENT, fg="white", font=(FONT, 12, "bold"), width=3, height=1)
        logo.pack(side="left", ipady=4)
        tt = ttk.Frame(top); tt.pack(side="left", padx=12)
        ttk.Label(tt, text="Site Mockup Maker", style="Title.TLabel").pack(anchor="w")
        ttk.Label(tt, text="by Raddito  -  paste links, pick styles, get finished mockups", style="Sub.TLabel").pack(anchor="w")

        # ---- left column: websites + progress
        left = ttk.Frame(root, width=420, height=10); left.grid(row=1, column=0, sticky="nsew", padx=(0, 18))
        left.grid_propagate(False)
        left.columnconfigure(0, weight=1)
        c1, w1 = card(left)
        c1.grid(row=0, column=0, sticky="ew")
        w1.columnconfigure(0, weight=1)
        st0 = self.load_state()
        head = ttk.Frame(w1, style="Card.TFrame"); head.grid(row=0, column=0, sticky="ew")
        ttk.Label(head, text="1  Websites", style="H.TLabel").pack(side="left")
        self.mode = tk.StringVar(value=st0.get("mode", "links"))
        seg = ttk.Frame(head, style="Card.TFrame"); seg.pack(side="right")
        ttk.Radiobutton(seg, text="Website links", value="links", variable=self.mode, style="Seg.Toolbutton",
                        command=self.switch_mode).pack(side="left")
        ttk.Radiobutton(seg, text="My screenshots", value="shots", variable=self.mode, style="Seg.Toolbutton",
                        command=self.switch_mode).pack(side="left", padx=(4, 0))
        self.hint = ttk.Label(w1, text="", style="Muted.TLabel", wraplength=350, justify="left")
        self.hint.grid(row=1, column=0, sticky="w", pady=(8, 6))

        self.links_box = ttk.Frame(w1, style="Card.TFrame")
        self.links_box.rowconfigure(0, weight=1); self.links_box.columnconfigure(0, weight=1)
        self.links = tk.Text(self.links_box, height=6, width=36, wrap="none", font=("Consolas", 10), relief="flat", bd=0,
                             highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT,
                             padx=10, pady=8, bg="#FBFBFE", fg=INK, insertbackground=INK)
        self.links.grid(row=0, column=0, sticky="nsew")
        self.links.insert("1.0", self.load_links())

        self.shots_box = ttk.Frame(w1, style="Card.TFrame")
        self.shots_box.rowconfigure(1, weight=1); self.shots_box.columnconfigure(0, weight=1)
        bt = ttk.Frame(self.shots_box, style="Card.TFrame"); bt.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(bt, text="Add folder...", style="Small.TButton", command=self.add_folder).pack(side="left")
        ttk.Button(bt, text="Add images...", style="Small.TButton", command=self.add_files).pack(side="left", padx=4)
        ttk.Button(bt, text="Remove", style="Small.TButton", command=self.remove_sel).pack(side="left")
        ttk.Button(bt, text="Clear", style="Small.TButton", command=lambda: self.paths.delete(0, "end")).pack(side="left", padx=4)
        self.paths = tk.Listbox(self.shots_box, height=6, width=36, relief="flat", bd=0, selectmode="extended",
                                font=(FONT, 9), highlightthickness=1, highlightbackground=BORDER,
                                highlightcolor=ACCENT, activestyle="none", bg="#FBFBFE", fg=INK)
        self.paths.grid(row=1, column=0, sticky="nsew")
        for pth in st0.get("paths", []):
            if Path(pth).exists():
                self.paths.insert("end", pth)
        self.switch_mode()

        chosen = [s.strip() for s in cfg.get("scenes", mm.DEFAULT_SCENES).split(",")]
        cP, wP = card(left, "Preview", "hover a style to see a sample")
        cP.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        self.build_preview(wP, chosen)
        left.rowconfigure(1, weight=0); left.rowconfigure(2, weight=1)
        c2, w2o = card(left, "Progress")
        c2.grid(row=2, column=0, sticky="nsew", pady=(14, 0))
        w2 = ttk.Frame(w2o, style="Card.TFrame"); w2.pack(fill="both", expand=True)
        w2.rowconfigure(1, weight=1); w2.columnconfigure(0, weight=1)
        self.bar = ttk.Progressbar(w2, mode="determinate")
        self.bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.log = tk.Text(w2, height=4, width=36, font=("Consolas", 9), relief="flat", bd=0, bg="#FBFBFE", fg=INK,
                           highlightthickness=1, highlightbackground=BORDER, state="disabled", padx=10, pady=8)
        self.log.grid(row=1, column=0, sticky="nsew")

        # ---- right column
        right = ttk.Frame(root); right.grid(row=1, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1, uniform="opt"); right.columnconfigure(1, weight=1, uniform="opt")

        # styles gallery
        self.scene_vars = {}
        c3, w3 = card(right, "2  Mockup styles")
        c3.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.sel_lbl = ttk.Label(w3.head, text="", style="Muted.TLabel")
        ttk.Button(w3.head, text="Edit panel text...", command=self.edit_text).pack(side="right")
        ttk.Button(w3.head, text="None", command=lambda: [v.set(False) for v in self.scene_vars.values()]).pack(side="right", padx=6)
        ttk.Button(w3.head, text="All", command=lambda: [v.set(True) for v in self.scene_vars.values()]).pack(side="right")
        self.sel_lbl.pack(side="right", padx=10)
        gal = tk.Frame(w3, bg=CARD); gal.pack(anchor="w")
        self.build_gallery(gal, chosen)

        # size & look
        c4, w4 = card(right, "3  Size & look")
        c4.grid(row=1, column=0, sticky="new", pady=(14, 0), padx=(0, 7))
        sz = ttk.Frame(w4, style="Card.TFrame"); sz.pack(fill="x")
        cur = cfg.get("size", "auto").split(",")[0].strip().lower()
        m = re.match(r"^(\d+)x(\d+)$", cur)
        self.size_mode = tk.StringVar(value="custom" if m else "own")
        self.w_var = tk.StringVar(value=m.group(1) if m else "2000")
        self.h_var = tk.StringVar(value=m.group(2) if m else "2000")
        ttk.Radiobutton(sz, text="Each style's own size", value="own", style="Card.TRadiobutton",
                        variable=self.size_mode).grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Radiobutton(sz, text="Custom size", value="custom", style="Card.TRadiobutton",
                        variable=self.size_mode).grid(row=1, column=0, sticky="w", pady=(6, 0))
        ent = ttk.Frame(sz, style="Card.TFrame"); ent.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(6, 0))
        we = ttk.Entry(ent, textvariable=self.w_var, width=6); we.pack(side="left")
        ttk.Label(ent, text=" x ", style="Card.TLabel").pack(side="left")
        he = ttk.Entry(ent, textvariable=self.h_var, width=6); he.pack(side="left")
        ttk.Label(ent, text=" px", style="Card.TLabel").pack(side="left")
        for e in (we, he):
            e.bind("<Key>", lambda ev: self.size_mode.set("custom"))
        cb = ttk.Combobox(sz, values=PRESETS, state="readonly", width=10)
        cb.set("or pick..."); cb.grid(row=1, column=2, padx=(10, 0), pady=(6, 0))

        def pick(_e=None):
            w, h = cb.get().split("x")
            self.w_var.set(w); self.h_var.set(h); self.size_mode.set("custom")
        cb.bind("<<ComboboxSelected>>", pick)
        zf = ttk.Frame(w4, style="Card.TFrame"); zf.pack(fill="x", pady=(12, 0))
        ttk.Label(zf, text="Device size", style="Card.TLabel").pack(side="left")
        self.zoom = tk.IntVar(value=int(float(cfg.get("zoom", 100))))
        ttk.Scale(zf, from_=60, to=150, variable=self.zoom, command=lambda v: self.zoom_lbl.config(
            text=f"{int(float(v))}%")).pack(side="left", fill="x", expand=True, padx=10)
        self.zoom_lbl = ttk.Label(zf, text=f"{self.zoom.get()}%", width=5, style="Card.TLabel")
        self.zoom_lbl.pack(side="left")
        bgf = ttk.Frame(w4, style="Card.TFrame"); bgf.pack(fill="x", pady=(12, 0))
        ttk.Label(bgf, text="Background", style="Card.TLabel").pack(side="left")
        cur_bg = cfg.get("bg", "auto")
        self.bg_var = tk.StringVar(value=dict(BGS).get(cur_bg, "My own color..."))
        self.bg_custom = tk.StringVar(value=cur_bg if cur_bg.startswith("#") else "#EEF2FF")
        ttk.Combobox(bgf, textvariable=self.bg_var, values=[b for _, b in BGS], state="readonly", width=24).pack(side="left", padx=8)
        ttk.Entry(bgf, textvariable=self.bg_custom, width=9).pack(side="left")
        lf = ttk.Frame(w4, style="Card.TFrame"); lf.pack(fill="x", pady=(12, 0))
        self.finish = tk.StringVar(value=cfg.get("finish", "black"))
        ttk.Label(lf, text="Devices", style="Card.TLabel").pack(side="left")
        ttk.Radiobutton(lf, text="Black", value="black", variable=self.finish, style="Card.TRadiobutton").pack(side="left", padx=(12, 6))
        ttk.Radiobutton(lf, text="Silver", value="silver", variable=self.finish, style="Card.TRadiobutton").pack(side="left")

        # pages & output
        c5, w5 = card(right, "4  Pages & save")
        c5.grid(row=1, column=1, sticky="new", pady=(14, 0), padx=(7, 0))
        sf = ttk.Frame(w5, style="Card.TFrame"); sf.pack(fill="x")
        self.src = tk.StringVar(value=cfg.get("page_source", "menu"))
        ttk.Radiobutton(sf, text="Only pages in the menu", value="menu", variable=self.src, style="Card.TRadiobutton").pack(side="left")
        ttk.Radiobutton(sf, text="All pages", value="all", variable=self.src, style="Card.TRadiobutton").pack(side="left", padx=(12, 0))
        pf = ttk.Frame(w5, style="Card.TFrame"); pf.pack(fill="x", pady=(8, 0))
        ttk.Label(pf, text="Max pages per website", style="Card.TLabel").pack(side="left")
        self.max_pages = tk.IntVar(value=int(cfg.get("max_pages", 60)))
        ttk.Spinbox(pf, from_=1, to=300, textvariable=self.max_pages, width=5).pack(side="left", padx=8)
        self.reuse = tk.BooleanVar(value=False)
        ttk.Checkbutton(w5, text="Reuse screenshots already taken (fast)", variable=self.reuse,
                        style="Card.TCheckbutton").pack(anchor="w", pady=(8, 0))
        self.shots_only = tk.BooleanVar(value=False)
        self.shots_mobile = tk.BooleanVar(value=False)
        self.shots_tablet = tk.BooleanVar(value=False)
        so = ttk.Frame(w5, style="Card.TFrame"); so.pack(fill="x", pady=(4, 0))
        ttk.Checkbutton(so, text="Only screenshots (no mockups)", variable=self.shots_only,
                        style="Card.TCheckbutton").pack(side="left")
        so2 = ttk.Frame(w5, style="Card.TFrame"); so2.pack(fill="x", padx=(24, 0))
        ttk.Checkbutton(so2, text="+ tablet", variable=self.shots_tablet, style="Card.TCheckbutton").pack(side="left")
        ttk.Checkbutton(so2, text="+ phone", variable=self.shots_mobile, style="Card.TCheckbutton").pack(side="left", padx=10)
        tf = ttk.Frame(w5, style="Card.TFrame"); tf.pack(fill="x", pady=(8, 0))
        ttk.Label(tf, text="Style 11 title", style="Card.TLabel").pack(side="left")
        self.t_small = tk.StringVar(value=cfg.get("title_small", "Fully editable"))
        self.t_big = tk.StringVar(value=cfg.get("title_big", "Website template"))
        ttk.Entry(tf, textvariable=self.t_small, width=13).pack(side="left", padx=(8, 4))
        ttk.Entry(tf, textvariable=self.t_big, width=15).pack(side="left")

        # ---- bottom bar
        bot = ttk.Frame(right); bot.grid(row=2, column=0, columnspan=2, sticky="sew", pady=(14, 0))
        right.rowconfigure(2, weight=1)
        bot.columnconfigure(0, weight=1)
        cs, ws = card(bot, pad=10)
        cs.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 12))
        of = ttk.Frame(ws, style="Card.TFrame"); of.pack(fill="x")
        ttk.Label(of, text="5  Save to", style="H.TLabel").pack(side="left", padx=(4, 10))
        self.out_var = tk.StringVar(value=cfg.get("out") or str(mm.desktop_dir() / "Mockups"))
        ttk.Button(of, text="Desktop", command=lambda: self.out_var.set(str(mm.desktop_dir() / "Mockups"))).pack(side="right")
        ttk.Button(of, text="Browse...", command=self.pick_out).pack(side="right", padx=(0, 6))
        ttk.Entry(of, textvariable=self.out_var).pack(side="left", fill="x", expand=True)
        self.go = ttk.Button(bot, text="Make Mockups", style="Go.TButton", command=self.start)
        self.go.grid(row=1, column=0, sticky="ew")
        self.stop_btn = ttk.Button(bot, text="Stop", command=self.stop, state="disabled")
        self.stop_btn.grid(row=1, column=1, padx=(10, 0), sticky="ns")
        ttk.Button(bot, text="Open finished mockups", command=self.open_out).grid(row=1, column=2, padx=(10, 0), sticky="ns")
        self.status = ttk.Label(bot, text="Ready.", style="Status.TLabel")
        self.status.grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))

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
        o = self.out_var.get().strip() if hasattr(self, "out_var") else self.cfg.get("out")
        return Path(o) if o else mm.desktop_dir() / "Mockups"

    def pick_out(self):
        d = filedialog.askdirectory(title="Choose the folder where mockups are saved",
                                    initialdir=str(self.out_dir().parent if self.out_dir().parent.exists() else Path.home()))
        if d:
            # a folder you pick is used as it is; each website gets its own sub-folder inside
            self.out_var.set(str(Path(d)))

    # ---- style preview panel -------------------------------------------------
    def build_gallery(self, parent, chosen):
        """Thumbnails you click to tick or untick a style."""
        self.tiles, self.thumbs, cols = {}, {}, 10
        for i, (key, label) in enumerate(SCENES):
            v = tk.BooleanVar(value=key in chosen)
            self.scene_vars[key] = v
            tile = tk.Frame(parent, bg=CARD, highlightthickness=2, highlightbackground=BORDER, cursor="hand2")
            tile.grid(row=i // cols, column=i % cols, padx=3, pady=3)
            img = self.thumb(key)
            if img is not None:
                pic = tk.Label(tile, image=img, bg=THUMB_BG, bd=0)
            else:
                pic = tk.Label(tile, text=styles.STYLES[key][0], bg=THUMB_BG, fg=MUTED, width=9, height=4)
            pic.pack(padx=3, pady=(3, 0))
            cap = tk.Label(tile, text=styles.STYLES[key][0].replace("Style ", "Style "), bg=CARD, fg=INK,
                           font=("Segoe UI", 8))
            cap.pack(pady=(1, 3))
            badge = tk.Label(tile, text="\u2713", bg=ACCENT, fg="white", font=("Segoe UI", 8, "bold"), width=2)
            self.tiles[key] = (tile, badge)
            for w in (tile, pic, cap, badge):
                w.bind("<Button-1>", lambda e, k=key: self.toggle_style(k))
                w.bind("<Enter>", lambda e, k=key: self.show_preview(k))
            v.trace_add("write", lambda *a, k=key: self.refresh_tile(k))
            self.refresh_tile(key)

    def thumb(self, key):
        if Image is None:
            return None
        try:
            im = Image.open(self.preview_file(key)).convert("RGB")
            im.thumbnail((THUMB, THUMB), Image.LANCZOS)
            sq = Image.new("RGB", (THUMB, THUMB), THUMB_BG)
            sq.paste(im, ((THUMB - im.width) // 2, (THUMB - im.height) // 2))
            ph = ImageTk.PhotoImage(sq)
            self.thumbs[key] = ph
            return ph
        except Exception:
            return None

    def toggle_style(self, key):
        self.scene_vars[key].set(not self.scene_vars[key].get())
        self.show_preview(key)

    def refresh_tile(self, key):
        tile, badge = self.tiles[key]
        on = self.scene_vars[key].get()
        tile.configure(highlightbackground=ACCENT if on else BORDER)
        if on:
            badge.place(relx=1.0, x=-4, y=4, anchor="ne")
        else:
            badge.place_forget()
        n = sum(1 for v in self.scene_vars.values() if v.get())
        if hasattr(self, "sel_lbl"):
            self.sel_lbl.configure(text=f"{n} of {len(self.scene_vars)} selected")

    def build_preview(self, parent, chosen):
        self.pv_cache, self.pv_key = {}, None
        box = ttk.Frame(parent, style="Card.TFrame"); box.pack(fill="x")
        if Image is None or not PREVIEWS.is_dir():
            return
        self.pv_canvas = tk.Canvas(box, width=PV, height=PV, bg=THUMB_BG, highlightthickness=1,
                                   highlightbackground=BORDER, cursor="hand2")
        self.pv_canvas.pack(pady=(0, 0))
        self.pv_canvas.bind("<Button-1>", lambda e: self.big_preview())
        self.pv_caption = ttk.Label(box, text="", style="Card.TLabel", font=("Segoe UI", 10, "bold"))
        self.pv_caption.pack(anchor="w", pady=(8, 0))
        self.pv_sub = ttk.Label(box, text="", style="Muted.TLabel")
        self.pv_sub.pack(anchor="w")
        first = next((k for k, _ in SCENES if k in chosen), SCENES[0][0])
        self.show_preview(first)

    def preview_file(self, key):
        return PREVIEWS / f"{styles.file_name(key)}.jpg"

    def show_preview(self, key):
        if Image is None or not hasattr(self, "pv_canvas") or key == self.pv_key:
            return
        try:
            if key not in self.pv_cache:
                im = Image.open(self.preview_file(key)).convert("RGB")
                im.thumbnail((PV, PV), Image.LANCZOS)
                self.pv_cache[key] = ImageTk.PhotoImage(im)
            self.pv_canvas.delete("all")
            self.pv_canvas.create_image(PV // 2, PV // 2, image=self.pv_cache[key])
            self.pv_key = key
            name, size, _ = styles.STYLES[key]
            self.pv_caption.configure(text=name)
            self.pv_sub.configure(text=f"Sample size {size[0]} x {size[1]} px")
        except Exception:
            pass

    def big_preview(self):
        if not self.pv_key:
            return
        try:
            im = Image.open(self.preview_file(self.pv_key)).convert("RGB")
            lim = max(300, self.winfo_screenheight() - 140)
            im.thumbnail((lim, lim), Image.LANCZOS)
            win = tk.Toplevel(self)
            win.title(f"{styles.STYLES[self.pv_key][0]} - sample preview")
            win.configure(bg=BG_UI)
            photo = ImageTk.PhotoImage(im)
            lab = tk.Label(win, image=photo, bd=0)
            lab.image = photo
            lab.pack(padx=10, pady=(10, 4))
            ttk.Label(win, text="Sample made with a demo website. Click the picture or press Esc to close.",
                      style="Muted.TLabel").pack(pady=(0, 10))
            for w in (win, lab):
                w.bind("<Button-1>", lambda e: win.destroy())
            win.bind("<Escape>", lambda e: win.destroy())
            win.focus_set()
        except Exception:
            pass

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
        out_text = self.out_var.get().strip()
        if out_text:
            try:
                Path(out_text).mkdir(parents=True, exist_ok=True)
            except OSError:
                messagebox.showerror("Site Mockup Maker by Raddito", f"Cannot use this save folder:\n{out_text}\n\nPick another folder with Browse.")
                return
        scenes = [k for k, v in self.scene_vars.items() if v.get()]
        if self.shots_only.get() and shots_mode:
            messagebox.showinfo("Site Mockup Maker by Raddito", "Screenshots only works with website links (box 1). Switch to 'Website links'.")
            return
        if not scenes and not self.shots_only.get():
            messagebox.showinfo("Site Mockup Maker by Raddito", "Tick at least one style in box 2.")
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
                     ("output_folder", "" if out_text == str(mm.desktop_dir() / "Mockups") else out_text),
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


def main():
    try:
        App().mainloop()
    except Exception:
        import traceback
        text = traceback.format_exc()
        try:
            (HERE / "error-log.txt").write_text(text, encoding="utf-8")
        except OSError:
            pass
        try:
            r = tk.Tk(); r.withdraw()
            messagebox.showerror("Site Mockup Maker by Raddito",
                                 "The program could not start.\n\nThe details were saved in error-log.txt in the program folder.\n"
                                 "Send that file to Raddito.\n\n" + text[-600:])
        except Exception:
            pass


if __name__ == "__main__":
    main()
