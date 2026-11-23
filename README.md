# Sudoku

Jednoduché sudoku bez reklam, které běží v prohlížeči a po přidání na plochu iPhonu funguje jako aplikace, i offline.

## Co umí

- Generuje zadání s **jednoznačným řešením**. Výchozí režim odebírá čísla, dokud to jde (typicky 22–27 čísel), takže zadání bývají náročná. Obtížnost se nehodnotí.
- V nastavení lze zvolit **cílový počet čísel** (24–60). Víc čísel obvykle znamená snazší zadání.
- Poznámky, Zpět, mazání, volitelné označování konfliktů, světlý i tmavý režim.
- Rozehraná hra se ukládá do zařízení a po otevření se obnoví.

## Instalace na iPhone

1. Otevři adresu aplikace v Safari.
2. Sdílet → **Přidat na plochu**.
3. Hraj z ikony na ploše. Rozehraná hra se ukládá jen v aplikaci z plochy, ne v kartě Safari.

Nová verze se po nasazení projeví až při **druhém** spuštění aplikace (první spuštění ukáže starou verzi a novou stáhne na pozadí).

## Vývoj

Bez build kroku, bez závislostí. Soubory se servírují staticky.

| Soubor | Účel |
|---|---|
| `sudoku.js` | solver a generátor (běží v Node i v prohlížeči) |
| `app.js`, `index.html`, `style.css` | rozhraní |
| `sw.js`, `manifest.webmanifest`, `icons/` | PWA (offline, instalace) |
| `test.js` | testy jádra: `node test.js` |
| `test_ui.py`, `test_pwa.py` | testy v Chrome (Playwright): `python3 test_ui.py`, `python3 test_pwa.py` |
| `tools/make_icons.py` | vyrenderuje `icons/icon.svg` do PNG |

Testy v Pythonu vyžadují `playwright` a Google Chrome (cesta je v horní části souborů).

## Licence

Zatím žádná. Bez licence platí výchozí autorská práva.
