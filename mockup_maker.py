#!/usr/bin/env python3
"""
Site Mockup Maker by Raddito
-----------------
Give it website links (urls.txt). For every website it:
  1. finds the site's pages (menu links first),
  2. takes full-page screenshots at desktop, tablet and mobile width,
  3. places them into device mockups (laptop, phone, monitor, browser...),
  4. saves everything to  Desktop/Mockups/<website name>/

Usage
  python mockup_maker.py                    (reads urls.txt next to this file)
  python mockup_maker.py my-links.txt --max-pages 5 --scenes laptop_phone,fullpage

Run  python mockup_maker.py --help  for every option.
"""
import argparse
import asyncio
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat
except ImportError:
    sys.exit("Pillow is missing. Run:  pip install pillow playwright")
try:
    from playwright.async_api import async_playwright, TimeoutError as PWTimeout
except ImportError:
    sys.exit("Playwright is missing. Run:  pip install playwright  then  python -m playwright install chromium")

Image.MAX_IMAGE_PIXELS = None

# ------------------------------------------------------------------ settings
DEFAULT_SCENES = ",".join(["two_pages_grid", "browser_hero", "banner_page", "banner_pages_phone", "banner_three_pages",
                           "features_tilted", "what_you_can_do", "benefits", "whats_included", "perspective_dark",
                           "presentation", "page_phone", "tilted_three_pages", "laptop_phone_features",
                           "hero_card", "hero_layered", "browser_phone", "three_phones", "page_cascade",
                           "device_trio", "elementsdoc"])


def scene_labels():
    """{style key: file name}.  The 16 styles live in styles.py."""
    import styles
    return {k: styles.file_name(k) for k in styles.STYLES}


def style_size(key):
    import styles
    return styles.STYLES[key][1]


def style_needs_phone(key):
    import styles
    return styles.STYLES[key][2]


VIEWPORTS = {
    "desk": dict(width=1440, height=900, scale=1, mobile=False, max_h=15000),
    "tab": dict(width=820, height=1180, scale=1, mobile=True, max_h=12000),
    "mob": dict(width=390, height=844, scale=2, mobile=True, max_h=7800),
}
MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1")
TABLET_UA = ("Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1")

# CSS injected before the screenshot: stop animations, show Elementor/AOS
# entrance-animated elements, hide cookie bars, preloaders and popups.
CLEAN_CSS = """
*,*::before,*::after{animation-delay:0s!important;animation-duration:0s!important;
  transition-duration:0s!important;transition-delay:0s!important;scroll-behavior:auto!important;caret-color:transparent!important}
.elementor-invisible{visibility:visible!important;opacity:1!important}
[data-aos],.wow,.reveal,.animate__animated{opacity:1!important;visibility:visible!important;transform:none!important}
#onetrust-banner-sdk,#onetrust-consent-sdk,.cky-consent-container,.cky-overlay,#cmplz-cookiebanner-container,
.cmplz-cookiebanner,#cookie-notice,#cookie-law-info-bar,.cli-modal-backdrop,.cookie-notice-container,
#moove_gdpr_cookie_info_bar,.cc-window,.cc-banner,#BorlabsCookieBox,.borlabs-cookie,#catapult-cookie-bar,
#gdpr-cookie-consent-bar,.gdpr-cookie-notice,#CybotCookiebotDialog,.iubenda-cs-container,#usercentrics-root,
.elementor-popup-modal,.dialog-lightbox-widget-content,#preloader,.preloader,#page-preloader,.page-loader,
.loader-wrapper,#loader-wrapper,.site-preloader,#pre-loader,.tawk-min-container,#tidio-chat,.crisp-client
{display:none!important}
html,body{overflow:visible!important}
"""

SCROLL_JS = """async () => {
  document.querySelectorAll('img[loading="lazy"]').forEach(i => i.loading = 'eager');
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const H = () => Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
  let y = 0;
  while (y < H() && y < 30000) { window.scrollTo(0, y); await sleep(140); y += Math.round(innerHeight * 0.75); }
  window.scrollTo(0, H()); await sleep(400);
  window.scrollTo(0, 0); await sleep(500);
  return H();
}"""

IMAGES_JS = """async () => {
  const imgs = [...document.images];
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  // force lazy images and retry broken ones once
  imgs.forEach(i => {
    if (i.dataset && (i.dataset.src || i.dataset.lazySrc)) i.src = i.dataset.src || i.dataset.lazySrc;
    if (i.complete && i.naturalWidth === 0 && i.src) { const s = i.src; i.src = ''; i.src = s; }
  });
  const t0 = Date.now();
  while (Date.now() - t0 < 10000) {
    if (imgs.every(i => i.complete)) break;
    await sleep(200);
  }
  await Promise.all(imgs.filter(i => i.decode).map(i => i.decode().catch(() => {})));
  return imgs.filter(i => !i.complete || i.naturalWidth === 0).length;
}"""

LINKS_JS = """() => {
  const out = [];
  const txt = a => {
    let t = (a.innerText || a.textContent || '').trim().split('\\n')[0].trim();
    if (!t) t = (a.getAttribute('aria-label') || a.getAttribute('title') || '').trim();
    return t;
  };
  const MENU = 'header a, nav a, .elementor-nav-menu a, .menu a, [role="navigation"] a, .e-n-menu a';
  const FOOT = 'footer, .site-footer, .elementor-location-footer';
  document.querySelectorAll(MENU).forEach(a => { if (a.href) out.push({href: a.href, text: txt(a), menu: !a.closest(FOOT)}); });
  document.querySelectorAll('a').forEach(a => { if (a.href) out.push({href: a.href, text: txt(a), menu: false}); });
  return out;
}"""

# Reads the website's own colors: Elementor global colors, buttons, links, page background.
COLORS_JS = """() => {
  const parse = c => { if (!c) return null; c = c.trim();
    let m = c.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
    if (m) { let h = m[1]; if (h.length === 3) h = h.split('').map(x => x + x).join('');
      return [parseInt(h.slice(0,2),16), parseInt(h.slice(2,4),16), parseInt(h.slice(4,6),16), 1]; }
    m = c.match(/rgba?\\(([^)]+)\\)/i); if (!m) return null;
    const p = m[1].split(/[ ,\\/]+/).filter(Boolean).map(parseFloat);
    return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const css = getComputedStyle(document.documentElement);
  const v = n => parse(css.getPropertyValue(n));
  const vivid = c => c && c[3] > 0.5 && (Math.max(c[0],c[1],c[2]) - Math.min(c[0],c[1],c[2])) > 28;
  const out = { primary: v('--e-global-color-primary'), accent: v('--e-global-color-accent'),
                secondary: v('--e-global-color-secondary'), page: null, buttons: [] };
  const bgOf = el => { while (el) { const c = parse(getComputedStyle(el).backgroundColor); if (c && c[3] > 0.6) return c; el = el.parentElement; } return null; };
  out.page = bgOf(document.querySelector('main, #content, .site-content, .elementor')) || bgOf(document.body) || [255,255,255,1];
  const tally = {};
  document.querySelectorAll('a.elementor-button, .elementor-button, button, .btn, .button, input[type=submit], a[class*="btn"]').forEach(el => {
    const r = el.getBoundingClientRect(); if (r.width < 40 || r.height < 20) return;
    const c = parse(getComputedStyle(el).backgroundColor);
    if (vivid(c)) { const k = c.slice(0,3).map(Math.round).join(','); tally[k] = (tally[k] || 0) + r.width * r.height; } });
  document.querySelectorAll('a').forEach(el => { const c = parse(getComputedStyle(el).color);
    if (vivid(c)) { const k = c.slice(0,3).map(Math.round).join(','); tally[k] = (tally[k] || 0) + 40; } });
  out.buttons = Object.entries(tally).sort((a, b) => b[1] - a[1]).slice(0, 3).map(e => e[0].split(',').map(Number));
  return out;
}"""

SKIP_EXT = re.compile(r"\.(pdf|jpe?g|png|gif|webp|svg|zip|rar|mp4|mp3|docx?|xlsx?|pptx?|xml|txt|css|js)$", re.I)
SKIP_PATH = re.compile(r"/(wp-admin|wp-login|wp-json|feed|cart|checkout|my-account|login|register|tag|author|"
                       r"category/.+/page|page/\d+|comments|xmlrpc)(/|$)", re.I)


# ------------------------------------------------------------------ helpers
def desktop_dir() -> Path:
    """The user's real Desktop folder (handles Windows OneDrive desktops)."""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
            buf = ctypes.c_wchar_p()
            fid = ctypes.c_char_p(bytes.fromhex("3ACCBFB42CDB4C42B0297FE99A87C641"))  # FOLDERID_Desktop
            if ctypes.windll.shell32.SHGetKnownFolderPath(fid, 0, None, ctypes.byref(buf)) == 0:
                p = Path(buf.value)
                ctypes.windll.ole32.CoTaskMemFree(buf)
                if p.exists():
                    return p
        except Exception:
            pass
        for cand in (Path.home() / "OneDrive" / "Desktop", Path.home() / "Desktop"):
            if cand.exists():
                return cand
    else:
        try:
            import subprocess
            out = subprocess.run(["xdg-user-dir", "DESKTOP"], capture_output=True, text=True, timeout=3).stdout.strip()
            if out and Path(out).exists():
                return Path(out)
        except Exception:
            pass
    d = Path.home() / "Desktop"
    return d if d.exists() else Path.home()


def safe_name(s: str) -> str:
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", s).strip(" .")
    return re.sub(r"\s+", " ", s)[:80] or "website"


