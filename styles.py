"""
The mockup styles, one per sample design.

Every style is drawn in the coordinates of its sample (for example 2000 x 2000) and scaled to
the output size, so a custom size keeps the same layout.  Each style gets:
  pages  : [(label, desktop_image, mobile_image_or_None)] in menu order, Home first
  brand  : the website's main color,   pagecol : its page background color
  T      : the editable panel text (see DEFAULT_TEXT / panel_text.json)
"""
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

import mockup_maker as mm

HERE = Path(__file__).resolve().parent
TEXT_FILE = HERE / "panel_text.json"

# ------------------------------------------------------------------ editable text
DEFAULT_TEXT = {
    "banner": "Featuring Responsive, Ready-Made Page Layouts Built With Elementor Free,",
    "banner_designed": "Designed For Small Businesses, Agencies And Local Service Websites.",
    "features": ["No Premium Required", "100% Responsive", "SEO Friendly", "Retina Ready", "Light Weight"],
    "features_tagline": "Why Start From Scratch When Your Website Is Already Built",
    "can_do_title": "What You Can Do",
    "can_do_items": ["Change Colors & Fonts", "Swap Images & Text In Minutes", "Add / Remove Any Section",
                     "Edit On Mobile, Tablet, Desktop", "Contact & Booking Forms", "Flexbox Containers",
                     "Revision History + Undo/Redo"],
    "benefits_title": "Benefits Of Our WordPress Website Templates For You",
    "benefits_items": ["No Need From Scratch", "Quick And Easy Setup", "Saves Time & Money",
                       "Mobile-Friendly & Responsive", "SEO-Ready, Fast Loading", "Easy Visual Editing (No Code)",
                       "Cost-Effective To Scale", "Cross-Browser Support", "Friendly Support"],
    "panel_footer": "Your Website Is Ready With In Few Click, Launch Fast With Our Pre-Made Template",
    "bottom_bar": "Experience The Live Template, Link In Description",
    "included_title": "What's Included",
    "included_items": ["Elementor WordPress Template Kit (.ZIP)", "Pre-Built Services Page", "Real Content Placeholders",
                       "Optimized Layout", "Global Design System", "Google Font Used", "Comprehensive Video Tutorials"],
    "cta_title": "Want A Website That's Truly Yours?",
    "cta_text": "We Create Custom WordPress Templates Made For Your Business.",
    "cta_button": "Contact us Today",
    "features_short": ["100% Responsive", "SEO Friendly", "Retina Ready", "Light Weight"],
    "features_side": ["No Code Required", "No Premium Plugin", "Fully Responsive", "Fast-Loading & SEO-Ready"],
}

TEXT_LABELS = {  # shown in the app's text editor
    "banner": "Top banner line (Style 3, Style 4)",
    "banner_designed": "Top banner line (Style 5)",
    "features": "Feature list (Style 6)",
    "features_tagline": "Tagline, top right (Style 6)",
    "can_do_title": "Title (Style 7)",
    "can_do_items": "List (Style 7)",
    "benefits_title": "Title (Style 8)",
    "benefits_items": "List (Style 8)",
    "panel_footer": "Small line at the bottom of the left panel (Style 7, Style 8)",
    "bottom_bar": "Bottom bar (Style 7, Style 8)",
    "included_title": "Title (Style 9)",
    "included_items": "List (Style 9)",
    "cta_title": "Box title (Style 9)",
    "cta_text": "Text under the box (Style 9)",
    "cta_button": "Button (Style 9)",
    "features_short": "Feature list (Style 13)",
    "features_side": "Feature list (Style 14)",
}


def load_text():
    t = dict(DEFAULT_TEXT)
    try:
        user = json.loads(TEXT_FILE.read_text(encoding="utf-8"))
        for k, v in user.items():
            if k in t and v not in (None, ""):
                t[k] = v
    except Exception:
        pass
    return t


def save_text(t):
    TEXT_FILE.write_text(json.dumps(t, indent=2, ensure_ascii=False), encoding="utf-8")


