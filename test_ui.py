#!/usr/bin/env python3
"""
test_ui.py — testy UI v reálném Chrome (Playwright, mobilní viewport).

Spuštění:  python3 test_ui.py
Vyžaduje: python playwright a /usr/bin/google-chrome. Soubory servíruje lokální
http server (aby fungoval localStorage jako na skutečném hostingu).
Screenshoty se ukládají do /tmp/shots.
"""
import json
import os
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

DIR = os.path.dirname(os.path.abspath(__file__))
PORT = 8765
URL = f"http://127.0.0.1:{PORT}/index.html"
SHOTS = "/tmp/shots"
CHROME = "/usr/bin/google-chrome"
os.makedirs(SHOTS, exist_ok=True)

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


READ_STATE = """() => [...document.querySelectorAll('.cell')].map(c => ({
  v: c.querySelector('.val').textContent,
  given: c.classList.contains('given'),
  sel: c.classList.contains('selected'),
  peer: c.classList.contains('peer'),
  same: c.classList.contains('same'),
  conflict: c.classList.contains('conflict'),
  hasNotes: c.classList.contains('has-notes'),
  notes: [...c.querySelectorAll('.notes span')].map(s => s.textContent).join(''),
}))"""

SOLVE = """() => {
  const g = [...document.querySelectorAll('.cell')].map(c =>
    c.classList.contains('given') ? parseInt(c.querySelector('.val').textContent, 10) : 0);
  return Array.from(Sudoku.solve(Int8Array.from(g)));
}"""

LAYOUT = """() => {
  const r = id => document.getElementById(id).getBoundingClientRect();
  const g = r('grid'), p = r('pad'), t = r('tools');
  const b = document.querySelector('#pad button').getBoundingClientRect();
  const tb = document.querySelector('#tools button').getBoundingClientRect();
  return { gridW: g.width, gridH: g.height, gridTop: g.top, padBottom: p.bottom,
           btnW: b.width, btnH: b.height, toolH: tb.height,
           docH: document.documentElement.scrollHeight, docW: document.documentElement.scrollWidth,
           innerH: innerHeight, innerW: innerWidth,
           fontPx: parseFloat(getComputedStyle(document.querySelector('.cell')).fontSize) };
}"""


def new_page(browser, w=390, h=844, scheme="light", init=None):
    ctx = browser.new_context(
        viewport={"width": w, "height": h},
        device_scale_factor=2,
        is_mobile=True,
        has_touch=True,
        color_scheme=scheme,
    )
    if init:
        ctx.add_init_script(init)
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append("pageerror: " + str(e)))
    page.on("console", lambda m: errors.append("console: " + m.text) if m.type == "error" else None)
    page.goto(URL)
    page.wait_for_selector(".cell")
    return ctx, page, errors


def state(page):
    return page.evaluate(READ_STATE)


def cell(page, i):
    return page.locator(f'.cell[data-i="{i}"]')


def pad(page, d):
    return page.locator(f'#pad button[data-d="{d}"]')


def empties(st):
    return [i for i, c in enumerate(st) if not c["given"]]


def peers_of(i):
    r, c = divmod(i, 9)
    s = set()
    for k in range(9):
        s.add(r * 9 + k)
        s.add(k * 9 + c)
    br, bc = r - r % 3, c - c % 3
    for dr in range(3):
        for dc in range(3):
            s.add((br + dr) * 9 + bc + dc)
    s.discard(i)
    return s


def fill_all(page, sol, wrong_at=None):
    """Vyplní všechna prázdná políčka správně; na `wrong_at` zadá špatnou číslici."""
    st = state(page)
    for i in empties(st):
        d = sol[i]
        if i == wrong_at:
            d = d % 9 + 1
        cell(page, i).click()
        pad(page, d).click()


def open_settings(page):
    page.click("#btn-settings")
    page.wait_for_selector("#dlg-settings:not([hidden])")


def set_range(page, value):
    page.evaluate(
        "v => { const r = document.getElementById('set-target'); r.value = v;"
        " r.dispatchEvent(new Event('input', {bubbles: true})); }",
        value,
    )


GAME_KEY = "sudoku.game.v1"


def givens_string(page):
    return "".join(c["v"] if c["given"] else "0" for c in state(page))


def saved(page):
    raw = page.evaluate(f"localStorage.getItem('{GAME_KEY}')")
    return None if raw is None else json.loads(raw)