def norm_url(u: str) -> str:
    p = urlparse(u.strip())
    if not p.scheme:
        p = urlparse("https://" + u.strip())
    path = p.path or "/"
    path = re.sub(r"/index\.(html?|php)$", "/", path, flags=re.I)   # /index.html is the same page as /
    if not path.endswith("/") and not re.search(r"\.[a-z0-9]{2,5}$", path, re.I):
        path += "/"
    return urlunparse((p.scheme, p.netloc.lower(), path, "", "", ""))


def host(u: str) -> str:
    return urlparse(u).netloc.lower().removeprefix("www.")


def site_name_from(url: str) -> str:
    p = urlparse(url)
    segs = [s for s in p.path.split("/") if s]
    if segs:  # demos often live at demo.example.com/kit-name/
        return safe_name(segs[-1].replace("-", " ").replace("_", " ").title())
    return safe_name(host(url))


def page_name(url: str, root: str) -> str:
    rel = urlparse(url).path[len(urlparse(root).path):].strip("/")
    if not rel:
        return "home"
    rel = re.sub(r"\.(html?|php)$", "", rel, flags=re.I)
    return re.sub(r"[^a-z0-9]+", "-", rel.lower()).strip("-")[:60] or "page"


def clean_label(text):
    """'About us ›' -> 'About_Us'.  Returns '' if the text is not usable as a name."""
    t = re.sub(r"[^\w\s&'-]", " ", text or "", flags=re.U)
    t = t.replace("&", "and").replace("'", "")
    words = [w for w in re.split(r"[\s_\-]+", t) if w and not (len(w) <= 2 and not re.search(r"[A-Za-z0-9]", w))]
    if not words or len(" ".join(words)) > 40:
        return ""
    return "_".join(w[:1].upper() + w[1:] for w in words)


def slug_label(url, root):
    rel = urlparse(url).path[len(urlparse(root).path):].strip("/")
    if not rel:
        return "Home"
    rel = re.sub(r"\.(html?|php)$", "", rel.split("/")[-1], flags=re.I)
    return clean_label(rel.replace("-", " ").replace("_", " ").title()) or "Page"


def numbered_names(pages):
    """[(url, label)] -> {url: '01_Home', ...} in order, unique."""
    out, used = {}, set()
    for i, (u, label) in enumerate(pages, 1):
        base = f"{i:02d}_{label}"
        name, n = base, 2
        while name.lower() in used:
            name = f"{base}_{n}"; n += 1
        used.add(name.lower())
        out[u] = name
    return out


def read_sites(path: Path, crawl_default: bool):
    """urls.txt lines:  https://site.com   or   Site Name | https://site.com
    Several lines with the same Site Name = exactly those pages (no crawling)."""
    groups, order = {}, []
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "|" in line:
            name, url = [x.strip() for x in line.split("|", 1)]
        else:
            name, url = "", line
        url = norm_url(url)
        name = safe_name(name) if name else site_name_from(url)
        if name not in groups:
            groups[name] = []
            order.append(name)
        if url not in groups[name]:
            groups[name].append(url)
    sites = []
    for n in order:
        urls = groups[n]
        sites.append(dict(name=n, root=urls[0], pages=urls, crawl=crawl_default and len(urls) == 1))
    return sites


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


# ------------------------------------------------------------------ capture
async def settle(page, url):
    resp = await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    if resp is not None and resp.status >= 400:
        raise RuntimeError(f"page not found (HTTP {resp.status})")
    try:
        await page.wait_for_load_state("load", timeout=25000)
    except PWTimeout:
        pass
    try:
        await page.wait_for_load_state("networkidle", timeout=8000)
    except PWTimeout:
        pass
    await page.add_style_tag(content=CLEAN_CSS)
    h = await page.evaluate(SCROLL_JS)
    try:
        await page.wait_for_load_state("networkidle", timeout=6000)
    except PWTimeout:
        pass
    try:
        await page.evaluate(IMAGES_JS)
    except Exception as e:
        if "crashed" in str(e) or "closed" in str(e):
            raise
    await page.wait_for_timeout(700)
    return h


SITEMAPS = ("wp-sitemap.xml", "sitemap_index.xml", "sitemap.xml", "page-sitemap.xml", "wp-sitemap-posts-page-1.xml")


async def fetch_text(ctx, url):
    try:
        r = await ctx.request.get(url, timeout=20000)
        if r.ok:
            return await r.text()
    except Exception:
        pass
    return ""


def site_prefix(path):
    """Folder the website lives in: '' for the domain root, '/en' for a language folder.
    A pasted link to a file such as /index.html or /home.php means the site root."""
    parts = [x for x in path.split("/") if x]
    if parts and "." in parts[-1]:
        parts = parts[:-1]
    return "/" + "/".join(parts) if parts else ""


async def sitemap_urls(ctx, root, limit=400):
    """Every page listed in the website's sitemap (WordPress/Elementor sites have one)."""
    pr = urlparse(root)
    base = f"{pr.scheme}://{pr.netloc}"
    prefix = site_prefix(pr.path)
    todo = [f"{base}{prefix}/{n}" for n in SITEMAPS] + ([f"{base}/{n}" for n in SITEMAPS] if prefix else [])
    seen, urls, done = set(), [], 0
    while todo and len(urls) < limit and done < 12:
        sm = todo.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        xml = await fetch_text(ctx, sm)
        if "<loc>" not in xml:
            continue
        done += 1
        locs = re.findall(r"<loc>\s*(?:<!\[CDATA\[)?\s*([^<\]\s]+)", xml)
        subs = [l for l in locs if l.lower().split("?")[0].endswith(".xml")]
        todo = subs + todo          # sitemaps inside an index are read next
        urls += [l for l in locs if l not in subs]
    return urls


async def discover(ctx, site, max_pages, menu_only=True):
    """Returns [(url, label)]: home first, then the menu in its order, then the rest of the website
    (sitemap + links found on the pages) until max_pages."""
    root = site["root"]
    if not site["crawl"]:
        return [(u, slug_label(u, root)) for u in site["pages"]]
    max_pages = max_pages if max_pages and max_pages > 0 else 300
    rp = urlparse(root)
    root_prefix = site_prefix(rp.path)
    found, labels = [root], {root: ""}

    def take(href, text=""):
        """Add an internal page link; returns True if it was new."""
        p = urlparse(href)
        if p.scheme not in ("http", "https") or host(href) != host(root):
            return False
        if p.fragment or href.endswith("#"):   # "Pages" dropdown toggles and on-page anchors
            return False
        if not p.path.startswith(root_prefix) or SKIP_EXT.search(p.path) or SKIP_PATH.search(p.path):
            return False
        u = norm_url(urlunparse((rp.scheme, rp.netloc, p.path, "", "", "")))
        lab = clean_label(text)
        if u in labels:
            if not labels[u] and lab:
                labels[u] = lab
            return False
        if len(found) >= max_pages:
            return False
        found.append(u)
        labels[u] = lab
        return True

    page = await ctx.new_page()
    try:
        await settle(page, root)
        links = await page.evaluate(LINKS_JS)
        for want_menu in (True, False):
            for ln in links:
                if ln["menu"] == want_menu and (want_menu or not menu_only):
                    take(ln["href"], ln["text"])
        if menu_only and len(found) < 3:       # menu not found: use every link on the page
            for ln in links:
                take(ln["href"], ln["text"])
    except Exception as e:
        if "crashed" in str(e) or "closed" in str(e):
            raise
        log(f"   ! could not read links on {root}: {short(e)}")
    finally:
        await page.close()
    n_menu = len(found)
    if menu_only and len(found) >= 3:
        log(f"   menu pages only: {len(found)} page(s)")
        return [(u, labels.get(u) or slug_label(u, root)) for u in found]
    if menu_only:
        log(f"   only {len(found)} page(s) found in the menu - also looking through the rest of the website")
        menu_only = False

    # the website's sitemap lists every page
    try:
        for u in await sitemap_urls(ctx, root):
            take(u)
    except Exception as e:
        log(f"   (sitemap not read: {short(e)})")
    n_map = len(found) - n_menu

    # follow links found inside the pages we already have (2 levels), without opening a browser tab
    n_deep, i, fetched = 0, 1, 0
    while len(found) < max_pages and i < len(found) and fetched < 60:
        html = await fetch_text(ctx, found[i])
        i += 1
        fetched += 1
        for m in re.finditer(r"""<a\s[^>]*?href\s*=\s*["']([^"'#]+)["'][^>]*>(.*?)</a>""", html, re.I | re.S):
            href = urljoin(found[i - 1], m.group(1).strip())
            if take(href, re.sub(r"<[^>]+>", " ", m.group(2)).strip()):
                n_deep += 1
    # drop links that lead to "page not found"
    sem = asyncio.Semaphore(8)

    async def alive(u):
        async with sem:
            try:
                r = await ctx.request.get(u, timeout=20000)
                return r.status < 400
            except Exception:
                return True
    ok = await asyncio.gather(*(alive(u) for u in found[1:]))
    found = [found[0]] + [u for u, good in zip(found[1:], ok) if good]
    log(f"   found {len(found)} page(s): {n_menu} from the menu, {n_map} from the sitemap, {n_deep} from links inside pages")
    return [(u, labels.get(u) or slug_label(u, root)) for u in found]