# ------------------------------------------------------------------ registry
# key: (name shown in app & used as file name, sample size, needs phone screenshots)
STYLES = {
    "two_pages_grid":      ("Style 1",               (2000, 2000), False),
    "browser_hero":        ("Style 2",                 (2000, 2000), False),
    "banner_page":         ("Style 3",                (2000, 2000), False),
    "banner_pages_phone":  ("Style 4",       (2000, 2000), True),
    "banner_three_pages":  ("Style 5",         (2000, 2000), False),
    "features_tilted":     ("Style 6",      (2000, 2000), False),
    "what_you_can_do":     ("Style 7",              (2000, 2000), False),
    "benefits":            ("Style 8",                     (2000, 2000), False),
    "whats_included":      ("Style 9",              (2000, 2000), False),
    "perspective_dark":    ("Style 10",             (2000, 2000), False),
    "presentation":        ("Style 11",                 (2000, 2000), False),
    "page_phone":          ("Style 12",                 (2000, 2355), True),
    "tilted_three_pages":  ("Style 13",           (1466, 1670), False),
    "laptop_phone_features": ("Style 14",  (2000, 1693), True),
    "hero_card":           ("Style 15",                    (1600, 1200), False),
    "hero_layered":        ("Style 16",                 (1600, 1200), False),
    "browser_phone":       ("Style 17",                 (2000, 2000), True),
    "three_phones":        ("Style 18",                 (2000, 2000), True),
    "page_cascade":        ("Style 19",                 (2000, 2000), False),
    "device_trio":         ("Style 20",                 (2000, 2000), True),
}


def file_name(key):
    n = list(STYLES).index(key) + 1
    return f"Style_{n:02d}"


# ------------------------------------------------------------------ drawing context
WHITE = (255, 255, 255)
LIGHT_INK = (238, 234, 228)


