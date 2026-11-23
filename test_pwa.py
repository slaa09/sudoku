#!/usr/bin/env python3
"""
test_pwa.py — testy PWA vrstvy (manifest, ikony, service worker, offline, aktualizace).

Aplikace se zkopíruje do PODADRESÁŘE (/sudoku-app/), aby se ověřily relativní
cesty tak, jak poběží na GitHub Pages. Offline test se dělá opravdově: server se
vypne. Kopie se pak upravuje, aby se otestovalo, jak se projeví aktualizace.

Spuštění:  python3 test_pwa.py
"""
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

SRC = os.path.dirname(os.path.abspath(__file__))
ROOT = "/tmp/pwa-root"
APP = os.path.join(ROOT, "sudoku-app")
PORT = 8767
BASE = f"http://127.0.0.1:{PORT}/sudoku-app/"
CHROME = "/usr/bin/google-chrome"

DEPLOY_FILES = [
    "index.html", "style.css", "app.js", "sudoku.js", "sw.js", "manifest.webmanifest",
    "icons/icon.svg", "icons/icon-192.png", "icons/icon-512.png", "icons/icon-maskable-512.png",
    "icons/apple-touch-icon.png", "icons/favicon-32.png",
]

fails = []
passes = 0


def check(name, cond, detail=""):
    global passes
    if cond:
        passes += 1
    else:
        fails.append(name)
        print("  FAIL: " + name + (" — " + str(detail) if detail else ""))


def section(t):
    print("\n" + t)


def deploy():
    shutil.rmtree(ROOT, ignore_errors=True)
    for f in DEPLOY_FILES:
        dst = os.path.join(APP, f)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy(os.path.join(SRC, f), dst)


class Server:
    def __init__(self):
        self.p = None

    def start(self):
        self.p = subprocess.Popen(
            [sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(50):
            try:
                urllib.request.urlopen(BASE + "index.html", timeout=0.5).read()
                return
            except Exception:
                time.sleep(0.1)
        raise RuntimeError("server nenastartoval")

    def stop(self):
        if self.p:
            self.p.terminate()
            self.p.wait()
            self.p = None


def http(path):
    r = urllib.request.urlopen(BASE + path, timeout=3)
    return r.status, r.headers.get("Content-Type", ""), r.read()


def png_size(data):
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


def new_page(browser, errors, w=393, h=852, scheme="light", init=None):
    ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=2,
                              is_mobile=True, has_touch=True, color_scheme=scheme)
    if init:
        ctx.add_init_script(init)
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append("pageerror: " + str(e)))
    page.on("console", lambda m: errors.append("console: " + m.text) if m.type == "error" else None)
    return ctx, page


CACHES_JS = """async () => {
  const out = {};
  for (const n of await caches.keys()) {
    const c = await caches.open(n);
    out[n] = (await c.keys()).map(r => new URL(r.url).pathname);
  }
  return out;
}"""

READY_JS = """async () => {
  const reg = await navigator.serviceWorker.ready;
  return { scope: reg.scope, state: reg.active && reg.active.state };
}"""


def wait_controlled(page, timeout=5000):
    page.wait_for_function("!!navigator.serviceWorker.controller", timeout=timeout)


def wait_activated(page, timeout=5000):
    page.wait_for_function(
        "navigator.serviceWorker.getRegistration().then(r => !!r && !!r.active && r.active.state === 'activated')",
        timeout=timeout,
    )


def bump_mtime(path):
    """http.server posílá čas změny s přesností na sekundu; bez posunu by prohlížeč dostal 304."""
    t = time.time() + 10
    os.utime(path, (t, t))


def sw_asset_list():
    src = open(os.path.join(SRC, "sw.js"), encoding="utf-8").read()
    block = re.search(r"const ASSETS = \[(.*?)\];", src, re.S).group(1)
    return re.findall(r"'([^']+)'", block)


def main():
    deploy()
    server = Server()
    server.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=CHROME, headless=True, args=["--no-sandbox"])
            run(browser, server)
            browser.close()
    finally:
        server.stop()
    print("\n" + ("VŠE V POŘÁDKU" if not fails else "SELHÁNÍ: " + str(len(fails))) + f" (úspěšných kontrol: {passes})")
    sys.exit(0 if not fails else 1)