def seed_and_reload(page, raw):
    page.evaluate(f"v => localStorage.setItem('{GAME_KEY}', v)", raw)
    page.reload()
    page.wait_for_selector(".cell")


def run_persistence_tests(browser):
    # ---------- 13. obnovení hry ----------
    section("13. Ukládání: obnovení rozehrané hry")
    ctx, page, errors = new_page(browser)
    st = state(page)
    es = empties(st)
    puzzle_before = givens_string(page)
    cell(page, es[0]).click()
    pad(page, 5).click()
    cell(page, es[1]).click()
    pad(page, 7).click()
    page.click("#btn-notes")
    cell(page, es[2]).click()
    pad(page, 1).click()
    pad(page, 3).click()
    snap_before = state(page)
    info_before = page.inner_text("#info")
    check("uložení existuje po tahu", saved(page) is not None)
    page.reload()
    page.wait_for_selector(".cell")
    snap_after = state(page)
    check("po reloadu je stejné zadání", givens_string(page) == puzzle_before)
    check("po reloadu jsou stejné hodnoty, poznámky i výběr", snap_after == snap_before)
    check("po reloadu je zapnutý režim poznámek", page.get_attribute("#btn-notes", "aria-pressed") == "true")
    check("po reloadu je stejný text o počtu čísel", page.inner_text("#info") == info_before)
    check("po reloadu je Zpět zapnuté", page.locator("#btn-undo").is_enabled())
    for _ in range(4):
        page.click("#btn-undo")
    s = state(page)
    check("Zpět po reloadu vrátí všechny 4 tahy",
          all(c["v"] == "" or c["given"] for c in s) and not any(c["hasNotes"] for c in s))
    check("po vrácení všech tahů je Zpět vypnuté", page.locator("#btn-undo").is_disabled())
    check("hra je po vrácení tahů pořád stejná", givens_string(page) == puzzle_before)

    cell(page, es[0]).click()
    page.click("#btn-notes")  # vypnout režim poznámek
    pad(page, 2).click()
    page.reload()
    page.wait_for_selector(".cell")
    page.click("#btn-new")
    check("po reloadu se s rozehranou hrou ptá na novou hru", page.locator("#dlg-new").is_visible())
    page.click("#dlg-new-cancel")
    check("žádné chyby v konzoli", errors == [], errors)
    ctx.close()

    # ---------- 14. vyřešená hra, nová hra ----------
    section("14. Ukládání: vyřešená hra a nová hra")
    ctx, page, errors = new_page(browser)
    sol = page.evaluate(SOLVE)
    puzzle_before = givens_string(page)
    fill_all(page, sol)
    check("po výhře je dialog vidět", page.locator("#dlg-win").is_visible())
    check("vyřešená hra se z úložiště odstraní", saved(page) is None)
    page.reload()
    page.wait_for_selector(".cell")
    check("po reloadu vyřešené hry začíná nová hra", givens_string(page) != puzzle_before)
    check("po reloadu vyřešené hry není dialog výhry", page.locator("#dlg-win").is_hidden())
    check("po reloadu vyřešené hry je mřížka bez zapsaných čísel",
          all(c["v"] == "" or c["given"] for c in state(page)))
    ctx.close()

    ctx, page, errors = new_page(browser)
    e = empties(state(page))[0]
    cell(page, e).click()
    pad(page, 4).click()
    page.click("#btn-new")
    page.click("#dlg-new-ok")
    newer = givens_string(page)
    page.reload()
    page.wait_for_selector(".cell")
    check("nová hra přepíše uloženou hru", givens_string(page) == newer)
    check("nová hra nemá zbytky historie", page.locator("#btn-undo").is_disabled())
    check("žádné chyby v konzoli", errors == [], errors)
    ctx.close()

    # ---------- 15. poškozená uložení ----------
    section("15. Ukládání: poškozená a podvržená uložení")
    ctx, page, errors = new_page(browser)
    st = state(page)
    es = empties(st)
    cell(page, es[0]).click()
    pad(page, 5).click()
    cell(page, es[1]).click()
    pad(page, 8).click()
    base_raw = page.evaluate(f"localStorage.getItem('{GAME_KEY}')")
    base = json.loads(base_raw)
    base_puzzle = givens_string(page)
    ctx.close()

    given_idx = next(i for i, c in enumerate(st) if c["given"])
    # druhé zadané políčko musí mít v řešení JINOU číslici, jinak by prohození nic nezměnilo
    other_given = next(i for i, c in enumerate(st)
                       if c["given"] and base["solution"][i] != base["solution"][given_idx])
    swap_a = es[0]
    swap_b = next(i for i in es if base["solution"][i] != base["solution"][swap_a])

    def mutate(fn):
        o = json.loads(base_raw)
        fn(o)
        return json.dumps(o)

    def swap(s, i, j):
        l = list(s)
        l[i], l[j] = l[j], l[i]
        return "".join(l)

    def set_at(s, i, ch):
        return s[:i] + ch + s[i + 1:]

    rejected_cases = [
        ("prázdný řetězec", ""),
        ("nesmyslný JSON", "tohle neni json"),
        ("pole místo objektu", "[]"),
        ("null", "null"),
        ("jiná verze", mutate(lambda o: o.update(v=2))),
        ("zadání je příliš krátké", mutate(lambda o: o.update(puzzle=o["puzzle"][:80]))),
        ("hodnoty obsahují písmeno", mutate(lambda o: o.update(values=set_at(o["values"], es[0], "x")))),
        ("hodnota zadaného políčka je změněná", mutate(lambda o: o.update(values=set_at(o["values"], given_idx, "0")))),
        ("řešení není platná mřížka", mutate(lambda o: o.update(solution=swap(o["solution"], swap_a, swap_b)))),
        ("řešení nesedí se zadáním", mutate(lambda o: o.update(solution=swap(o["solution"], given_idx, other_given)))),
        ("zadání není jednoznačné", mutate(lambda o: o.update(puzzle=set_at(o["puzzle"], given_idx, "0")))),
        ("poznámky mimo rozsah", mutate(lambda o: o.update(notes=set_at(o["notes"], 0, "f") + o["notes"][1:]))),
        ("poznámky mají špatnou délku", mutate(lambda o: o.update(notes=o["notes"][:-1]))),
        ("hra je už vyřešená", mutate(lambda o: o.update(values=o["solution"]))),
    ]
    for name, raw in rejected_cases:
        ctx, page, errors = new_page(browser)
        seed_and_reload(page, raw)
        new_puzzle = givens_string(page)
        s = saved(page)
        ok_new = new_puzzle != base_puzzle and len(state(page)) == 81
        check(f"{name}: začne nová hra", ok_new)
        check(f"{name}: nová hra je zapsaná platně", s is not None and s.get("v") == 1)
        check(f"{name}: bez chyb v konzoli", errors == [], errors)
        ctx.close()

    kept_cases = [
        ("historie má špatnou délku", mutate(lambda o: o.update(history=["abc"])), False),
        ("historie není pole znaků", mutate(lambda o: o.update(history=[123])), False),
        ("historie mění zadané políčko",
         mutate(lambda o: o.update(history=[set_at(o["puzzle"], given_idx, "0" if o["puzzle"][given_idx] != "0" else "1") + "0" * 243])), False),
        ("výběr mimo mřížku", mutate(lambda o: o.update(selected=999)), True),
        ("výběr není číslo", mutate(lambda o: o.update(selected="a")), True),
    ]
    for name, raw, history_ok in kept_cases:
        ctx, page, errors = new_page(browser)
        seed_and_reload(page, raw)
        check(f"{name}: hra se zachová", givens_string(page) == base_puzzle)
        s = state(page)
        check(f"{name}: zapsané tahy zůstanou",
              s[es[0]]["v"] == "5" and s[es[1]]["v"] == "8")
        if "historie" in name:
            check(f"{name}: historie se zahodí", page.locator("#btn-undo").is_disabled())
        else:
            check(f"{name}: žádné políčko není vybrané", not any(c["sel"] for c in s))
            check(f"{name}: historie zůstane", page.locator("#btn-undo").is_enabled())
        check(f"{name}: bez chyb v konzoli", errors == [], errors)
        ctx.close()

    ctx, page, errors = new_page(browser)
    nraw = mutate(lambda o: o.update(notes=o["notes"][:es[0] * 3] + "1ff" + o["notes"][es[0] * 3 + 3:]))
    seed_and_reload(page, nraw)
    s = state(page)
    check("poznámky u vyplněného políčka se vyčistí", not s[es[0]]["hasNotes"] and s[es[0]]["v"] == "5")
    check("bez chyb v konzoli", errors == [], errors)
    ctx.close()

    # ---------- 16. nedostupné úložiště ----------
    section("16. Ukládání: nedostupné nebo plné úložiště")
    for name, js in [
        ("zápis vyhazuje chybu (plné úložiště)",
         "Storage.prototype.setItem = function () { throw new DOMException('quota', 'QuotaExceededError'); };"),
        ("čtení vyhazuje chybu (blokované úložiště)",
         "Storage.prototype.getItem = function () { throw new DOMException('blocked', 'SecurityError'); };"),
        ("zápis i čtení vyhazují chybu",
         "Storage.prototype.setItem = function () { throw new Error('x'); };"
         "Storage.prototype.getItem = function () { throw new Error('x'); };"
         "Storage.prototype.removeItem = function () { throw new Error('x'); };"),
    ]:
        ctx, page, errors = new_page(browser, init=js)
        st = state(page)
        e = empties(st)[0]
        cell(page, e).click()
        pad(page, 6).click()
        check(f"{name}: hra běží a zapisuje čísla", state(page)[e]["v"] == "6")
        page.click("#btn-undo")
        check(f"{name}: Zpět funguje", state(page)[e]["v"] == "")
        open_settings(page)
        page.check("#set-conflicts")
        page.click("#dlg-settings-close")
        check(f"{name}: nastavení funguje", page.is_visible("#btn-new"))
        check(f"{name}: bez chyb v konzoli", errors == [], errors)
        ctx.close()

    # ---------- 17. velká historie ----------
    section("17. Ukládání: rychlost a velikost při dlouhé historii (strop 500 kroků)")
    ctx, page, errors = new_page(browser)
    st = state(page)
    e = empties(st)[0]
    cell(page, e).click()
    N = 1000  # víc tahů, než kolik historie pojme: ověří se i ořezávání
    ms = page.evaluate(
        """n => { const t0 = performance.now();
          for (let k = 0; k < n; k++)
            document.dispatchEvent(new KeyboardEvent('keydown', { key: String(1 + (k % 9)) }));
          return performance.now() - t0; }""",
        N,
    )
    s = saved(page)
    size_kb = len(json.dumps(s)) / 1024
    per_move = ms / N
    print(f"  {N} tahů: celkem {ms:.0f} ms, {per_move:.2f} ms na tah (vykreslení + uložení), uložení má {size_kb:.0f} KB")
    check("historie je ořezaná na 500 kroků", len(s["history"]) == 500, len(s["history"]))
    check("uložení má méně než 250 KB", size_kb < 250, size_kb)
    check("průměrný tah trvá méně než 5 ms (Chrome na tomto stroji)", per_move < 5, per_move)
    page.evaluate("() => { for (let k = 0; k < 15; k++) document.dispatchEvent(new KeyboardEvent('keydown', { key: String(1 + ((k + 4) % 9)) })); }")
    check("po dalších tazích zůstane historie na 500", len(saved(page)["history"]) == 500)
    page.reload()
    page.wait_for_selector(".cell")
    page.evaluate("() => { const b = document.getElementById('btn-undo'); for (let k = 0; k < 600; k++) b.click(); }")
    check("po reloadu jde vrátit všech 500 kroků a ne víc", page.locator("#btn-undo").is_disabled())
    check("po vrácení historie je hra v platném stavu (81 políček)", len(state(page)) == 81)
    check("bez chyb v konzoli", errors == [], errors)
    ctx.close()


