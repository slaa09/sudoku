/*
 * sudoku.js — solver a generátor zadání s jednoznačným řešením.
 *
 * Bez závislostí; běží v Node i v prohlížeči (včetně Web Workeru).
 * Mřížka je pole 81 čísel (0 = prázdné políčko), řazené po řádcích.
 *
 * API:
 *   Sudoku.countSolutions(grid, limit = 2) -> počet řešení (max. `limit`), 0 pro nekonzistentní zadání
 *   Sudoku.solve(grid)                     -> první nalezené řešení (Int8Array) nebo null
 *   Sudoku.generateFull(rng?)              -> plná platná mřížka (Int8Array)
 *   Sudoku.generate({ targetClues, seed, maxAttempts })
 *        -> { puzzle, solution, clues, reachedTarget }
 *
 * Výchozí režim (targetClues = null): čísla se odebírají, dokud to jde, tedy
 * výsledek je minimální zadání (odebráním libovolného čísla by přestalo mít
 * jednoznačné řešení).
 *
 * Režim s cílovým počtem čísel: odebírání se zastaví, jakmile zbývá
 * `targetClues` čísel. Pokud je cíl nižší, než kolik se z dané mřížky dá
 * dosáhnout, zkusí se až `maxAttempts` nových mřížek a vrátí se zadání
 * s nejmenším počtem čísel. `reachedTarget` říká, jestli se cíl povedlo
 * splnit (clues <= targetClues).
 */