def run(browser, server):
    # ---------- 1. manifest, ikony, hlavička ----------
    section("1. Manifest, ikony, hlavička")
    st, ctype, body = http("manifest.webmanifest")
    m = json.loads(body)
    check("manifest se načte", st == 200)
    for key in ("name", "short_name", "start_url", "scope", "display", "icons", "background_color", "theme_color"):
        check(f"manifest má '{key}'", key in m)
    check("display je standalone", m.get("display") == "standalone")
    check("start_url a scope jsou relativní", m.get("start_url") == "./" and m.get("scope") == "./")
    purposes = {(i["sizes"], i.get("purpose", "any")) for i in m["icons"]}
    check("ikony 192 any, 512 any a 512 maskable jsou deklarovány",
          {("192x192", "any"), ("512x512", "any"), ("512x512", "maskable")} <= purposes, purposes)
    for icon in m["icons"]:
        stt, ct, data = http(icon["src"])
        w, h = png_size(data)
        check(f"ikona {icon['src']} existuje a je PNG", stt == 200 and "image/png" in ct, ct)
        check(f"ikona {icon['src']} má deklarovanou velikost {icon['sizes']}", f"{w}x{h}" == icon["sizes"], f"{w}x{h}")

    html = http("index.html")[2].decode("utf-8")
    check("hlavička odkazuje na manifest", 'rel="manifest" href="manifest.webmanifest"' in html)
    check("hlavička má apple-touch-icon", 'rel="apple-touch-icon" href="icons/apple-touch-icon.png"' in html)
    check("hlavička má režim standalone pro iOS", 'name="apple-mobile-web-app-capable" content="yes"' in html)
    check("hlavička má theme-color pro světlý i tmavý režim",
          html.count('name="theme-color"') == 2 and "prefers-color-scheme: dark" in html)
    for link in re.findall(r'(?:href|src)="([^"#]+)"', html):
        if link.startswith(("http", "data:")):
            continue
        try:
            stt = http(link)[0]
        except Exception as e:
            stt = str(e)
        check(f"odkaz z index.html '{link}' existuje", stt == 200, stt)
    check("žádná absolutní cesta (začínající /) v HTML, manifestu a sw.js",
          not re.search(r'(?:href|src)="/', html)
          and not re.search(r'"(?:src|start_url|scope)":\s*"/', json.dumps(m))
          and "'/" not in open(os.path.join(SRC, "sw.js"), encoding="utf-8").read().split("const ASSETS")[1].split("];")[0])

    assets = sw_asset_list()
    check("všechny soubory ze seznamu v sw.js existují",
          all(http(a if a != "./" else "")[0] == 200 for a in assets), assets)

    # ---------- 2. instalovatelnost a service worker ----------
    section("2. Instalovatelnost a service worker")
    errors = []
    ctx, page = new_page(browser, errors)
    page.goto(BASE)
    page.wait_for_selector(".cell")
    page.evaluate(READY_JS)
    wait_activated(page)
    info = page.evaluate(READY_JS)
    check("service worker je aktivní", info["state"] == "activated", info)
    check("scope odpovídá podadresáři", info["scope"] == BASE, info["scope"])
    wait_controlled(page)
    caches_now = page.evaluate(CACHES_JS)
    check("existuje právě jeden cache 'sudoku-v1'", list(caches_now.keys()) == ["sudoku-v1"], list(caches_now.keys()))
    cached_paths = set(caches_now.get("sudoku-v1", []))
    expected = {"/sudoku-app/" + (a if a != "./" else "") for a in assets}
    check("v cache jsou všechny soubory aplikace", expected <= cached_paths, expected - cached_paths)

    cdp = ctx.new_cdp_session(page)
    man = cdp.send("Page.getAppManifest")
    check("Chrome načetl manifest bez chyb", man.get("errors") == [], man.get("errors"))
    inst = cdp.send("Page.getInstallabilityErrors")
    # 'in-incognito' pochází z testovacího prohlížeče (anonymní kontext), ne z aplikace
    blockers = [e for e in inst.get("installabilityErrors", []) if e.get("errorId") != "in-incognito"]
    check("Chrome nehlásí žádné překážky instalace (kromě anonymního kontextu testu)", blockers == [], blockers)
    check("žádné chyby v konzoli", errors == [], errors)
    ctx.close()

    # ---------- 3. offline (server se opravdu vypne) ----------
    section("3. Offline start (server vypnutý)")
    errors = []
    ctx, page = new_page(browser, errors)
    page.goto(BASE)
    page.wait_for_selector(".cell")
    page.evaluate(READY_JS)
    page.reload()
    wait_controlled(page)
    cells = page.evaluate("[...document.querySelectorAll('.cell')].map(c => c.classList.contains('given'))")
    e = cells.index(False)
    page.locator(f'.cell[data-i="{e}"]').click()
    page.locator('#pad button[data-d="6"]').click()
    before = page.evaluate("[...document.querySelectorAll('.val')].map(v => v.textContent).join('')")

    server.stop()
    try:
        urllib.request.urlopen(BASE + "index.html", timeout=0.5)
        check("server je opravdu vypnutý", False)
    except Exception:
        check("server je opravdu vypnutý", True)

    page.reload()
    page.wait_for_selector(".cell")
    after = page.evaluate("[...document.querySelectorAll('.val')].map(v => v.textContent).join('')")
    check("offline: aplikace se načte (81 políček)", page.locator(".cell").count() == 81)
    check("offline: rozehraná hra se obnoví", after == before)
    page.locator(f'.cell[data-i="{e}"]').click()
    page.locator('#pad button[data-d="2"]').click()
    check("offline: hra jde dál hrát", page.locator(f'.cell[data-i="{e}"] .val').inner_text() == "2")
    page.click("#btn-settings")
    check("offline: nastavení se otevře", page.locator("#dlg-settings").is_visible())
    page.click("#dlg-settings-close")
    page.evaluate("document.getElementById('btn-new').click()")
    page.evaluate("document.getElementById('dlg-new-ok').click()")
    check("offline: nová hra funguje", page.locator(".cell").count() == 81 and
          page.evaluate("[...document.querySelectorAll('.cell.given')].length") >= 21)

    page.goto(BASE + "?utm=1")
    page.wait_for_selector(".cell")
    check("offline: adresa s parametrem se také načte z cache", page.locator(".cell").count() == 81)
    page.goto(BASE + "index.html")
    page.wait_for_selector(".cell")
    check("offline: adresa index.html se načte z cache", page.locator(".cell").count() == 81)
    rejected = page.evaluate("fetch('neexistuje.txt').then(() => false, () => true)")
    check("offline: nekešovaný soubor selže čistě (bez zásahu do aplikace)", rejected is True)
    check("offline: žádné chyby v konzoli (kromě očekávaného selhání nekešovaného souboru)",
          all("neexistuje.txt" in x or "Failed to load resource" in x or "ERR_" in x for x in errors), errors)
    ctx.close()
    server.start()

    # ---------- 4. aktualizace ----------
    section("4. Aktualizace nasazené verze")
    deploy()
    errors = []
    ctx, page = new_page(browser, errors)
    page.goto(BASE)
    page.wait_for_selector(".cell")
    page.evaluate(READY_JS)
    wait_controlled(page)
    check("výchozí nadpis je 'Sudoku'", page.inner_text("h1") == "Sudoku")

    idx = os.path.join(APP, "index.html")
    txt = open(idx, encoding="utf-8").read()
    open(idx, "w", encoding="utf-8").write(txt.replace("<h1>Sudoku</h1>", "<h1>Sudoku NOVÉ</h1>"))
    bump_mtime(idx)

    page.reload()
    page.wait_for_selector(".cell")
    check("1. spuštění po nasazení: ještě stará verze (rychlé, z cache)", page.inner_text("h1") == "Sudoku", page.inner_text("h1"))
    time.sleep(1.0)  # aktualizace na pozadí
    page.reload()
    page.wait_for_selector(".cell")
    check("2. spuštění po nasazení: nová verze", page.inner_text("h1") == "Sudoku NOVÉ", page.inner_text("h1"))

    # úprava nového souboru: nahrazení JS; hra a nastavení nesmí zmizet
    page.evaluate("document.querySelectorAll('.cell:not(.given)')[0].click()")
    page.locator('#pad button[data-d="9"]').click()
    mine = page.evaluate("[...document.querySelectorAll('.val')].map(v => v.textContent).join('')")

    sw = os.path.join(APP, "sw.js")
    s = open(sw, encoding="utf-8").read()
    open(sw, "w", encoding="utf-8").write(s.replace("const VERSION = 'v1';", "const VERSION = 'v2';"))
    bump_mtime(sw)
    page.goto(BASE)  # navigace spustí kontrolu sw.js
    page.wait_for_selector(".cell")
    # Chrome kontroluje sw.js po navigaci se zpožděním (v testu ~3 s) a aktivace trvá další ~1–2 s
    deadline = time.time() + 20
    names = []
    while time.time() < deadline:
        names = sorted(page.evaluate(CACHES_JS).keys())
        if names == ["sudoku-v2"]:
            break
        time.sleep(0.2)
    check("po změně VERSION se starý cache smaže a vznikne nový", names == ["sudoku-v2"], names)
    c2 = page.evaluate(CACHES_JS).get("sudoku-v2", [])
    check("nový cache obsahuje všechny soubory", {"/sudoku-app/" + (a if a != "./" else "") for a in assets} <= set(c2))
    page.reload()
    page.wait_for_selector(".cell")
    after = page.evaluate("[...document.querySelectorAll('.val')].map(v => v.textContent).join('')")
    check("rozehraná hra přežije aktualizaci service workeru", after == mine)
    check("žádné chyby v konzoli", errors == [], errors)
    ctx.close()

    # ---------- 5. bez service workeru ----------
    section("5. Prostředí bez service workeru (nezabezpečený původ, soukromé okno)")
    deploy()
    errors = []
    ctx, page = new_page(browser, errors,
                         init="Object.defineProperty(Navigator.prototype, 'serviceWorker', { get: () => undefined });")
    page.goto(BASE)
    page.wait_for_selector(".cell")
    check("aplikace funguje i bez service workeru", page.locator(".cell").count() == 81)
    check("žádné chyby v konzoli", errors == [], errors)
    ctx.close()

    # ---------- 6. tmavý režim a stránka v 'standalone' ----------
    section("6. Vzhled: tmavý režim a standalone")
    errors = []
    ctx, page = new_page(browser, errors, scheme="dark")
    page.goto(BASE)
    page.wait_for_selector(".cell")
    bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
    check("tmavý režim má tmavé pozadí", bg == "rgb(16, 16, 20)", bg)
    tc = page.evaluate("""() => [...document.querySelectorAll('meta[name=theme-color]')]
        .map(m => [m.media, m.content])""")
    check("theme-color má variantu pro tmavý režim", ["(prefers-color-scheme: dark)", "#101014"] in tc, tc)
    check("žádné chyby v konzoli", errors == [], errors)
    ctx.close()

    # standalone: v Chrome se dá emulovat display-mode přes CDP? Ověří se alespoň, že layout je stejný
    errors = []
    ctx, page = new_page(browser, errors)
    page.goto(BASE)
    page.wait_for_selector(".cell")
    page.emulate_media(media="screen")
    L = page.evaluate("""() => { const g = document.getElementById('grid').getBoundingClientRect();
        const p = document.getElementById('pad').getBoundingClientRect();
        return {gw: g.width, gh: g.height, padBottom: p.bottom, h: innerHeight,
                scrollH: document.documentElement.scrollHeight}; }""")
    check("rozložení po PWA úpravách: čtvercová mřížka a žádné přetékání",
          abs(L["gw"] - L["gh"]) < 1 and L["scrollH"] <= L["h"] + 1, L)
    ctx.close()


if __name__ == "__main__":
    main()