def main():
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"],
        cwd=DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(0.8)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=CHROME, headless=True, args=["--no-sandbox"])
            run_tests(browser)
            browser.close()
    finally:
        server.terminate()

    print("\n" + ("VŠE V POŘÁDKU" if not fails else "SELHÁNÍ: " + str(len(fails))) + f" (úspěšných kontrol: {passes})")
    sys.exit(0 if not fails else 1)


def run_tests(browser):
    # ---------- 1. načtení ----------
    section("1. Načtení")
    ctx, page, errors = new_page(browser)
    st = state(page)
    givens = sum(1 for c in st if c["given"])
    info = page.inner_text("#info")
    check("81 políček", len(st) == 81)
    check("9 tlačítek číslic", page.locator("#pad button").count() == 9)
    check("info odpovídá počtu zadaných čísel", info == f"{givens} zadaných čísel", info)
    check("výchozí režim: 21–28 čísel", 21 <= givens <= 28, givens)
    check("zadaná čísla jsou vyplněna, ostatní prázdná",
          all((c["v"] != "") == c["given"] for c in st))
    check("Zpět je na začátku vypnuté", page.locator("#btn-undo").is_disabled())
    check("žádné chyby v konzoli", errors == [], errors)
    ctx.close()

    # ---------- 2. zadání čísla, zpět ----------
    section("2. Zadávání, zpět, mazání")
    ctx, page, errors = new_page(browser)
    st = state(page)
    given_i = next(i for i, c in enumerate(st) if c["given"])
    before = st[given_i]["v"]
    cell(page, given_i).tap()
    pad(page, 5 if before != "5" else 6).tap()
    check("do zadaného políčka nejde zapsat", state(page)[given_i]["v"] == before)
    check("zapsání do zadaného nevytvoří krok zpět", page.locator("#btn-undo").is_disabled())

    e = empties(st)[0]
    cell(page, e).tap()
    pad(page, 7).tap()
    s2 = state(page)
    check("číslo se zapíše do prázdného políčka", s2[e]["v"] == "7")
    check("zapsané číslo není označené jako zadané", not s2[e]["given"])
    check("Zpět je po tahu zapnuté", page.locator("#btn-undo").is_enabled())
    page.click("#btn-undo")
    check("Zpět vrátí prázdné políčko", state(page)[e]["v"] == "")
    check("Zpět je po vrácení vypnuté", page.locator("#btn-undo").is_disabled())

    cell(page, e).click()
    pad(page, 3).click()
    pad(page, 4).click()
    check("přepsání jiným číslem", state(page)[e]["v"] == "4")
    page.click("#btn-erase")
    check("Smazat vymaže číslo", state(page)[e]["v"] == "")
    page.click("#btn-undo")
    check("Zpět po smazání vrátí číslo", state(page)[e]["v"] == "4")
    page.click("#btn-undo")
    page.click("#btn-undo")
    check("Zpět přes celou historii vrátí prázdné políčko", state(page)[e]["v"] == "")
    check("žádné chyby v konzoli", errors == [], errors)
    ctx.close()

    # ---------- 3. poznámky ----------
    section("3. Poznámky")
    ctx, page, errors = new_page(browser)
    st = state(page)
    es = empties(st)
    a = es[0]
    b = next(i for i in es if i != a and i in peers_of(a))
    page.click("#btn-notes")
    check("režim poznámek je zapnutý", page.get_attribute("#btn-notes", "aria-pressed") == "true")
    cell(page, b).click()
    for d in (2, 5, 9):
        pad(page, d).click()
    sb = state(page)[b]
    check("poznámky 2, 5 a 9 se zobrazí", sb["hasNotes"] and sb["notes"] == "259", sb)
    check("poznámky nejsou hodnota políčka", sb["v"] == "")
    pad(page, 5).click()
    check("opětovné zadání poznámky ji vypne", state(page)[b]["notes"] == "29", state(page)[b])

    # a: normální režim; číslo 9 je v poznámkách souseda b -> musí z něj zmizet
    page.click("#btn-notes")
    check("režim poznámek se vypne", page.get_attribute("#btn-notes", "aria-pressed") == "false")
    cell(page, a).click()
    pad(page, 9).click()
    sa = state(page)
    check("zapsané číslo odebere stejnou poznámku u sousedů", sa[b]["notes"] == "2", sa[b])
    page.click("#btn-undo")
    check("Zpět vrátí odebranou poznámku u souseda", state(page)[b]["notes"] == "29", state(page)[b])

    # poznámky v políčku s hodnotou se neukládají
    cell(page, a).click()
    pad(page, 1).click()
    page.click("#btn-notes")
    pad(page, 6).click()
    check("v režimu poznámek se do políčka s hodnotou nic nepřidá",
          state(page)[a]["v"] == "1" and state(page)[a]["notes"].strip() == "")
    page.click("#btn-notes")

    # Smazat u políčka jen s poznámkami
    cell(page, b).click()
    page.click("#btn-erase")
    check("Smazat odstraní poznámky", state(page)[b]["notes"].strip() == "" and not state(page)[b]["hasNotes"])
    check("žádné chyby v konzoli", errors == [], errors)
    ctx.close()

    # ---------- 4. zvýraznění ----------
    section("4. Zvýraznění")
    ctx, page, errors = new_page(browser)
    st = state(page)
    e = empties(st)[10]
    cell(page, e).click()
    s = state(page)
    check("vybrané je právě jedno políčko", sum(c["sel"] for c in s) == 1 and s[e]["sel"])
    check("zvýrazněno je 20 sousedů", sum(c["peer"] for c in s) == 20, sum(c["peer"] for c in s))
    v = next(c["v"] for i, c in enumerate(s) if c["given"] and i != e)
    gi = next(i for i, c in enumerate(s) if c["given"] and c["v"] == v)
    cell(page, gi).click()
    s = state(page)
    same = [i for i, c in enumerate(s) if c["same"]]
    expected = [i for i, c in enumerate(s) if c["v"] == v and i != gi]
    check("zvýrazněna jsou stejná čísla", same == expected, (same, expected))
    ctx.close()

    # ---------- 5. konflikty ----------
    section("5. Konflikty")
    ctx, page, errors = new_page(browser)
    st = state(page)
    # najdi prázdné políčko a číslici, která už je zadaná v jeho sousedství
    target = None
    for i in empties(st):
        for j in peers_of(i):
            if st[j]["given"]:
                target = (i, j, st[j]["v"])
                break
        if target:
            break
    i, j, d = target
    cell(page, i).click()
    pad(page, int(d)).click()
    s = state(page)
    check("konflikty jsou ve výchozím nastavení vypnuté", not any(c["conflict"] for c in s))
    open_settings(page)
    page.check("#set-conflicts")
    page.click("#dlg-settings-close")
    s = state(page)
    check("po zapnutí je konfliktní zadané číslo označeno", s[i]["conflict"])
    check("zadané číslo (z předlohy) se neoznačuje", not s[j]["conflict"])
    stored = json.loads(page.evaluate("localStorage.getItem('sudoku.settings.v1')"))
    check("přepínač se uložil do localStorage", stored["showConflicts"] is True, stored)
    page.click("#btn-undo")
    check("po vrácení tahu konflikt zmizí", not any(c["conflict"] for c in state(page)))
    # dva konfliktní zápisy navzájem
    cell(page, i).click()
    pad(page, int(d)).click()
    check("konflikt se znovu zobrazí", state(page)[i]["conflict"])
    check("žádné chyby v konzoli", errors == [], errors)
    ctx.close()

    # ---------- 6. dokončení hry ----------
    section("6. Dokončení hry")
    ctx, page, errors = new_page(browser)
    sol = page.evaluate(SOLVE)
    st = state(page)
    first_puzzle = "".join(c["v"] or "0" for c in st)
    es = empties(st)
    wrong_cell = es[-1]
    fill_all(page, sol, wrong_at=wrong_cell)
    check("vyplněná mřížka s chybou nespustí dialog výhry", page.locator("#dlg-win").is_hidden())
    check("zobrazí se hláška o chybě", "obsahuje chybu" in page.inner_text("#status"), page.inner_text("#status"))
    cell(page, wrong_cell).click()
    pad(page, sol[wrong_cell]).click()
    check("po opravě se zobrazí dialog výhry", page.locator("#dlg-win").is_visible())
    check("hláška o chybě zmizí", page.inner_text("#status") == "")
    page.click("#dlg-win-ok")
    s2 = state(page)
    second_puzzle = "".join(c["v"] or "0" for c in s2)
    check("po výhře začne nová hra", page.locator("#dlg-win").is_hidden() and second_puzzle != first_puzzle)
    check("v nové hře jsou jen zadaná čísla", all((c["v"] != "") == c["given"] for c in s2))
    check("žádné chyby v konzoli", errors == [], errors)
    ctx.close()

    # ---------- 7. nová hra ----------
    section("7. Nová hra")
    ctx, page, errors = new_page(browser)
    st = state(page)
    before = "".join(c["v"] or "0" for c in st)
    page.click("#btn-new")
    s = state(page)
    check("bez rozehrané hry se nová hra spustí bez dotazu", page.locator("#dlg-new").is_hidden())
    check("bez rozehrané hry vznikne jiné zadání", "".join(c["v"] or "0" for c in s) != before)
    e = empties(s)[0]
    cell(page, e).click()
    pad(page, 8).click()
    mid = "".join(c["v"] or "0" for c in state(page))
    page.click("#btn-new")
    check("s rozehranou hrou se zobrazí potvrzení", page.locator("#dlg-new").is_visible())
    page.click("#dlg-new-cancel")
    check("Zrušit ponechá rozehranou hru", page.locator("#dlg-new").is_hidden() and
          "".join(c["v"] or "0" for c in state(page)) == mid)
    page.click("#btn-new")
    page.click("#dlg-new-ok")
    after = "".join(c["v"] or "0" for c in state(page))
    check("potvrzení spustí novou hru", page.locator("#dlg-new").is_hidden() and after != mid)
    page.click("#btn-new")
    check("po spuštění nové hry už se neptá", page.locator("#dlg-new").is_hidden())
    check("žádné chyby v konzoli", errors == [], errors)
    ctx.close()

    # ---------- 8. nastavení počtu čísel ----------
    section("8. Nastavení počtu čísel")
    ctx, page, errors = new_page(browser)
    open_settings(page)
    check("posuvník je bez omezení vypnutý", page.locator("#set-target").is_disabled())
    check("posuvník má rozsah 24–60",
          page.get_attribute("#set-target", "min") == "24" and page.get_attribute("#set-target", "max") == "60")
    page.check("#set-limit")
    check("posuvník se po zapnutí odemkne", page.locator("#set-target").is_enabled())
    set_range(page, "40")
    check("hodnota se zobrazí", page.inner_text("#set-target-out") == "40")
    page.click("#dlg-settings-close")
    page.click("#btn-new")
    check("nová hra má přesně 40 čísel", page.inner_text("#info") == "40 zadaných čísel", page.inner_text("#info"))
    check("opravdu 40 zadaných políček", sum(c["given"] for c in state(page)) == 40)
    stored = json.loads(page.evaluate("localStorage.getItem('sudoku.settings.v1')"))
    check("nastavení se uložilo", stored == {"limitClues": True, "targetClues": 40, "showConflicts": False}, stored)

    # nejnižší dostupná hodnota, opakovaně
    set_range(page, "24")
    page.evaluate("document.getElementById('dlg-settings').hidden = false")
    ok = True
    for _ in range(15):
        page.evaluate("document.getElementById('btn-new').click()")
        if page.inner_text("#info") != "24 zadaných čísel":
            ok = False
    check("cíl 24 se splní ve 15 hrách z 15", ok, page.inner_text("#info"))

    # po obnovení stránky nastavení zůstane
    page.reload()
    page.wait_for_selector(".cell")
    open_settings(page)
    check("po obnovení zůstane omezení zapnuté", page.is_checked("#set-limit"))
    check("po obnovení zůstane hodnota 24", page.input_value("#set-target") == "24")
    page.uncheck("#set-limit")
    page.click("#dlg-settings-close")
    page.click("#btn-new")
    n = int(page.inner_text("#info").split()[0])
    check("po vypnutí omezení se opět generuje minimální zadání", 21 <= n <= 28, n)
    check("žádné chyby v konzoli", errors == [], errors)
    ctx.close()

    # ---------- 9. neplatná uložená nastavení ----------
    section("9. Neplatná uložená nastavení")
    cases = [
        ("nesmyslný JSON", "localStorage.setItem('sudoku.settings.v1', 'not json')", False, 30, False),
        ("špatné typy", "localStorage.setItem('sudoku.settings.v1', JSON.stringify({limitClues:'yes',targetClues:'x',showConflicts:1}))", False, 30, False),
        ("cíl pod minimem", "localStorage.setItem('sudoku.settings.v1', JSON.stringify({limitClues:true,targetClues:5,showConflicts:true}))", True, 24, True),
        ("cíl nad maximem", "localStorage.setItem('sudoku.settings.v1', JSON.stringify({limitClues:true,targetClues:1000,showConflicts:false}))", True, 60, False),
        ("pole místo objektu", "localStorage.setItem('sudoku.settings.v1', '[1,2,3]')", False, 30, False),
    ]
    for name, js, lim, tgt, conf in cases:
        ctx, page, errors = new_page(browser, init=js)
        open_settings(page)
        ok = (page.is_checked("#set-limit") == lim and page.input_value("#set-target") == str(tgt)
              and page.is_checked("#set-conflicts") == conf)
        check(f"{name}: ošetřeno", ok, (page.is_checked("#set-limit"), page.input_value("#set-target"), page.is_checked("#set-conflicts")))
        check(f"{name}: bez chyb v konzoli", errors == [], errors)
        ctx.close()

    # ---------- 10. klávesnice ----------
    section("10. Klávesnice")
    ctx, page, errors = new_page(browser)
    st = state(page)
    e = empties(st)[0]
    cell(page, e).click()
    page.keyboard.press("6")
    check("klávesa 6 zapíše číslo", state(page)[e]["v"] == "6")
    page.keyboard.press("Backspace")
    check("Backspace maže", state(page)[e]["v"] == "")
    page.keyboard.press("n")
    check("klávesa n přepne poznámky", page.get_attribute("#btn-notes", "aria-pressed") == "true")
    page.keyboard.press("4")
    check("v režimu poznámek klávesa přidá poznámku", "4" in state(page)[e]["notes"])
    page.keyboard.press("n")
    page.keyboard.press("Control+z")
    check("Ctrl+Z vrátí tah", state(page)[e]["notes"].strip() == "")
    cell(page, 40).click()
    page.keyboard.press("ArrowRight")
    check("šipka doprava posune výběr", state(page)[41]["sel"])
    page.keyboard.press("ArrowUp")
    check("šipka nahoru posune výběr", state(page)[32]["sel"])
    cell(page, 0).click()
    page.keyboard.press("ArrowLeft")
    page.keyboard.press("ArrowUp")
    check("výběr nevyjede z mřížky", state(page)[0]["sel"])
    open_settings(page)
    page.keyboard.press("5")
    check("při otevřeném dialogu klávesy nic nezapisují",
          all(c["v"] == "" or c["given"] for c in state(page)))
    page.keyboard.press("Escape")
    check("Escape zavře nastavení", page.locator("#dlg-settings").is_hidden())
    check("žádné chyby v konzoli", errors == [], errors)
    ctx.close()

    # ---------- 11. rozložení ----------
    section("11. Rozložení na různých displejích (reálné rozměry v Chrome)")
    print("  viewport   | mřížka | buňka | číslice WxH | nástroje H | scroll  | pad.dole")
    for name, w, h in [
        ("iPhone 15/16", 393, 852), ("iPhone 14 Pro Max", 430, 932), ("iPhone 13 mini", 375, 812),
        ("iPhone SE 2/3", 375, 667), ("iPhone SE 1", 320, 568), ("Jelly Star", 480, 854),
    ]:
        ctx, page, errors = new_page(browser, w, h)
        L = page.evaluate(LAYOUT)
        scroll_ok = L["docH"] <= L["innerH"] + 1 and L["docW"] <= L["innerW"]
        print(f"  {name:<18} {w}x{h} | {L['gridW']:6.1f} | {L['gridW']/9:5.1f} | {L['btnW']:5.1f}x{L['btnH']:.0f}   | {L['toolH']:5.0f}      | {'ne ' if scroll_ok else 'ANO'}     | {L['padBottom']:.0f}/{L['innerH']}")
        check(f"{name}: mřížka je čtvercová", abs(L["gridW"] - L["gridH"]) < 1, L)
        check(f"{name}: nic nepřetéká přes displej", scroll_ok, L)
        check(f"{name}: spodní okraj číslic je na displeji", L["padBottom"] <= L["innerH"], L)
        check(f"{name}: ovládání je u spodního okraje (do 20 px)", L["padBottom"] >= L["innerH"] - 20, L)
        check(f"{name}: tlačítka číslic mají výšku >= 44", L["btnH"] >= 44, L)
        check(f"{name}: tlačítka číslic jsou široká >= 28", L["btnW"] >= 28, L["btnW"])
        ctx.close()

    # ---------- 12. screenshoty ----------
    section("12. Screenshoty (/tmp/shots)")
    for scheme in ("light", "dark"):
        ctx, page, errors = new_page(browser, 393, 852, scheme=scheme)
        st = state(page)
        es = empties(st)
        # rozehraná hra: pár čísel, poznámky, výběr, jeden konflikt
        open_settings(page)
        page.check("#set-conflicts")
        page.click("#dlg-settings-close")
        for k, d in zip(es[:6], (3, 7, 1, 9, 2, 5)):
            cell(page, k).click()
            pad(page, d).click()
        page.click("#btn-notes")
        for k in es[10:13]:
            cell(page, k).click()
            for d in (1, 4, 6, 8):
                pad(page, d).click()
        page.click("#btn-notes")
        cell(page, es[20]).click()
        page.screenshot(path=f"{SHOTS}/game_{scheme}.png")
        if scheme == "light":
            open_settings(page)
            page.screenshot(path=f"{SHOTS}/settings_{scheme}.png")
        ctx.close()
    ctx, page, errors = new_page(browser, 320, 568)
    cell(page, empties(state(page))[0]).click()
    page.screenshot(path=f"{SHOTS}/small_320x568.png")
    ctx.close()
    check("screenshoty vytvořeny", all(os.path.exists(f"{SHOTS}/{n}") for n in
          ("game_light.png", "game_dark.png", "settings_light.png", "small_320x568.png")))

    run_persistence_tests(browser)


if __name__ == "__main__":
    main()