async def shoot(ctx, url, kind, out_png):
    vp = VIEWPORTS[kind]
    page = await ctx.new_page()
    try:
        h = await settle(page, url)
        if kind == "desk":
            try:
                cols = await page.evaluate(COLORS_JS)
                (out_png.parent / "_data").mkdir(exist_ok=True)
                (out_png.parent / "_data" / (out_png.stem + "_colors.json")).write_text(json.dumps(cols))
            except Exception:
                pass
        h = min(int(h or vp["height"]), vp["max_h"])
        await page.screenshot(path=str(out_png), full_page=True, type="png",
                              clip=dict(x=0, y=0, width=vp["width"], height=max(h, vp["height"])),
                              animations="disabled", timeout=90000)
    finally:
        await page.close()


def short(e):
    return str(e).strip().splitlines()[0][:160]


# ------------------------------------------------------------------ drawing
FIN = {
    "black": dict(body=(43, 46, 52), edge=(26, 28, 32), bezel=(8, 9, 11), b1=(58, 62, 69), b2=(23, 25, 28)),
    "silver": dict(body=(211, 215, 221), edge=(169, 175, 184), bezel=(12, 13, 15), b1=(236, 238, 241), b2=(180, 186, 194)),
}


def mix(a, b, t):
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def lum(c):
    return (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) / 255


def hexrgb(h):
    h = h.strip().lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def tint_of(img):
    """Brand-ish color from the top of a screenshot."""
    top = img.crop((0, 0, img.width, min(img.height, int(img.width * 0.6)))).convert("RGB").resize((24, 16))
    px = list(top.get_flattened_data() if hasattr(top, "get_flattened_data") else top.getdata())
    avg = tuple(int(sum(p[i] for p in px) / len(px)) for i in range(3))
    best = max(px, key=lambda p: max(p) - min(p))
    return mix(avg, best, 0.6) if max(best) - min(best) > 40 else avg


def sat(c):
    return max(c) - min(c)


def site_palette(colors, img):
    """Pick (brand, page) colors from what the website itself uses."""
    page = tuple(int(v) for v in (colors or {}).get("page") or (255, 255, 255))[:3]
    brand = None
    for key in ("primary", "accent", "secondary"):
        c = (colors or {}).get(key)
        if c and (len(c) < 4 or c[3] > 0.5) and sat(c[:3]) > 28 and 0.03 < lum(c[:3]) < 0.9:
            brand = tuple(int(v) for v in c[:3]); break
    if brand is None and (colors or {}).get("buttons"):
        brand = tuple(int(v) for v in colors["buttons"][0][:3])
    if brand is None:
        brand = tint_of(img)
    return brand, page


def backdrop(mode, brand, page):
    """Two gradient stops that match the website."""
    W, K = (255, 255, 255), (12, 15, 22)
    dark_site = lum(page) < 0.25
    if mode == "auto":   # follows the site: dark sites get dark, light sites get a soft brand tint
        if dark_site:
            return mix(brand, page, 0.82), mix(brand, page, 0.62)
        return mix(brand, W, 0.86), mix(brand, W, 0.66)
    if mode == "brand":  # stronger: the actual brand color as a gradient
        return mix(brand, W, 0.12), mix(brand, K, 0.28)
    if mode == "site":   # the page's own background color
        return page, mix(page, brand, 0.12)
    if mode == "autodark":
        return mix(brand, K, 0.86), mix(brand, K, 0.66)
    if mode == "white":
        return W, W
    cols = [hexrgb(c) for c in mode.split(",")]
    return cols[0], cols[-1]


def gradient(size, a, b):
    w, h = size
    g = Image.new("L", (64, 64))
    g.putdata([int((x + y) / 126 * 255) for y in range(64) for x in range(64)])
    g = g.resize((w, h), Image.BILINEAR)
    return Image.composite(Image.new("RGB", size, b), Image.new("RGB", size, a), g)