class Ctx:
    def __init__(self, c, design, pages, brand, pagecol, stops, T, opt, site, host):
        self.c, self.pages, self.brand, self.pagecol, self.stops = c, pages, brand, pagecol, stops
        self.T, self.opt, self.site, self.host = T, opt, site, host
        dw, dh = design
        self.sx, self.sy = c.W / dw, c.H / dh
        self.s = min(self.sx, self.sy)
        self.home = pages[0][1]
        self.home_mob = pages[0][2]
        c.k = c.W / 1600

    # coordinates
    def X(self, v): return v * self.sx
    def Y(self, v): return v * self.sy
    def S(self, v): return v * self.s

    # pages
    def page_img(self, i):
        """i-th page after Home (wraps); Home if the site has only one page."""
        others = self.pages[1:]
        return others[i % len(others)][1] if others else self.home

    def page_mob(self, i):
        others = self.pages[1:]
        if others:
            m = others[i % len(others)][2]
            if m is not None:
                return m
        return self.home_mob or self.page_img(i)

    def sect(self, img, n):
        """Source y of the n-th section after the hero (n=1 -> right after the hero)."""
        if n <= 0:
            return 0
        after = mm.hero_end(img)
        cands = [e for e in mm.section_edges(img) if e >= after - 4 and e < img.height - img.width * 0.3]
        if not cands:
            return min(after, max(0, img.height - img.width))
        return cands[min(n - 1, len(cands) - 1)]

    def start(self, img, i_wanted):
        """Where to start a non-home page: its top, or a later section if it is Home again."""
        return self.sect(img, i_wanted) if img is self.home else 0

    # backgrounds
    def dark_bg(self):
        c, b = self.c, self.brand
        if self.opt.bg.startswith("#") or self.opt.bg == "white":
            return
        top, bot = mm.mix(b, (6, 5, 5), 0.86), mm.mix(b, (6, 5, 5), 0.70)
        c.im.paste(mm.gradient((c.W, c.H), top, bot), (0, 0))
        c.d = ImageDraw.Draw(c.im)

    def soft_grid(self, step, strength=0.07, base=None):
        mid = base or mm.mix(*self.stops, .5)
        col = mm.mix(mid, (0, 0, 0) if mm.lum(mid) > .4 else (255, 255, 255), strength)
        self.c.grid(self.S(step), col)

    def band_color(self):
        return mm.mix(self.brand, (24, 14, 10), 0.68)

    def panel_color(self):
        return mm.mix(self.brand, (10, 6, 5), 0.93)

    # text
    def font(self, px, weight=560, width=100):
        f = mm.get_font("ui", self.S(px))
        try:
            f.set_variation_by_axes([weight, width])
        except Exception:
            pass
        return f

    def spaced(self, x, y, text, font, fill, spacing, anchor_v="m"):
        d = self.c.d
        for ch in text:
            d.text((x, y), ch, font=font, fill=fill, anchor="l" + anchor_v)
            x += d.textlength(ch, font=font) + spacing
        return x

    def wrap(self, text, font, maxw):
        words, lines, line = text.split(), [], ""
        for w in words:
            t = (line + " " + w).strip()
            if self.c.d.textlength(t, font=font) > maxw and line:
                lines.append(line); line = w
            else:
                line = t
        if line:
            lines.append(line)
        return lines

    def lines(self, x, y, text, font, fill, maxw, lh, align="l"):
        for ln in self.wrap(text, font, maxw):
            ax = {"l": x, "m": x, "r": x}[align]
            self.c.d.text((ax, y), ln, font=font, fill=fill, anchor=align + "t")
            y += lh
        return y

    def italic(self, cx, y, text, font, fill, maxw, lh):
        """Slanted, centered lines (there is no italic font file, so the text is sheared)."""
        for ln in self.wrap(text, font, maxw):
            w = int(self.c.d.textlength(ln, font=font)) + 20
            h = int(lh * 1.4)
            layer = Image.new("RGBA", (w + h // 3, h), (0, 0, 0, 0))
            ImageDraw.Draw(layer).text((h // 6, h // 2), ln, font=font, fill=fill + (255,), anchor="lm")
            k = 0.2
            layer = layer.transform(layer.size, Image.AFFINE, (1, k, -k * h / 2, 0, 1, 0), Image.BICUBIC)
            self.c.overlay(layer, round(cx - layer.width / 2), round(y))
            y += lh
        return y

    def ring(self, x, y, r, color, width):
        self.c.d.ellipse([x - r, y - r, x + r, y + r], outline=color, width=max(1, round(width)))

    def arrow(self, x, y, length, color, width):
        d = self.c.d
        w = max(1, round(width))
        d.line([(x, y), (x + length, y)], fill=color, width=w)
        d.line([(x + length - length * .3, y - length * .28), (x + length, y)], fill=color, width=w)
        d.line([(x + length - length * .3, y + length * .28), (x + length, y)], fill=color, width=w)

    # pieces
    def page(self, src, x, y, w, top=0, h=None, r=8, shadow=40):
        h = (self.c.H - y + 50) if h is None else h
        need = h * src.width / max(1, w)          # source pixels needed to fill the space
        top = max(0, min(top, src.height - need))  # short page: start higher so it reaches the edge
        self.c.strip(src, x, y, w, top, h, self.S(r), shadow)

    def banner(self, text, h, size=46, align="l", x=100):
        c = self.c
        c.d.rectangle([0, 0, c.W, round(self.Y(h))], fill=self.band_color())
        f = self.font(size, 520)
        if align == "m":
            c.d.text((c.W / 2, self.Y(h) / 2), text, font=f, fill=WHITE, anchor="mm")
        else:
            c.d.text((self.X(x), self.Y(h) / 2), text, font=f, fill=WHITE, anchor="lm")

    def badge(self, kind, x, y, h, anchor="lt"):
        """Places your own logo from the badges folder (file name containing e.g. 'elementor')."""
        files = sorted(p for p in mm.BADGE_DIR.glob("*.png") if kind in p.stem.lower()) if mm.BADGE_DIR.exists() else []
        if not files:
            return
        try:
            b = Image.open(files[0]).convert("RGBA")
        except Exception:
            return
        hh = round(self.S(h)); ww = round(b.width * hh / b.height)
        b = b.resize((ww, hh), Image.LANCZOS)
        px = self.X(x) - (ww if anchor[0] == "r" else ww / 2 if anchor[0] == "m" else 0)
        py = self.Y(y) - (hh if anchor[1] == "b" else 0)
        self.c.overlay(b, round(px), round(py))

    def phone(self, x, y, w, src):
        self.c.phone(self.X(x), self.Y(y), self.S(w), src, 0.0)

    def bullets(self, items, x, y, step, size, color, ring_color, spacing=4, weight=560, upper=False, filled=False):
        f = self.font(size, weight)
        room = self.c.W - self.X(x) - self.S(size * 0.9) - self.S(30)
        def width(fnt, sp):
            return max(sum(self.c.d.textlength(ch, font=fnt) + sp for ch in (t.upper() if upper else t)) for t in items)
        while size > 14 and width(f, self.S(spacing)) > room:
            size *= 0.94; spacing *= 0.94
            f = self.font(size, weight)
        for i, t in enumerate(items):
            cy = self.Y(y) + i * self.S(step)
            r = self.S(size * 0.32)
            if filled:
                self.c.d.ellipse([self.X(x) - r, cy - r, self.X(x) + r, cy + r], fill=ring_color, outline=WHITE,
                                 width=max(1, round(self.S(3))))
            else:
                self.ring(self.X(x), cy, r, ring_color, self.S(5))
            self.spaced(self.X(x) + r + self.S(size * 0.55), cy, t.upper() if upper else t, f, color, self.S(spacing))


def accent(brand):
    """A lighter, punchier version of the brand color for small marks on dark backgrounds."""
    return mm.mix(brand, WHITE, 0.25) if mm.lum(brand) < .35 else brand


# ------------------------------------------------------------------ the styles
def two_pages_grid(x):
    x.soft_grid(70)
    x.page(x.home, x.X(70), x.Y(90), x.X(1072), r=8, shadow=35)
    right = x.page_img(0)
    x.page(right, x.X(1243), x.Y(12), x.X(622), top=x.sect(right, 1), r=8, shadow=35)


def browser_hero(x):
    c = x.c
    bw = x.X(1620)
    c.k = bw / 1000
    c.url_text = x.host
    c.browser(x.X(160), x.Y(155), bw, c.H, x.home, 0.0)


def banner_page(x):
    c = x.c
    base = mm.mix(mm.mix(*x.stops, .5), (150, 144, 138), 0.55)
    c.im.paste(mm.gradient((c.W, c.H), mm.mix(base, WHITE, .08), base), (0, 0)); c.d = ImageDraw.Draw(c.im)
    x.soft_grid(110, 0.05, base)
    x.banner(x.T["banner"], 96, 46, x=100)
    x.page(x.home, x.X(162), x.Y(162), x.X(1580), r=26, shadow=60)


def banner_pages_phone(x):
    x.dark_bg()
    x.banner(x.T["banner"], 70, 44, x=100)
    x.badge("wordpress", 1000, 120, 62, "mt")
    x.page(x.home, x.X(75), x.Y(182), x.X(788), r=6, shadow=50)
    right = x.page_img(0)
    x.page(right, x.X(1088), x.Y(176), x.X(778), top=x.start(right, 1), r=14, shadow=50)
    x.phone(735, 518, 430, x.page_mob(1))


def banner_three_pages(x):
    x.dark_bg()
    x.banner(x.T["banner_designed"], 88, 42, x=22)
    left, right = x.page_img(0), x.page_img(1)
    x.page(left, x.X(45), x.Y(262), x.X(900), top=x.sect(left, 1), r=6, shadow=45)
    x.page(right, x.X(1000), x.Y(262), x.X(888), top=x.sect(right, 1), r=6, shadow=45)
    x.badge("elementor", 1865, 150, 80, "rt")
    x.page(x.home, x.X(455), x.Y(155), x.X(967), r=10, shadow=80)


def features_tilted(x):
    x.dark_bg()
    back, front = x.page_img(0), x.home
    x.c.rot_strip(back, x.X(1560), x.Y(420), x.X(700), x.c.H * 1.15, -13, x.start(back, 1))
    x.c.rot_strip(front, x.X(920), x.Y(150), x.X(760), x.c.H * 1.1, -13, x.sect(front, 1))
    x.bullets(x.T["features"], 80, 90, 89, 44, LIGHT_INK, LIGHT_INK, spacing=4, weight=600)
    f = x.font(36, 400)
    x.lines(x.X(1890), x.Y(70), x.T["features_tagline"], f, LIGHT_INK, x.X(560), x.S(54), "r")
    x.badge("elementor", 1840, 1725, 64, "rt")
    x.badge("wordpress", 1895, 1805, 70, "rt")


def _text_panel(x, title, items, page_src, page_top):
    c = x.c
    bar_top = x.Y(1830)
    x.page(page_src, x.X(962), 0, c.W - x.X(962) + x.S(40), top=page_top, h=bar_top, r=0, shadow=0)
    c.d.rectangle([0, 0, round(x.X(960)), c.H], fill=x.panel_color())
    ft = x.font(88, 700)
    y = x.lines(x.X(105), x.Y(270), title, ft, LIGHT_INK, x.X(800), x.S(96))
    fi = x.font(50, 500)
    y += x.S(70)
    step = min(x.S(118), (x.Y(1520) - y) / max(1, len(items)))
    for t in items:
        x.arrow(x.X(105), y + step * 0.42, x.S(50), LIGHT_INK, x.S(4))
        c.d.text((x.X(178), y + step * 0.42), t, font=fi, fill=LIGHT_INK, anchor="lm")
        y += step
    x.italic(x.X(480), x.Y(1585), x.T["panel_footer"], x.font(40, 420), LIGHT_INK, x.X(780), x.S(58))
    c.d.rectangle([0, round(bar_top), c.W, c.H], fill=x.band_color())
    c.d.text((c.W / 2, (bar_top + c.H) / 2), x.T["bottom_bar"].upper(), font=x.font(52, 700), fill=WHITE, anchor="mm")


def what_you_can_do(x):
    src = x.page_img(0)
    _text_panel(x, x.T["can_do_title"], x.T["can_do_items"], src, x.sect(src, 1))


def benefits(x):
    src = x.page_img(1)
    _text_panel(x, x.T["benefits_title"], x.T["benefits_items"], src, x.sect(src, 2))


def whats_included(x):
    c = x.c
    src = x.page_img(2)
    x.page(src, x.X(945), 0, c.W - x.X(945) + x.S(30), top=x.sect(src, 1), h=c.H, r=26, shadow=0)
    c.d.rectangle([0, 0, round(x.X(944)), c.H], fill=x.panel_color())
    c.d.text((x.X(130), x.Y(220)), x.T["included_title"].upper(), font=x.font(64, 760), fill=LIGHT_INK, anchor="lm")
    fi = x.font(48, 500)
    y = x.Y(310)
    for t in x.T["included_items"]:
        ln = x.wrap(t, fi, x.X(690))
        x.ring(x.X(146), y + x.S(30), x.S(14), LIGHT_INK, x.S(5))
        for j, part in enumerate(ln):
            c.d.text((x.X(175), y + x.S(30) + j * x.S(60)), part, font=fi, fill=LIGHT_INK, anchor="lm")
        y += x.S(60) * len(ln) + x.S(40)
    box_top = max(y + x.S(50), x.Y(1160))
    fb = x.font(64, 780)
    tl = x.wrap(x.T["cta_title"].upper(), fb, x.X(720))
    box_h = x.S(40) * 2 + len(tl) * x.S(76)
    c.rrect((x.X(88), box_top, x.X(858), box_top + box_h), x.S(16), x.band_color())
    ty = box_top + x.S(40) + x.S(38)
    for ln in tl:
        c.d.text((x.X(473), ty), ln, font=fb, fill=WHITE, anchor="mm"); ty += x.S(76)
    y = x.lines(x.X(473), box_top + box_h + x.S(50), x.T["cta_text"], x.font(48, 700), LIGHT_INK, x.X(780), x.S(66), "m")
    by = min(y + x.S(40), c.H - x.S(130))
    fbt = x.font(52, 480)
    bw = c.d.textlength(x.T["cta_button"], font=fbt) + x.S(70)
    c.rrect((x.X(473) - bw / 2, by, x.X(473) + bw / 2, by + x.S(90)), x.S(45), WHITE)
    c.d.text((x.X(473), by + x.S(45)), x.T["cta_button"], font=fbt, fill=(30, 20, 15), anchor="mm")


def perspective_dark(x):
    x.dark_bg()
    back = x.page_img(0)
    quad = [(x.X(1180), x.Y(130)), (x.X(1915), x.Y(262)), (x.X(1880), x.Y(2080)), (x.X(1150), x.Y(2010))]
    x.c.perspective_page(back, quad, x.start(back, 1))
    x.page(x.home, x.X(232), x.Y(48), x.X(1024), r=4, shadow=70)


def page_phone(x):
    x.dark_bg()
    x.page(x.home, x.X(227), x.Y(45), x.X(1110), r=4, shadow=60)
    mob = x.home_mob or x.home
    pw = x.S(430)
    x.c.phone(x.X(1385), x.Y(158), pw, mob, 0.0)
    sw = pw * 0.89
    shown = (pw * 2.05 - pw * 0.11 - pw * 0.16) * mob.width / sw
    x.page(mob, x.X(1385) + pw * 0.055, x.Y(158) + pw * 2.05 + x.S(24), sw, top=min(shown, mob.height - 10), r=6, shadow=40)
    x.badge("elementor", 1760, 50, 90, "rt")


def tilted_three_pages(x):
    x.dark_bg()
    a, b = x.page_img(1), x.page_img(0)
    x.c.rot_strip(a, x.X(1270), x.Y(620), x.X(560), x.c.H * 1.2, -17, x.start(a, 2))
    x.c.rot_strip(b, x.X(880), x.Y(330), x.X(600), x.c.H * 1.2, -17, x.start(b, 1))
    x.c.rot_strip(x.home, x.X(400), x.Y(40), x.X(640), x.c.H * 1.2, -17, 0)
    x.bullets(x.T["features_short"], 1078, 70, 60, 34, LIGHT_INK, accent(x.brand), spacing=4, weight=500,
              upper=True, filled=True)
    x.badge("elementor", 1450, 1655, 55, "rb")


def laptop_phone_features(x):
    x.dark_bg()
    sw = x.X(1188)
    m = 0.028
    lw = sw / (1 - 2 * m)
    lap_bottom = x.Y(78) - lw * m + lw * 0.65 + (lw / 0.84) * 0.035
    x.page(x.home, x.X(255), lap_bottom - x.S(20), x.X(1188), top=mm.hero_end(x.home), r=0, shadow=40)
    x.c.laptop_hero(x.X(245), x.Y(78), sw, x.home)
    x.phone(1395, 450, 420, x.home_mob or x.home)
    x.bullets(x.T["features_side"], 1562, 142, 68, 36, LIGHT_INK, accent(x.brand), spacing=2, weight=500,
              filled=True)
    x.badge("wordpress", 1540, 1335, 58, "lt")
    x.badge("elementor", 1540, 1408, 58, "lt")


def hero_card(x):
    x.page(x.home, x.X(98), x.Y(72), x.X(1404), r=14, shadow=45)


def hero_layered(x):
    c = x.c
    x.dark_bg()
    tr, bl = x.page_img(1), x.page_img(0)
    x.page(tr, x.X(955), 0, x.X(700), top=x.sect(tr, 2), h=x.Y(362), r=0, shadow=45)
    x.page(bl, x.X(-10), x.Y(918), x.X(682), top=x.sect(bl, 1), r=0, shadow=45)
    pad = x.S(12)
    box = (x.X(248), x.Y(231), x.X(1352), x.Y(984))
    c.drop_shadow(box, 2, 70)
    c.d.rectangle([round(v) for v in box], fill=WHITE)
    x.page(x.home, box[0] + pad, box[1] + pad, box[2] - box[0] - 2 * pad, h=box[3] - box[1] - 2 * pad, r=0, shadow=0)


# ------------------------------------------------------------------ new styles (17+)
def _ink_on(stops):
    """Dark text on a light backdrop, light text on a dark one."""
    return (24, 28, 38) if mm.lum(mm.mix(*stops, .5)) > .45 else (245, 247, 250)


def _headline(x, text, y, size=84, color=None, align="l", left=140):
    f = x.font(size, 700)
    col = color or _ink_on(x.stops)
    if align == "m":
        x.c.d.text((x.c.W / 2, x.Y(y)), text, font=f, fill=col, anchor="mm")
    else:
        x.c.d.text((x.X(left), x.Y(y)), text, font=f, fill=col, anchor="lm")


def browser_phone(x):
    c = x.c
    x.soft_grid(80, 0.04)
    _headline(x, x.site, 135)
    bw = x.X(1500)
    c.k = bw / 1000
    c.url_text = x.host
    c._bg = c.im.copy()
    c.browser(x.X(110), x.Y(270), bw, x.Y(1560), x.home, 0.0)
    x.phone(1470, 760, 420, x.page_mob(0))


def three_phones(x):
    x.dark_bg()
    _headline(x, x.site, 180, 96, WHITE, "m")
    x.c.d.text((x.c.W / 2, x.Y(275)), x.host, font=x.font(42, 450), fill=(190, 196, 206), anchor="mm")
    x.phone(100, 650, 590, x.page_mob(1))
    x.phone(1310, 650, 590, x.page_mob(2))
    x.phone(690, 430, 620, x.home_mob or x.home)


def page_cascade(x):
    c = x.c
    x.soft_grid(90, 0.04)
    _headline(x, x.site, 105, 70)
    pages = [x.home, x.page_img(0), x.page_img(1)]
    spots = [(120, 190, 1100), (480, 540, 1100), (840, 890, 1040)]
    for i, (img, (px, py, pw)) in enumerate(zip(pages, spots)):
        x.page(img, x.X(px), x.Y(py), x.X(pw), top=x.start(img, i) if img is x.home and i else 0,
               h=x.Y(1000), r=14, shadow=55)


def device_trio(x):
    c = x.c
    x.soft_grid(80, 0.04)
    c._bg = c.im.copy()
    c.monitor(x.X(300), x.Y(170), x.S(1400), x.home, 0.0)
    c.tablet(x.X(120), x.Y(1060), x.S(520), x.page_img(0), 0.0)
    x.phone(1530, 1110, 300, x.page_mob(1))
    _headline(x, x.site, 1860, 56, None, "m")


DRAW = {
    "two_pages_grid": two_pages_grid, "browser_hero": browser_hero, "banner_page": banner_page,
    "banner_pages_phone": banner_pages_phone, "banner_three_pages": banner_three_pages,
    "features_tilted": features_tilted, "what_you_can_do": what_you_can_do, "benefits": benefits,
    "whats_included": whats_included, "perspective_dark": perspective_dark, "page_phone": page_phone,
    "tilted_three_pages": tilted_three_pages, "laptop_phone_features": laptop_phone_features,
    "hero_layered": hero_layered, "hero_card": hero_card,
    "browser_phone": browser_phone, "three_phones": three_phones, "page_cascade": page_cascade,
    "device_trio": device_trio,
    # "presentation" is drawn by mockup_maker.compose_site
}


def render(key, pages, opt, size, out_path, colors, site_name, host):
    """pages: [(label, desktop_img, mobile_img_or_None)]"""
    if key == "presentation":
        mm.compose_site(key, [p[1] for p in pages], opt, size, out_path, colors, site_name, [p[0] for p in pages])
        return
    home = pages[0][1]
    brand, pagecol = mm.site_palette(colors, home)
    stops = mm.backdrop(opt.bg, brand, pagecol)
    W, H = size
    ss = 2 if W * H <= 4_200_000 else 1
    c = mm.Canvas(W, H, ss, stops, opt.finish, opt.shadow / 100, False, host)
    c._bg = c.im.copy()
    x = Ctx(c, STYLES[key][1], pages, brand, pagecol, stops, load_text(), opt, site_name, host)
    DRAW[key](x)
    c.save(out_path, opt.format, opt.quality)