(function (root) {
  'use strict';

  const ALL = 0x1ff; // bity 0..8 = číslice 1..9

  // počet nastavených bitů pro 9bitovou masku
  const POP = new Uint8Array(512);
  for (let i = 1; i < 512; i++) POP[i] = POP[i >> 1] + (i & 1);

  // řádek, sloupec a čtverec pro každé políčko
  const ROW = new Uint8Array(81);
  const COL = new Uint8Array(81);
  const BOX = new Uint8Array(81);
  for (let i = 0; i < 81; i++) {
    ROW[i] = (i / 9) | 0;
    COL[i] = i % 9;
    BOX[i] = (((i / 27) | 0) * 3) + (((i % 9) / 3) | 0);
  }

  // ---------- náhodná čísla ----------

  function mulberry32(seed) {
    let a = seed >>> 0;
    return function () {
      a = (a + 0x6d2b79f5) >>> 0;
      let t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function makeRng(seed) {
    return seed === null || seed === undefined ? Math.random : mulberry32(seed);
  }

  function shuffle(arr, rng) {
    for (let i = arr.length - 1; i > 0; i--) {
      const j = Math.floor(rng() * (i + 1));
      const t = arr[i];
      arr[i] = arr[j];
      arr[j] = t;
    }
    return arr;
  }

  // ---------- jádro: backtracking s heuristikou nejméně kandidátů ----------

  function checkGrid(grid) {
    if (!grid || grid.length !== 81) {
      throw new Error('Mřížka musí mít 81 prvků.');
    }
    for (let i = 0; i < 81; i++) {
      const v = grid[i];
      if (!Number.isInteger(v) || v < 0 || v > 9) {
        throw new Error('Neplatná hodnota na pozici ' + i + ': ' + v);
      }
    }
  }

  /*
   * Hledá řešení, dokud jich nenajde `limit`. Pokud je dán `rng`, zkouší číslice
   * v náhodném pořadí (používá se pro generování plných mřížek). Vrací
   * { count, solution } kde solution je první nalezené řešení.
   */
  function engine(grid, limit, rng) {
    checkGrid(grid);
    const g = Int8Array.from(grid);
    const rows = new Uint16Array(9);
    const cols = new Uint16Array(9);
    const boxes = new Uint16Array(9);

    for (let i = 0; i < 81; i++) {
      const v = g[i];
      if (v === 0) continue;
      const bit = 1 << (v - 1);
      if ((rows[ROW[i]] & bit) || (cols[COL[i]] & bit) || (boxes[BOX[i]] & bit)) {
        return { count: 0, solution: null }; // zadání porušuje pravidla
      }
      rows[ROW[i]] |= bit;
      cols[COL[i]] |= bit;
      boxes[BOX[i]] |= bit;
    }

    let count = 0;
    let solution = null;

    function search() {
      // najdi prázdné políčko s nejméně kandidáty
      let best = -1;
      let bestMask = 0;
      let bestN = 10;
      for (let i = 0; i < 81; i++) {
        if (g[i] !== 0) continue;
        const mask = ALL & ~(rows[ROW[i]] | cols[COL[i]] | boxes[BOX[i]]);
        const n = POP[mask];
        if (n === 0) return; // slepá ulička
        if (n < bestN) {
          best = i;
          bestMask = mask;
          bestN = n;
          if (n === 1) break;
        }
      }

      if (best === -1) {
        count++;
        if (solution === null) solution = Int8Array.from(g);
        return;
      }

      const r = ROW[best];
      const c = COL[best];
      const b = BOX[best];

      let digits = [];
      for (let d = 0; d < 9; d++) if (bestMask & (1 << d)) digits.push(d);
      if (rng) shuffle(digits, rng);

      for (let k = 0; k < digits.length; k++) {
        const d = digits[k];
        const bit = 1 << d;
        g[best] = d + 1;
        rows[r] |= bit;
        cols[c] |= bit;
        boxes[b] |= bit;
        search();
        rows[r] &= ~bit;
        cols[c] &= ~bit;
        boxes[b] &= ~bit;
        g[best] = 0;
        if (count >= limit) return;
      }
    }

    search();
    return { count, solution };
  }

  function countSolutions(grid, limit) {
    return engine(grid, limit === undefined ? 2 : limit, null).count;
  }

  function solve(grid) {
    return engine(grid, 1, null).solution;
  }

  function generateFull(rng) {
    const r = engine(new Int8Array(81), 1, rng || Math.random);
    return r.solution;
  }

  // ---------- generátor zadání ----------

  function carve(solution, targetClues, rng) {
    const puzzle = Int8Array.from(solution);
    let clues = 81;
    const order = [];
    for (let i = 0; i < 81; i++) order.push(i);
    shuffle(order, rng);

    for (let k = 0; k < order.length; k++) {
      if (targetClues !== null && clues <= targetClues) break;
      const i = order[k];
      const v = puzzle[i];
      puzzle[i] = 0;
      if (engine(puzzle, 2, null).count === 1) {
        clues--;
      } else {
        puzzle[i] = v; // odebráním by zadání ztratilo jednoznačnost
      }
    }
    // Poznámka: stačí jediný průchod. Číslo, které nešlo odebrat teď, nepůjde
    // odebrat ani později (méně čísel = víc řešení), takže výsledek bez cíle je minimální.
    return { puzzle, clues };
  }

  function generate(opts) {
    const o = opts || {};
    const targetClues = o.targetClues === undefined ? null : o.targetClues;
    const maxAttempts = o.maxAttempts === undefined ? 20 : o.maxAttempts;
    const rng = makeRng(o.seed);

    if (targetClues !== null) {
      if (!Number.isInteger(targetClues) || targetClues < 17 || targetClues > 81) {
        throw new Error('targetClues musí být celé číslo 17–81 nebo null.');
      }
    }

    const attempts = targetClues === null ? 1 : Math.max(1, maxAttempts);
    let best = null;
    for (let a = 0; a < attempts; a++) {
      const solution = generateFull(rng);
      const res = carve(solution, targetClues, rng);
      if (best === null || res.clues < best.clues) {
        best = { puzzle: res.puzzle, solution, clues: res.clues };
      }
      if (targetClues === null || best.clues <= targetClues) break;
    }

    return {
      puzzle: best.puzzle,
      solution: best.solution,
      clues: best.clues,
      reachedTarget: targetClues === null ? null : best.clues <= targetClues,
    };
  }

  const api = { countSolutions, solve, generateFull, generate };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  } else {
    root.Sudoku = api;
  }
})(typeof self !== 'undefined' ? self : this);