class Canvas:
    def __init__(self, w, h, ss, stops, finish, shadow, glare, url_text):
        self.ss = ss
        self.W, self.H = w * ss, h * ss
        a, b = stops
        self.im = gradient((self.W, self.H), a, b).convert("RGBA")
        self.d = ImageDraw.Draw(self.im)
        self.F = FIN[finish]
        self.shadow = shadow
        self.glare = glare
        self.url_text = url_text
        self.zoom = 1.0
        self.stops = (a, b)
        self.k = self.W / 1600

    # shapes ---------------------------------------------------------
    def rrect(self, box, r, fill):
        self.d.rounded_rectangle([round(v) for v in box], radius=max(0, round(r)), fill=fill)

    def drop_shadow(self, box, r, amount):
        if self.shadow <= 0:
            return
        blur = amount * self.k * self.shadow * 0.55
        off = amount * self.k * self.shadow * 0.45
        x0, y0, x1, y1 = box
        m = int(blur * 3 + off + 4)
        rx0, ry0 = max(0, int(x0 - m)), max(0, int(y0 - m))
        rx1, ry1 = min(self.W, int(x1 + m)), min(self.H, int(y1 + m + off))
        if rx1 <= rx0 or ry1 <= ry0:
            return
        mask = Image.new("L", (rx1 - rx0, ry1 - ry0), 0)
        ImageDraw.Draw(mask).rounded_rectangle([x0 - rx0, y0 - ry0 + off, x1 - rx0, y1 - ry0 + off],
                                               radius=round(r), fill=int(255 * 0.34 * self.shadow))
        mask = mask.filter(ImageFilter.GaussianBlur(max(1, blur)))
        shade = Image.new("RGBA", mask.size, (10, 14, 25, 255))
        shade.putalpha(mask)
        self.im.alpha_composite(shade, (rx0, ry0))

    def screen(self, src, box, scroll, r, glare=True, top=0):
        x0, y0, x1, y1 = [round(v) for v in box]
        w, h = x1 - x0, y1 - y0
        if w <= 0 or h <= 0:
            return
        top = round(top)
        fill = src.getpixel((2, 2))[:3] if src is not None else (255, 255, 255)
        tile = Image.new("RGB", (w, h), fill)
        if top:  # phone status bar strip with time + battery, page starts below it
            dd = ImageDraw.Draw(tile)
            ink = (20, 20, 20) if lum(fill) > 0.5 else (245, 245, 245)
            try:
                font = ImageFont.load_default(size=max(6, round(top * 0.36)))
                dd.text((w * 0.14, top * 0.55), "9:41", fill=ink, font=font, anchor="lm")
            except Exception:
                pass
            bw, bh = w * 0.075, top * 0.22
            dd.rounded_rectangle([w * 0.82, top * 0.55 - bh / 2, w * 0.82 + bw, top * 0.55 + bh / 2], radius=bh * .3, outline=ink, width=max(1, round(bh * .12)))
            dd.rounded_rectangle([w * 0.82 + bh * .2, top * 0.55 - bh / 2 + bh * .2, w * 0.82 + bw * .75, top * 0.55 + bh / 2 - bh * .2], radius=bh * .15, fill=ink)
        h_avail = h - top
        if src is not None and h_avail > 0:
            h0 = h
            h = h_avail
            need = h * src.width / w
            if need >= src.height:
                part = src.resize((w, max(1, round(src.height * w / src.width))), Image.LANCZOS)
            else:
                sy = (src.height - need) * max(0.0, min(1.0, scroll))
                part = src.crop((0, round(sy), src.width, round(sy + need))).resize((w, h), Image.LANCZOS)
            tile.paste(part.convert("RGB"), (0, top))
            h = h0
        if glare and self.glare:
            g = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            ImageDraw.Draw(g).polygon([(0, 0), (w * 0.55, 0), (0, h * 0.85)], fill=(255, 255, 255, 9))
            tile = Image.alpha_composite(tile.convert("RGBA"), g)
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=max(0, round(r)), fill=255)
        self.im.paste(tile.convert("RGB"), (x0, y0), mask)

    # devices --------------------------------------------------------
    def laptop(self, x, y, w, src, scroll):
        F = self.F
        lw = w * 0.84; lx = x + (w - lw) / 2; lh = lw * 0.65; bh = w * 0.035; y2 = y + lh
        self.drop_shadow((x, y, x + w, y2 + bh), lw * 0.03, 70)
        self.rrect((lx, y, lx + lw, y2), lw * 0.028, F["edge"])
        self.rrect((lx + lw * .004, y + lw * .004, lx + lw * .996, y2), lw * 0.025, F["bezel"])
        m = lw * 0.028
        self.screen(src, (lx + m, y + m, lx + lw - m, y2 - lw * 0.042), scroll, lw * 0.006)
        cr = lw * 0.003
        self.d.ellipse([lx + lw / 2 - cr, y + m / 2 - cr, lx + lw / 2 + cr, y + m / 2 + cr], fill=(29, 32, 38))
        # base with vertical gradient
        base = gradient((max(1, round(w)), max(1, round(bh))), F["b1"], F["b2"]).rotate(0)
        bmask = Image.new("L", base.size, 0)
        ImageDraw.Draw(bmask).polygon([(0, 0), (w, 0), (w * .985, bh), (w * .015, bh)], fill=255)
        vg = Image.linear_gradient("L").resize(base.size)
        base = Image.composite(Image.new("RGB", base.size, F["b2"]), Image.new("RGB", base.size, F["b1"]), vg)
        self.im.paste(base, (round(x), round(y2)), bmask)
        self.rrect((x + w * .43, y2, x + w * .57, y2 + bh * .32), bh * .16, mix(F["b1"], (0, 0, 0), .25))

    def phone(self, x, y, w, src, scroll):
        F = self.F
        h = w * 2.05; r = w * 0.17
        self.drop_shadow((x, y, x + w, y + h), r, 50)
        self.rrect((x, y, x + w, y + h), r, F["edge"])
        self.rrect((x + w * .012, y + w * .012, x + w * .988, y + h - w * .012), r * .95, F["body"])
        b = w * 0.03
        self.rrect((x + b, y + b, x + w - b, y + h - b), r * .88, F["bezel"])
        s = w * 0.055
        self.screen(src, (x + s, y + s, x + w - s, y + h - s), scroll, r * .72, top=w * 0.16)
        self.rrect((x + w * .35, y + s + w * .03, x + w * .65, y + s + w * .115), w * .045, (0, 0, 0))

    def tablet(self, x, y, w, src, scroll):
        F = self.F
        h = w * 1.38; r = w * 0.065
        self.drop_shadow((x, y, x + w, y + h), r, 55)
        self.rrect((x, y, x + w, y + h), r, F["edge"])
        b = w * 0.012
        self.rrect((x + b, y + b, x + w - b, y + h - b), r * .9, F["bezel"])
        s = w * 0.045
        self.screen(src, (x + s, y + s, x + w - s, y + h - s), scroll, r * .4)

    def monitor(self, x, y, w, src, scroll):
        F = self.F
        sh = w * .585; ch = w * .07; nh = w * .13; fh = w * .025
        nx = x + w * .43; nw = w * .14; ny = y + sh + ch
        self.d.polygon([(nx + nw * .08, ny), (nx + nw * .92, ny), (nx + nw, ny + nh), (nx, ny + nh)], fill=F["b2"])
        self.d.polygon([(nx + nw * .3, ny), (nx + nw * .7, ny), (nx + nw * .75, ny + nh), (nx + nw * .25, ny + nh)], fill=F["b1"])
        self.drop_shadow((x + w * .33, ny + nh - 2, x + w * .67, ny + nh + fh), fh * .5, 30)
        self.rrect((x + w * .33, ny + nh - 2, x + w * .67, ny + nh + fh), fh * .5, F["b1"])
        self.drop_shadow((x, y, x + w, y + sh + ch), w * .016, 70)
        self.rrect((x, y, x + w, y + sh + ch), w * .016, F["body"])
        self.rrect((x, y, x + w, y + sh + w * .016), w * .016, F["bezel"])
        self.d.rectangle([round(x), round(y + sh), round(x + w), round(y + sh + w * .016)], fill=F["body"])
        m = w * .016
        self.screen(src, (x + m, y + m, x + w - m, y + sh - m), scroll, 2 * self.ss)

    def browser(self, x, y, w, h, src, scroll):
        bar = 56 * self.k; r = 16 * self.k
        self.drop_shadow((x, y, x + w, y + h), r, 70)
        self.rrect((x, y, x + w, y + h), r, (233, 235, 238))
        for i, col in enumerate([(255, 95, 87), (254, 188, 46), (40, 200, 64)]):
            cx, cy, rr_ = x + (28 + i * 22) * self.k, y + bar / 2, 6.5 * self.k
            self.d.ellipse([cx - rr_, cy - rr_, cx + rr_, cy + rr_], fill=col)
        aw = min(560 * self.k, w * .5)
        self.rrect((x + (w - aw) / 2, y + 13 * self.k, x + (w + aw) / 2, y + 43 * self.k), 15 * self.k, (255, 255, 255))
        try:
            font = ImageFont.load_default(size=max(8, round(14 * self.k)))
            self.d.text((x + w / 2, y + bar / 2), self.url_text, fill=(107, 114, 128), font=font, anchor="mm")
        except Exception:
            pass
        # screen with rounded bottom corners only
        sx0, sy0, sx1, sy1 = round(x), round(y + bar), round(x + w), round(y + h)
        self.screen(src, (sx0, sy0, sx1, sy1), scroll, 0, glare=False)
        corner = Image.new("L", (sx1 - sx0, sy1 - sy0), 0)
        ImageDraw.Draw(corner).rounded_rectangle([0, -r * 2, corner.width - 1, corner.height - 1], radius=round(r), fill=255)
        inv = corner.point(lambda v: 255 - v)
        self.im.paste(self.bg_at((sx0, sy0, sx1, sy1)), (sx0, sy0), inv)

    def bg_at(self, box):
        return self._bg.crop(box)

    # layout ---------------------------------------------------------
    def place(self, scene, srcs, pad_pct, scroll):
        self._bg = self.im.copy()
        a = srcs["desk"].height / srcs["desk"].width if srcs.get("desk") else 1
        P = {
            "laptop_phone": [("laptop", 0, 0, 1200, "desk", None), ("phone", 1060, 250, 230, "mob", None)],
            "three": [("monitor", 180, 0, 1100, "desk", None), ("tablet", 0, 367, 380, "tab", None), ("phone", 1170, 481, 200, "mob", None)],
            "laptop": [("laptop", 0, 0, 1200, "desk", None)],
            "monitor": [("monitor", 0, 0, 1200, "desk", None)],
            "browser": [("browser", 0, 0, 1400, "desk", None, 880)],
            "fullpage": [("browser", 0, 0, 1000, "desk", 0.0, 56 + 1000 * a)],
            "phones": [("phone", 0, 70, 300, "mob", .35), ("phone", 680, 70, 300, "mob", .7), ("phone", 340, 0, 300, "mob", 0.0)],
            "tablet_phone": [("tablet", 0, 0, 600, "tab", None), ("phone", 520, 346, 250, "mob", None)],
        }[scene]

        def dh(p):
            d, w = p[0], p[3]
            return {"laptop": w * .84 * .65 + w * .035, "phone": w * 2.05, "tablet": w * 1.38,
                    "monitor": w * .81}.get(d, p[6] if len(p) > 6 else 0)

        x0 = min(p[1] for p in P); y0 = min(p[2] for p in P)
        x1 = max(p[1] + p[3] for p in P); y1 = max(p[2] + dh(p) for p in P)
        pad = min(self.W, self.H) * pad_pct / 100
        aw, ah = self.W - 2 * pad, self.H - 2 * pad
        k = min(aw / (x1 - x0), ah / (y1 - y0)) * (self.zoom if scene != "fullpage" else 1)
        ox = pad + (aw - (x1 - x0) * k) / 2 - x0 * k
        oy = pad + (ah - (y1 - y0) * k) / 2 - y0 * k
        self.k = k
        for p in P:
            d, x, y, w, use, sc = p[:6]
            src = srcs.get(use) or srcs.get("desk")
            sc = scroll if sc is None else sc
            X, Y, Wd = ox + x * k, oy + y * k, w * k
            if d == "browser":
                self.browser(X, Y, Wd, p[6] * k, src, sc)
            else:
                getattr(self, d)(X, Y, Wd, src, sc)

    # site collages ---------------------------------------------------
    def strip(self, src, x, y, w, top, h, r, shadow=30):
        """A slice of a page (from `top` in source pixels) drawn `w` wide and `h` tall."""
        x0, y0, w = round(x), round(y), round(w)
        if w <= 0 or y0 >= self.H:
            return
        scale = w / src.width
        src_h = min(h / scale, src.height - top, (self.H - y0) / scale + 2)
        if src_h <= 1:
            return
        hc = max(1, round(src_h * scale))
        if shadow:
            self.drop_shadow((x0, y0, x0 + w, y0 + hc), r, shadow)
        part = src.crop((0, round(top), src.width, round(top + src_h))).resize((w, hc), Image.LANCZOS).convert("RGB")
        mask = Image.new("L", (w, hc), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, hc - 1], radius=max(0, round(r)), fill=255)
        self.im.paste(part, (x0, y0), mask)

    def laptop_spill(self, x, y, sw, src):
        """Laptop whose screen shows the page, with the page continuing below it."""
        F = self.F
        m = 0.028
        lw = sw / (1 - 2 * m); lx = x - lw * m; ly = y - lw * m
        lh = lw * 0.65; bw = lw / 0.84; bx = lx - (bw - lw) / 2; bh = bw * 0.035; y2 = ly + lh
        self.drop_shadow((bx, ly, bx + bw, y2 + bh), lw * .03, 60)
        self.rrect((lx, ly, lx + lw, y2), lw * 0.028, F["edge"])
        self.rrect((lx + lw * .004, ly + lw * .004, lx + lw * .996, y2), lw * 0.025, F["bezel"])
        base = Image.composite(Image.new("RGB", (max(1, round(bw)), max(1, round(bh))), F["b2"]),
                               Image.new("RGB", (max(1, round(bw)), max(1, round(bh))), F["b1"]),
                               Image.linear_gradient("L").resize((max(1, round(bw)), max(1, round(bh)))))
        bmask = Image.new("L", base.size, 0)
        ImageDraw.Draw(bmask).polygon([(0, 0), (bw, 0), (bw * .985, bh), (bw * .015, bh)], fill=255)
        self.im.paste(base, (round(bx), round(y2)), bmask)
        self.drop_shadow((x, y2, x + sw, self.H + 200), 4 * self.k, 45)
        self.strip(src, x, y, sw, 0, self.H - y + 20, lw * 0.006, shadow=0)

    def laptop_hero(self, x, y, sw, src):
        """Laptop whose screen shows only the top of the page (the hero). Returns bottom y."""
        m = 0.028
        lw = sw / (1 - 2 * m)
        w = lw / 0.84
        self.laptop(x - lw * m - (w - lw) / 2, y - lw * m, w, src, 0.0)
        return y - lw * m + lw * 0.65 + w * 0.035

    def grid(self, step, color):
        for gx in range(0, self.W, max(4, round(step))):
            self.d.line([(gx, 0), (gx, self.H)], fill=color, width=max(1, self.ss))
        for gy in range(0, self.H, max(4, round(step))):
            self.d.line([(0, gy), (self.W, gy)], fill=color, width=max(1, self.ss))

    def perspective_page(self, src, quad, src_top=0, aspect=None):
        """Draw a page slice mapped onto quad = [tl, tr, br, bl] (canvas pixels)."""
        (x0, y0), (x1, y1), (x2, y2), (x3, y3) = quad
        top_w = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** .5
        left_h = ((x3 - x0) ** 2 + (y3 - y0) ** 2) ** .5
        sw = round(max(top_w, 10)); sh = round(max(left_h, 10))
        need = sh * src.width / sw
        part = src.crop((0, round(src_top), src.width, round(min(src.height, src_top + need))))
        part = part.resize((sw, max(1, round(part.height * sw / src.width))), Image.LANCZOS).convert("RGBA")
        page = Image.new("RGBA", (sw, sh), (255, 255, 255, 255)); page.paste(part, (0, 0))
        minx, miny = int(min(x0, x1, x2, x3)), int(min(y0, y1, y2, y3))
        maxx, maxy = int(max(x0, x1, x2, x3)) + 1, int(max(y0, y1, y2, y3)) + 1
        dst = [(x0 - minx, y0 - miny), (x1 - minx, y1 - miny), (x2 - minx, y2 - miny), (x3 - minx, y3 - miny)]
        srcq = [(0, 0), (sw, 0), (sw, sh), (0, sh)]
        coeffs = perspective_coeffs(dst, srcq)
        warped = page.transform((maxx - minx, maxy - miny), Image.PERSPECTIVE, coeffs, Image.BICUBIC, fillcolor=(0, 0, 0, 0))
        # soft shadow from the page's own shape
        if self.shadow > 0:
            a = warped.getchannel("A")
            pad = round(60 * self.k)
            sm = Image.new("L", (a.width + 2 * pad, a.height + 2 * pad), 0)
            sm.paste(a.point(lambda v: int(v * .42 * self.shadow)), (pad, pad + round(18 * self.k)))
            sm = sm.filter(ImageFilter.GaussianBlur(28 * self.k * self.shadow + 1))
            sh_img = Image.new("RGBA", sm.size, (0, 0, 0, 255)); sh_img.putalpha(sm)
            self.overlay(sh_img, minx - pad, miny - pad)
        self.overlay(warped, minx, miny)

    def badges(self, files, size):
        """Put the user's own badge/logo PNGs in the corners (top-right, then bottom-right, top-left...)."""
        spots = [(0.965, 0.035, "rt"), (0.965, 0.965, "rb"), (0.035, 0.035, "lt"), (0.035, 0.965, "lb")]
        for f, (fx, fy, anc) in zip(files, spots):
            try:
                b = Image.open(f).convert("RGBA")
            except Exception:
                continue
            h = round(size); w = round(b.width * h / b.height)
            b = b.resize((w, h), Image.LANCZOS)
            x = round(self.W * fx - (w if anc[0] == "r" else 0))
            y = round(self.H * fy - (h if anc[1] == "b" else 0))
            self.overlay(b, x, y)

    def rot_strip(self, src, cx, top_y, w, h, angle, src_top=0):
        """A tall page slice, tilted by `angle` degrees, with its own shadow."""
        w = round(w); h = round(h)
        m = round(90 * self.k)
        layer = Image.new("RGBA", (w + 2 * m, h + 2 * m), (0, 0, 0, 0))
        if self.shadow > 0:
            sm = Image.new("L", layer.size, 0)
            off = round(28 * self.k * self.shadow)
            ImageDraw.Draw(sm).rectangle([m, m + off, m + w, m + h + off], fill=int(255 * .38 * self.shadow))
            sm = sm.filter(ImageFilter.GaussianBlur(max(1, 34 * self.k * self.shadow)))
            sh = Image.new("RGBA", layer.size, (10, 14, 25, 255)); sh.putalpha(sm)
            layer.alpha_composite(sh)
        scale = w / src.width
        src_h = min(h / scale, src.height - src_top)
        part = src.crop((0, round(src_top), src.width, round(src_top + src_h))).resize((w, max(1, round(src_h * scale))), Image.LANCZOS)
        layer.paste(part.convert("RGB"), (m, m))
        rot = layer.rotate(angle, resample=Image.BICUBIC, expand=True)
        self.overlay(rot, round(cx - rot.width / 2), round(top_y + (h + 2 * m) / 2 - rot.height / 2 - m))

    def overlay(self, img, x, y):
        """alpha_composite that tolerates parts outside the canvas."""
        sx, sy = max(0, -x), max(0, -y)
        ex, ey = min(img.width, self.W - x), min(img.height, self.H - y)
        if ex <= sx or ey <= sy:
            return
        self.im.alpha_composite(img.crop((sx, sy, ex, ey)), (x + sx, y + sy))

    def text(self, xy, s, font, fill, anchor="la"):
        if s:
            self.d.text(xy, s, font=font, fill=fill, anchor=anchor)

    def save(self, path, fmt, quality):
        out = self.im
        if self.ss != 1:
            out = out.resize((self.W // self.ss, self.H // self.ss), Image.LANCZOS)
        out = out.convert("RGB")
        if fmt == "png":
            out.save(path, "PNG", optimize=True)
        elif fmt == "webp":
            out.save(path, "WEBP", quality=quality, method=4)
        else:
            out.save(path, "JPEG", quality=quality, optimize=True, progressive=True)


FONT_DIR = Path(__file__).resolve().parent / "fonts"
BADGE_DIR = Path(__file__).resolve().parent / "badges"


def perspective_coeffs(dst, src):
    """Coefficients for Image.transform(PERSPECTIVE) mapping output points dst -> input points src."""
    A, B = [], []
    for (x, y), (u, v) in zip(dst, src):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); B.append(u)
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y]); B.append(v)
    n = 8
    M = [A[i] + [B[i]] for i in range(n)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        M[col], M[piv] = M[piv], M[col]
        for r in range(n):
            if r != col and M[col][col]:
                f = M[r][col] / M[col][col]
                M[r] = [a - f * b for a, b in zip(M[r], M[col])]
    return [M[i][n] / M[i][i] for i in range(n)]


def hero_end(img):
    """Source y where the hero ends: the strongest full-width background change
    between ~70% and ~150% of the first desktop screen."""
    first_screen = img.width * 900 / 1440
    lo, hi = int(first_screen * 0.7), int(min(img.height - 4, first_screen * 1.5))
    if hi <= lo:
        return min(img.height, round(first_screen))
    band = img.crop((0, lo, img.width, hi)).convert("L").resize((48, (hi - lo) // 2))
    px = band.load()
    best, by = 0, None
    for y in range(3, band.height - 3):
        a = sum(px[x, y - 3] for x in range(48)) / 48
        b = sum(px[x, y + 3] for x in range(48)) / 48
        # rows below must be calm (a plain section background), rows above may be busy (photo)
        calm = sum(abs(px[x, y + 3] - b) for x in range(48)) / 48
        score = abs(a - b) - calm * 0.5
        if score > best:
            best, by = score, y
    if by is None or best < 12:
        return min(img.height, round(first_screen))
    return lo + by * 2


def get_font(role, px, custom=None):
    """role 'title' = bold condensed headline (Anton), 'ui' = Archivo medium."""
    px = max(6, round(px))
    try:
        if role == "title":
            return ImageFont.truetype(custom or str(FONT_DIR / "Anton-Regular.ttf"), px)
        f = ImageFont.truetype(str(FONT_DIR / "Archivo.ttf"), px)
        try:
            f.set_variation_by_axes([560, 100])
        except Exception:
            pass
        return f
    except Exception:
        for cand in (r"C:\Windows\Fonts\arialbd.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
            try:
                return ImageFont.truetype(cand, px)
            except Exception:
                continue
        return ImageFont.load_default(size=px)


def fill_text(t, site, pages):
    return (t or "").replace("{site}", site).replace("{pages}", " | ".join(p.replace("-", " ").replace("_", " ") for p in pages[:6])).upper()


def section_edges(img):
    """Y positions where the page background changes (section boundaries), in source pixels."""
    small = img.convert("L").resize((24, max(2, img.height // 4)))
    px = small.load()
    rows = [(px[0, y] + px[1, y] + px[22, y] + px[23, y]) / 4 for y in range(small.height)]
    edges, last = [0], 0
    for y in range(2, len(rows) - 2):
        if abs(rows[y] - rows[y - 2]) > 10 and abs(rows[y + 2] - rows[y]) < 4 and (y - last) * 4 > img.width * 0.18:
            edges.append(y * 4); last = y
    edges.append(img.height)
    return edges


def compose_site(scene, shots, opt, size, out_path, colors, site_name, page_names):
    """Collage of several pages of one website (showcase / presentation)."""
    home = shots[0]
    brand, page = site_palette(colors, home)
    stops = backdrop(opt.bg, brand, page)
    W, H = size
    ss = 2 if W * H <= 4_200_000 else 1
    c = Canvas(W, H, ss, stops, opt.finish, opt.shadow / 100, False, "")
    c._bg = c.im.copy()
    z = opt.zoom / 100
    W, H, k = c.W, c.H, c.k
    others = shots[1:] or shots
    R = __import__("random").Random(len(site_name) * 131 + W + H)

    if scene == "showcase":
        g = W * 0.035
        c1, c2 = W * 0.34 * z, W * 0.27 * z
        x1 = max(W * 0.02, (W - (c1 + 2 * c2 + 2 * g)) / 2 + W * 0.035)
        sw = c1 * 0.86
        lap_bottom = c.laptop_hero(x1 + (c1 - sw) / 2, H * 0.09, sw, home)

        cuts = {id(im): section_edges(im) for im in shots}

        def card(src, w, first, after=0):
            """Pick a slice that starts and ends on section edges."""
            ed = cuts[id(src)]
            scale = w / src.width
            lo, hi = w * 0.9, w * 1.7
            starts = [after] if (first and after) else [0] if first else [e for e in ed[:-1] if e > max(0, after)] or [after]
            if not first:
                R.shuffle(starts)
            for st in starts:
                ends = [e for e in ed if lo <= (e - st) * scale <= hi]
                if ends:
                    return st, (R.choice(ends) - st) * scale
            st = starts[0]
            return st, min(w * R.uniform(1.0, 1.5), (src.height - st) * scale)

        def column(x, w, y, start, pool=None, after=0):
            pool = pool or others
            i = start
            first = True
            while y < H:
                src = pool[i % len(pool)]
                top, ch = card(src, w, first, after if src is home else 0)
                if ch < w * 0.3:
                    top, ch = after if src is home else 0, w * 1.2
                c.strip(src, x, y, w, top, ch, 5 * k, 30)
                y += ch + g * 0.85; i += 1; first = False

        # under the laptop: the home page's next sections as cards
        column(x1, c1, lap_bottom + g * 0.9, 0, pool=[home], after=hero_end(home))

        column(x1 + c1 + g, c2, -H * 0.06, 0)
        column(x1 + c1 + g + c2 + g, c2, -H * 0.22, 1 if len(others) > 1 else 0)

    elif scene == "presentation":  # banner + title + fanned pages
        ink = (24, 20, 18) if lum(mix(*stops, .5)) > 0.45 else (245, 243, 240)
        y = 0
        bl, br = fill_text(opt.banner_left, site_name, page_names), fill_text(opt.banner_right, site_name, page_names)
        if bl or br:
            bh = H * 0.042
            c.d.rectangle([0, 0, W, round(bh)], fill=mix(brand, (22, 16, 13), 0.62))
            f = get_font("ui", bh * 0.40)
            c.text((W * 0.06, bh / 2), bl, f, (250, 248, 245), "lm")
            c.text((W * 0.94, bh / 2), br, f, (250, 248, 245), "rm")
            y = bh
        ts, tb = fill_text(opt.title_small, site_name, page_names), fill_text(opt.title_big, site_name, page_names)
        ty = y + H * 0.03
        if ts:
            c.text((W / 2, ty), ts, get_font("ui", H * 0.024), ink, "mt"); ty += H * 0.032
        if tb:
            c.text((W / 2, ty), tb, get_font("title", H * 0.058, opt.font_title), ink, "mt"); ty += H * 0.07
        top = max(ty + H * 0.045, H * 0.12)
        sw_side = W * 0.30 * z
        left = others[0]; right = others[1 % len(others)] if len(others) > 1 else others[0]
        c.rot_strip(left, W * 0.235, top + H * 0.08, sw_side, H - top, 6)
        c.rot_strip(right, W * 0.765, top + H * 0.08, sw_side, H - top, -6,
                    src_top=0 if right is not left else min(right.height * 0.4, max(0, right.height - 2000)))
        sw = W * 0.42 * z
        lap_bottom = c.laptop_hero((W - sw) / 2, top + sw * 0.03, sw, home)
        he = hero_end(home)
        c.strip(home, (W - sw) / 2, lap_bottom + H * 0.025, sw, he, H, 6 * k, 40)

    elif scene == "perspective":
        if opt.bg in ("auto", "autodark"):
            c.im.paste(gradient((W, H), mix(brand, (8, 8, 10), 0.80), mix(brand, (8, 8, 10), 0.58)), (0, 0))
            c.d = ImageDraw.Draw(c.im)
        back = others[0] if len(shots) > 1 else home
        bt = 0 if back is not home else hero_end(home)
        quad = [(W * .615, H * .065), (W * .99, H * .135), (W * .975, H * 1.08), (W * .60, H * 1.02)]
        c.perspective_page(back, quad, bt)
        fw = W * 0.53 * z
        c.strip(home, W * 0.12, H * 0.025, fw, 0, H, 4 * k, 60)
        if BADGE_DIR.exists():
            c.badges(sorted(BADGE_DIR.glob("*.png")), H * 0.055)

    elif scene == "two_pages":
        mid = mix(*stops, .5)
        c.grid(W / 28, mix(mid, (0, 0, 0) if lum(mid) > .4 else (255, 255, 255), 0.07))
        lw_ = W * 0.555 * z
        c.strip(home, W * 0.035, H * 0.045, lw_, 0, H, 4 * k, 35)
        right = others[0] if len(shots) > 1 else home
        rt = hero_end(right)
        rx = W * 0.035 + lw_ + W * 0.035
        c.strip(right, rx, H * 0.006, W - rx - W * 0.035, rt, H, 4 * k, 35)

    elif scene == "hero_card":
        cw = W * 0.91 * z
        cut = min(home.height, round(home.width * 900 / 1440 * 1.25))
        c.strip(home, (W - cw) / 2, H * 0.05, cw, 0, min(H, cut * cw / home.width), 18 * k, 45)

    c.save(out_path, opt.format, opt.quality)


def compose(scene, srcs, opt, url_text, out_path, colors=None, size=None):
    brand, page = site_palette(colors, srcs["desk"])
    stops = backdrop(opt.bg, brand, page)
    W2, H2 = size or (opt.w, opt.h)
    ss = 2 if W2 * H2 <= 4_200_000 else 1
    c = Canvas(W2, H2, ss, stops, opt.finish, opt.shadow / 100, not opt.no_glare, url_text)
    c.zoom = opt.zoom / 100
    if scene == "fullpage":
        # exact size: browser window as wide as the image allows, page runs off the bottom edge
        c._bg = c.im.copy()
        pad = min(c.W, c.H) * opt.pad / 100
        bw = min(c.W - 2 * pad, (c.W - 2 * pad) * c.zoom)
        c.k = bw / 1000
        c.browser((c.W - bw) / 2, pad, bw, c.H - pad + 60 * c.k, srcs["desk"], 0.0)
    else:
        c.place(scene, srcs, opt.pad, opt.scroll / 100)
    c.save(out_path, opt.format, opt.quality)


# ------------------------------------------------------------------ main flow
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp"}
SUFFIX_KIND = re.compile(r"[\s_\-]+(mobile|phone|mob|tablet|ipad)$", re.I)


def image_sites(paths):
    """Turn picked files/folders into sites.
    - files -> one site per parent folder
    - a folder with images -> one site (folder name)
    - a folder with sub-folders -> one site per sub-folder
    Files ending _Mobile / _Tablet are used as the phone / tablet screen of the matching page."""
    groups = {}

    def add(site_dir, f):
        groups.setdefault(site_dir, []).append(f)

    for raw in paths:
        p = Path(raw)
        if p.is_file() and p.suffix.lower() in IMG_EXT:
            add(p.parent, p)
        elif p.is_dir():
            direct = [f for f in sorted(p.iterdir()) if f.is_file() and f.suffix.lower() in IMG_EXT]
            if direct:
                for f in direct:
                    add(p, f)
            for sub in sorted(d for d in p.iterdir() if d.is_dir() and not d.name.startswith(("_", "."))):
                for f in sorted(sub.iterdir()):
                    if f.is_file() and f.suffix.lower() in IMG_EXT:
                        add(sub, f)
    sites = []
    for d, files in groups.items():
        pages, extra = {}, {}
        for f in sorted(files, key=lambda x: natural_key(x.stem)):
            m = SUFFIX_KIND.search(f.stem)
            if m:
                kind = "tab" if m.group(1).lower() in ("tablet", "ipad") else "mob"
                extra.setdefault(f.stem[:m.start()].lower(), {})[kind] = f
            else:
                pages[f.stem] = {"desk": f}
        for stem, v in pages.items():
            v.update(extra.get(stem.lower(), {}))
        # page names: keep "01_Home" style names, otherwise number them in file order
        ordered = list(pages.items())
        if not any(re.match(r"^\d{1,3}[\s_\-.]", k) for k, _ in ordered):
            # not numbered: the home page goes first, the rest stay in A-Z order
            home_like = re.compile(r"^(home|homepage|home[\s_\-]?page|index|front|main|landing)$", re.I)
            ordered.sort(key=lambda kv: 0 if home_like.match(kv[0]) else 1)
        named = []
        for i, (stem, v) in enumerate(ordered, 1):
            m = re.match(r"^(\d{1,3})[\s_\-.]+(.*)$", stem)
            label = clean_label(m.group(2) if m else stem) or "Page"
            named.append((f"{i:02d}_{label}", label, v))
        if named:
            sites.append(dict(name=safe_name(d.name), pages=named))
    return sites


def natural_key(t):
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", t)]


def run_images(opt):
    """Make mockups from screenshot files instead of website links."""
    sites = image_sites(opt.images)
    if not sites:
        sys.exit("No screenshots found. Pick PNG, JPG or WebP files, or a folder that contains them.")
    labels_map = scene_labels()
    scenes = []
    site_scenes = [x.strip() for x in opt.scenes.split(",") if x.strip() in labels_map]

    def sizes_for(sc):
        return opt.scene_sizes.get(sc) or opt.sizes or [style_size(sc)]

    def out_file(folder, base, sc, size):
        tag = f"_{size[0]}x{size[1]}" if len(sizes_for(sc)) > 1 else ""
        return folder / f"{base}{labels_map[sc]}{tag}.{opt.format}"

    out_root = Path(opt.out) if opt.out else desktop_dir() / "Mockups"
    out_root.mkdir(parents=True, exist_ok=True)
    log(f"Saving to: {out_root}")
    log(f"{len(sites)} website(s) from screenshots | styles: {len(site_scenes)}")
    made, failures, t0 = 0, [], time.time()
    for si, site in enumerate(sites, 1):
        log(f"[{si}/{len(sites)}] {site['name']}")
        log(f"   {len(site['pages'])} page(s): " + ", ".join(n for n, _, _ in site["pages"]))
        folder = out_root / site["name"]
        folder.mkdir(parents=True, exist_ok=True)
        desks = []
        for name, label, files in site["pages"]:
            try:
                srcs = {k: Image.open(v).convert("RGB") for k, v in files.items()}
            except Exception as e:
                failures.append(f"{site['name']}  {files['desk']}  ->  {short(e)}")
                log(f"   ! {name}: could not open the image")
                continue
            desks.append((label, srcs["desk"], srcs.get("mob")))
            if any(style_needs_phone(sc) for sc in site_scenes) and "mob" not in srcs:
                if not site.get("warned"):
                    log("   (pages without a _Mobile screenshot show the desktop screenshot on phones)")
                    site["warned"] = True
            for sc in scenes:
                for size in sizes_for(sc):
                    try:
                        compose(sc, srcs, opt, site["name"].lower().replace(" ", "") + ".com",
                                out_file(folder, name + "_", sc, size), None, size)
                        made += 1
                    except Exception as e:
                        failures.append(f"{site['name']}  {name}  ->  mockup error: {short(e)}")
            log(f"   + {name}")
        if site_scenes and desks:
            for sc in site_scenes:
                for size in sizes_for(sc):
                    try:
                        import styles
                        styles.render(sc, desks, opt, size, out_file(folder, "", sc, size),
                                      None, site["name"], site["name"].lower().replace(" ", "") + ".com")
                        made += 1
                    except Exception as e:
                        failures.append(f"{site['name']}  collage error: {short(e)}")
            log(f"   + site collages: {', '.join(site_scenes)}")
    if failures:
        (out_root / "failed-pages.txt").write_text("\n".join(failures), encoding="utf-8")
    log(f"Done: {made} mockups in {(time.time() - t0) / 60:.1f} min. Folder: {out_root}")


async def run(opt):
    sites = read_sites(Path(opt.urls), not opt.no_crawl)
    if not sites:
        sys.exit(f"No links found in {opt.urls}. Add one website link per line.")
    scenes = [s.strip() for s in opt.scenes.split(",") if s.strip()]
    labels_map = scene_labels()
    bad = [s for s in scenes if s not in labels_map]
    if bad:
        sys.exit(f"Unknown style(s): {', '.join(bad)}. Choose from: {', '.join(labels_map)}")
    site_scenes = [] if getattr(opt, "shots_only", False) else list(scenes)
    scenes = []

    def sizes_for(sc):
        return opt.scene_sizes.get(sc) or opt.sizes or [style_size(sc)]

    def out_file(folder, base, sc, size):
        multi = len(sizes_for(sc)) > 1
        tag = f"_{size[0]}x{size[1]}" if multi else ""
        return folder / f"{base}{labels_map[sc]}{tag}.{opt.format}"

    need = {"desk"}
    if any(style_needs_phone(s) for s in site_scenes):
        need.add("mob")
    if getattr(opt, "shots_only", False) and getattr(opt, "shots_mobile", False):
        need.add("mob")
    if getattr(opt, "shots_only", False) and getattr(opt, "shots_tablet", False):
        need.add("tab")

    out_root = Path(opt.out) if opt.out else desktop_dir() / "Mockups"
    out_root.mkdir(parents=True, exist_ok=True)
    log(f"Saving to: {out_root}")
    if getattr(opt, "shots_only", False):
        log(f"{len(sites)} website(s) | screenshots only (no mockups)")
    else:
        log(f"{len(sites)} website(s) | styles: {len(site_scenes)}")
    log("Size: " + (", ".join(f"{w}x{h}" for w, h in opt.sizes) if opt.sizes else "each style's own size"))

    failures, made = [], 0
    pool = ThreadPoolExecutor(max_workers=max(2, os.cpu_count() or 2))
    loop = asyncio.get_running_loop()
    t_start = time.time()

    async with async_playwright() as p:
        class Browsers:
            """Keeps one browser + a context per device; rebuilds them if Chromium crashes."""
            def __init__(self):
                self.browser, self.ctxs, self.gen, self.lock = None, {}, 0, asyncio.Lock()

            async def start(self):
                try:
                    if self.browser:
                        await self.browser.close()
                except Exception:
                    pass
                self.browser = await p.chromium.launch(args=["--disable-dev-shm-usage", "--hide-scrollbars", "--disable-gpu"])
                self.ctxs = {}
                for kind in need:
                    vp = VIEWPORTS[kind]
                    self.ctxs[kind] = await self.browser.new_context(
                        viewport=dict(width=vp["width"], height=vp["height"]), device_scale_factor=vp["scale"],
                        is_mobile=vp["mobile"], has_touch=vp["mobile"],
                        user_agent=MOBILE_UA if kind == "mob" else TABLET_UA if kind == "tab" else None,
                        ignore_https_errors=True, reduced_motion="reduce", color_scheme="light")
                self.gen += 1

            async def recover(self, seen_gen):
                async with self.lock:
                    if self.gen == seen_gen:   # nobody else restarted it yet
                        log("   (browser restarted after a crash)")
                        await self.start()

            async def run(self, make, tries=3):
                """make(ctxs) -> awaitable. Retries on crashes."""
                for attempt in range(tries):
                    g = self.gen
                    try:
                        return await make(self.ctxs)
                    except Exception as e:
                        msg = str(e)
                        if attempt == tries - 1:
                            raise
                        crashed = any(k in msg for k in ("crashed", "closed", "disconnected", "Target"))
                        if crashed or not self.browser.is_connected():
                            await self.recover(g)
                        else:
                            await asyncio.sleep(2)

        B = Browsers()
        await B.start()
        sem = asyncio.Semaphore(opt.workers)

        for si, site in enumerate(sites, 1):
            log(f"[{si}/{len(sites)}] {site['name']}  ({site['root']})")
            found = await B.run(lambda c: discover(c["desk"], site, opt.max_pages, getattr(opt, "page_source", "menu") != "all"))
            pages = [u for u, _ in found]
            names = numbered_names(found)
            labels = {u: lab for u, lab in found}
            log(f"   {len(pages)} page(s): " + ", ".join(names[u] for u in pages))
            folder = out_root / site["name"]
            shots = folder / "screenshots"
            shots.mkdir(parents=True, exist_ok=True)
            used = set()
            url_text = host(site["root"])
            desk_files = {}  # url -> (name, desktop screenshot) for the site collages

            async def do_page(url):
                nonlocal made
                name = names[url]
                old = page_name(url, site["root"])   # file names used by earlier versions
                async with sem:
                    files = {}
                    try:
                        for kind in sorted(need):
                            f = shots / (name + {"desk": "", "tab": "_Tablet", "mob": "_Mobile"}[kind] + ".png")
                            legacy = shots / f"{old}-{ {'desk': 'desktop', 'tab': 'tablet', 'mob': 'mobile'}[kind]}.png"
                            if opt.reuse and not f.exists() and legacy.exists():
                                legacy.replace(f)
                                lc = shots / f"{old}-colors.json"
                                if kind == "desk" and lc.exists():
                                    (shots / "_data").mkdir(exist_ok=True)
                                    lc.replace(shots / "_data" / f"{name}_colors.json")
                            if not (opt.reuse and f.exists()):
                                await B.run(lambda c, k=kind, f=f: shoot(c[k], url, k, f))
                            files[kind] = f
                    except Exception as e:
                        failures.append(f"{site['name']}  {url}  ->  {short(e)}")
                        log(f"   ! {name}: {short(e)}")
                        if "desk" not in files:
                            return
                desk_files[url] = (name, files["desk"], files.get("mob"))
                log(f"   + {name}")
                return

                def build():
                    srcs = {k: Image.open(v).convert("RGB") for k, v in files.items()}
                    cf = shots / "_data" / f"{name}_colors.json"
                    colors = json.loads(cf.read_text()) if cf.exists() else None
                    cnt = 0
                    for sc in scenes:
                        for size in sizes_for(sc):
                            compose(sc, srcs, opt, url_text, out_file(folder, name + "_", sc, size), colors, size)
                            cnt += 1
                    for im in srcs.values():
                        im.close()
                    return cnt

                try:
                    cnt = await loop.run_in_executor(pool, build)
                    made += cnt
                    log(f"   + {name}")
                except Exception as e:
                    failures.append(f"{site['name']}  {url}  ->  mockup error: {short(e)}")
                    log(f"   ! {name} mockup error: {short(e)}")

            await asyncio.gather(*(do_page(u) for u in pages))

            ordered = [desk_files[u] for u in pages if u in desk_files]
            if site_scenes and ordered:
                def build_site():
                    imgs = [(labels[u], Image.open(d).convert("RGB"), Image.open(m).convert("RGB") if m else None)
                            for u, (_, d, m) in ((u, desk_files[u]) for u in pages if u in desk_files)]
                    cf = shots / "_data" / f"{ordered[0][0]}_colors.json"
                    colors = json.loads(cf.read_text()) if cf.exists() else None
                    cnt = 0
                    import styles
                    for sc in site_scenes:
                        for size in sizes_for(sc):
                            styles.render(sc, imgs, opt, size, out_file(folder, "", sc, size), colors, site["name"], url_text)
                            cnt += 1
                    return cnt
                try:
                    made += await loop.run_in_executor(pool, build_site)
                    log(f"   + site collages: {', '.join(site_scenes)}")
                except Exception as e:
                    failures.append(f"{site['name']}  collage error: {short(e)}")
                    log(f"   ! collage error: {short(e)}")

            if not opt.keep_screenshots and not getattr(opt, "shots_only", False):
                for f in shots.glob("*.png"):
                    f.unlink()
                try:
                    shots.rmdir()
                except OSError:
                    pass
        try:
            await B.browser.close()
        except Exception:
            pass

    pool.shutdown()
    if failures:
        (out_root / "failed-pages.txt").write_text("\n".join(failures), encoding="utf-8")
    mins = (time.time() - t_start) / 60
    log(f"Done: {made} mockups in {mins:.1f} min. Folder: {out_root}")
    if failures:
        log(f"{len(failures)} page(s) failed; see failed-pages.txt")


SETTING_KEYS = {
    "size": str, "scenes": str, "background": ("bg", str), "device_color": ("finish", str), "shadow": int,
    "padding": ("pad", float), "scroll": int, "format": str, "quality": int, "max_pages": int, "workers": int,
    "output_folder": ("out", str), "glare": ("no_glare", "neg"), "find_pages": ("no_crawl", "neg"),
    "keep_screenshots": bool, "page_source": str, "device_size": ("zoom", float),
    "banner_left": str, "banner_right": str, "title_small": str, "title_big": str, "title_font_file": ("font_title", str),
}
TEXT_KEYS = {"banner_left", "banner_right", "title_small", "title_big"}

SIZE_PRESETS = [
    ("1920x1080", "landscape 16:9"),
    ("1600x1200", "4:3, good for showcase collages"),
    ("1588x1588", "square, good for presentation"),
    ("1200x900", "marketplace preview"),
    ("1080x1350", "portrait / social post"),
    ("2560x1440", "large landscape"),
    ("590x300", "small thumbnail"),
]


def parse_sizes(text):
    """'1920x1080, 1080x1080' -> [(1920,1080), (1080,1080)].  Numbers pick presets."""
    out = []
    for tok in re.split(r"[,;]+", str(text)):
        tok = tok.strip().lower()
        if not tok:
            continue
        if tok.isdigit() and 1 <= int(tok) <= len(SIZE_PRESETS):
            tok = SIZE_PRESETS[int(tok) - 1][0]
        m = re.match(r"^(\d{2,5})\s*[x×*]\s*(\d{2,5})$", tok)
        if not m:
            raise ValueError(tok)
        w, h = int(m.group(1)), int(m.group(2))
        if not (200 <= w <= 8000 and 200 <= h <= 8000):
            raise ValueError(tok)
        if (w, h) not in out:
            out.append((w, h))
    if not out:
        raise ValueError("empty")
    return out


def load_settings(path: Path) -> dict:
    """settings.txt:  key = value   (lines starting with # are notes).
    size_<scene> = 1600x1200  gives one scene its own size(s)."""
    out = {"scene_sizes": {}}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if line.startswith("#") or "=" not in line:
            continue
        line = re.split(r"\s#\s", line, maxsplit=1)[0]          # inline note:  value  # note
        k, v = [x.strip() for x in line.split("=", 1)]
        k = k.lower().replace(" ", "_")
        if k.startswith("size_"):
            sc = k[5:]
            if v and sc in scene_labels():
                try:
                    out["scene_sizes"][sc] = parse_sizes(v)
                except ValueError:
                    print(f"settings.txt: ignoring size for {sc}: '{v}'")
            continue
        spec = SETTING_KEYS.get(k)
        if spec is None or (v == "" and k not in TEXT_KEYS):
            continue
        dest, typ = (spec if isinstance(spec, tuple) else (k, spec))
        yes = v.lower() in ("yes", "y", "true", "on", "1")
        try:
            if typ == "neg":
                out[dest] = not yes
            elif typ is bool:
                out[dest] = yes
            else:
                out[dest] = typ(v)
        except ValueError:
            print(f"settings.txt: ignoring '{raw.strip()}'")
    return out


def ask(label, default, pattern):
    while True:
        try:
            v = input(f"{label} [{default}]: ").strip()
        except EOFError:
            return default
        if not v:
            return default
        if re.match(pattern, v, re.I):
            return v
        print("  That doesn't look right, try again (or press Enter to keep the default).")


def ask_size(default):
    print("\nMockup size:")
    for i, (s, note) in enumerate(SIZE_PRESETS, 1):
        print(f"  {i}) {s:<10} {note}")
    print("  Type a number, your own size (e.g. 2400x1600), or several separated by commas (e.g. 1,3 or 1920x1080,1080x1080)")
    while True:
        try:
            v = input(f"Size [{default}]: ").strip()
        except EOFError:
            v = ""
        try:
            return parse_sizes(v or default)
        except ValueError:
            print("  That doesn't look right. Example: 1920x1080  or  2  or  1,3")


def main():
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description="Screenshot websites and turn every page into device mockups.")
    ap.add_argument("urls", nargs="?", default=str(here / "urls.txt"), help="text file with one website per line (default: urls.txt)")
    ap.add_argument("--out", help="output folder (default: Desktop/Mockups)")
    ap.add_argument("--max-pages", type=int, default=60, help="max pages per website (default 60, 0 = all)")
    ap.add_argument("--no-crawl", action="store_true", help="only capture the exact links in the file")
    ap.add_argument("--scenes", default=DEFAULT_SCENES, help="comma list: " + ", ".join(scene_labels()) + f" (default {DEFAULT_SCENES})")
    ap.add_argument("--size", default="auto", help="auto = each style's own size, or your size: 2000x2000  or  2000x2000,1080x1080")
    ap.add_argument("--zoom", type=float, default=100, help="device size inside the image, percent (default 100)")
    ap.add_argument("--bg", default="auto", help="auto | brand | site | autodark | white | #hex | #hex,#hex (gradient)")
    ap.add_argument("--finish", default="black", choices=["black", "silver"], help="device color")
    ap.add_argument("--shadow", type=int, default=60, help="shadow strength 0-100")
    ap.add_argument("--pad", type=float, default=8, help="padding around devices, percent")
    ap.add_argument("--scroll", type=int, default=0, help="where the screens start, 0 = top of page, 100 = bottom")
    ap.add_argument("--no-glare", action="store_true", help="turn off the screen reflection")
    ap.add_argument("--format", default="jpg", choices=["jpg", "png", "webp"])
    ap.add_argument("--quality", type=int, default=92)
    ap.add_argument("--workers", type=int, default=2, help="pages captured at the same time (default 3)")
    ap.add_argument("--banner-left", default="{pages}", help="presentation banner, left text ({site}, {pages} allowed)")
    ap.add_argument("--banner-right", default="{site}", help="presentation banner, right text")
    ap.add_argument("--title-small", default="Fully editable", help="presentation small title")
    ap.add_argument("--title-big", default="Website template", help="presentation big title")
    ap.add_argument("--font-title", default=None, help="path to a .ttf for the big title")
    ap.add_argument("--keep-screenshots", action="store_true", default=True, help=argparse.SUPPRESS)
    ap.add_argument("--no-screenshots", dest="keep_screenshots", action="store_false", help="delete the raw screenshots afterwards")
    ap.add_argument("--images", nargs="+", help="make mockups from these screenshot files or folders instead of links")
    ap.add_argument("--shots-only", action="store_true", help="only save the website screenshots (every page), make no mockups")
    ap.add_argument("--shots-mobile", action="store_true", help="with --shots-only: also save phone screenshots")
    ap.add_argument("--pages-from", dest="page_source", choices=["menu", "all"], default="menu",
                    help="menu = only the pages in the website's menu (default), all = every page found")
    ap.add_argument("--shots-tablet", action="store_true", help="with --shots-only: also save tablet screenshots")
    ap.add_argument("--reuse", action="store_true", help="reuse screenshots already in the folder (fast re-styling)")
    ap.add_argument("--settings", default=str(here / "settings.txt"), help="settings file (default: settings.txt)")
    ap.add_argument("--ask", action="store_true", help="ask for size, device size and background before starting")
    pre, _ = ap.parse_known_args()
    ap.set_defaults(**{"scene_sizes": {}, **load_settings(Path(pre.settings))})
    opt = ap.parse_args()
    try:
        opt.sizes = None if str(opt.size).strip().lower() in ("auto", "") else parse_sizes(opt.size)
    except ValueError:
        sys.exit("Size must look like 1920x1080 (each side between 200 and 8000). Several: 1920x1080,1080x1080")
    if opt.ask:
        opt.sizes = ask_size(", ".join(f"{w}x{h}" for w, h in opt.sizes) if opt.sizes else "2000x2000")
        if opt.scene_sizes:
            print("  (settings.txt also gives own sizes to: " + ", ".join(opt.scene_sizes) + ")")
        opt.zoom = float(ask("Device size in %, 100 = normal, 120 = bigger, 85 = smaller", f"{opt.zoom:g}", r"^\d{2,3}(\.\d+)?$"))
        opt.bg = ask("Background (auto / brand / site / white / #hex)", opt.bg, r"^(auto|brand|site|autodark|white|#[0-9a-fA-F]{6}(,#[0-9a-fA-F]{6})?)$")
    opt.zoom = max(40.0, min(200.0, opt.zoom))
    if opt.images:
        run_images(opt)
        return
    if not Path(opt.urls).exists():
        sys.exit(f"Can't find {opt.urls}. Put your links in urls.txt next to this program.")
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(run(opt))


if __name__ == "__main__":
    main()
