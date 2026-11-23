/*
 * test.js — testy jádra (sudoku.js). Bez závislostí: node test.js
 *
 * Jednoznačnost se ověřuje NEZÁVISLÝM solverem (refCount) napsaným jinak než
 * ten v sudoku.js: kandidáti se počítají skenováním řádku/sloupce/čtverce,
 * bez bitových masek a bez sdíleného kódu.
 *
 * Velikosti běhu lze měnit proměnnými prostředí:
 *   N_DEFAULT (výchozí 1000)  počet zadání v defaultním režimu
 *   N_MINIMAL (výchozí 200)   z toho počet zadání ověřovaných na minimalitu
 *   N_TARGET  (výchozí 100)   počet zadání pro každý cílový počet čísel
 */
'use strict';

const Sudoku = require('./sudoku.js');

const N_DEFAULT = parseInt(process.env.N_DEFAULT || '1000', 10);
const N_MINIMAL = parseInt(process.env.N_MINIMAL || '200', 10);
const N_TARGET = parseInt(process.env.N_TARGET || '100', 10);

// ---------- nezávislý referenční solver ----------

function refCandidates(g, i) {
  const used = new Array(10).fill(false);
  const r = Math.floor(i / 9);
  const c = i % 9;
  for (let k = 0; k < 9; k++) {
    used[g[r * 9 + k]] = true;
    used[g[k * 9 + c]] = true;
  }
  const br = r - (r % 3);
  const bc = c - (c % 3);
  for (let dr = 0; dr < 3; dr++) {
    for (let dc = 0; dc < 3; dc++) used[g[(br + dr) * 9 + bc + dc]] = true;
  }
  const out = [];
  for (let d = 1; d <= 9; d++) if (!used[d]) out.push(d);
  return out;
}

function refCount(grid, limit) {
  const g = Array.from(grid);
  // vstupní konzistence: každé zadané číslo musí být kandidátem při vyprázdněném políčku
  for (let i = 0; i < 81; i++) {
    if (g[i] === 0) continue;
    const v = g[i];
    g[i] = 0;
    const ok = refCandidates(g, i).includes(v);
    g[i] = v;
    if (!ok) return 0;
  }
  let count = 0;
  function rec() {
    let best = -1;
    let bestC = null;
    for (let i = 0; i < 81; i++) {
      if (g[i] !== 0) continue;
      const cs = refCandidates(g, i);
      if (cs.length === 0) return;
      if (bestC === null || cs.length < bestC.length) {
        best = i;
        bestC = cs;
        if (cs.length === 1) break;
      }
    }
    if (best === -1) {
      count++;
      return;
    }
    for (const d of bestC) {
      g[best] = d;
      rec();
      g[best] = 0;
      if (count >= limit) return;
    }
  }
  rec();
  return count;
}

// ---------- pomocné funkce ----------

function isValidFull(g) {
  if (g.length !== 81) return false;
  const full = 0x3fe; // bity 1..9
  for (let k = 0; k < 9; k++) {
    let row = 0;
    let col = 0;
    let box = 0;
    for (let j = 0; j < 9; j++) {
      const a = g[k * 9 + j];
      const b = g[j * 9 + k];
      const br = Math.floor(k / 3) * 3 + Math.floor(j / 3);
      const bc = (k % 3) * 3 + (j % 3);
      const c = g[br * 9 + bc];
      if (a < 1 || a > 9 || b < 1 || b > 9 || c < 1 || c > 9) return false;
      row |= 1 << a;
      col |= 1 << b;
      box |= 1 << c;
    }
    if (row !== full || col !== full || box !== full) return false;
  }
  return true;
}

function parse(s) {
  return Int8Array.from(s.split('').map((ch) => (ch === '.' ? 0 : parseInt(ch, 10))));
}

function countClues(g) {
  let n = 0;
  for (let i = 0; i < 81; i++) if (g[i] !== 0) n++;
  return n;
}

function pct(sorted, p) {
  return sorted[Math.min(sorted.length - 1, Math.floor((p / 100) * sorted.length))];
}

// ---------- minimální testovací rámec ----------

let failures = 0;
let passes = 0;

function check(name, cond, detail) {
  if (cond) {
    passes++;
  } else {
    failures++;
    console.log('  FAIL: ' + name + (detail ? ' — ' + detail : ''));
  }
}

function section(title) {
  console.log('\n' + title);
}

function throwsErr(fn) {
  try {
    fn();
  } catch (e) {
    return true;
  }
  return false;
}

// ---------- 1. solver: okrajové případy ----------

section('1. Solver: okrajové případy');
{
  check('prázdná mřížka má >= 2 řešení (limit 2)', Sudoku.countSolutions(new Int8Array(81), 2) === 2);
  check('limit se respektuje (limit 5 na prázdné mřížce)', Sudoku.countSolutions(new Int8Array(81), 5) === 5);

  const wiki = parse(
    '53..7....6..195....98....6.8...6...34..8.3..17...2...6.6....28....419..5....8..79'
  );
  const wikiSol = '534678912672195348198342567859761423426853791713924856961537284287419635345286179';
  check('známé zadání: 1 řešení (solver)', Sudoku.countSolutions(wiki, 2) === 1);
  check('známé zadání: 1 řešení (referenční solver)', refCount(wiki, 2) === 1);
  const s = Sudoku.solve(wiki);
  check('známé zadání: solve() vrací očekávané řešení', s !== null && Array.from(s).join('') === wikiSol);

  const full = Sudoku.solve(wiki);
  check('plná mřížka má právě 1 řešení', Sudoku.countSolutions(full, 2) === 1);

  const dup = new Int8Array(81);
  dup[0] = 5;
  dup[1] = 5;
  check('duplicita v řádku: 0 řešení (solver)', Sudoku.countSolutions(dup, 2) === 0);
  check('duplicita v řádku: 0 řešení (referenční)', refCount(dup, 2) === 0);

  // políčko (0,8) nemá kandidáta: řádek 1..8, ve sloupci 8 je 9 — žádná duplicita, ale 0 řešení
  const dead = new Int8Array(81);
  for (let i = 0; i < 8; i++) dead[i] = i + 1;
  dead[17] = 9;
  check('bez řešení bez zjevné duplicity: 0 (solver)', Sudoku.countSolutions(dead, 2) === 0);
  check('bez řešení bez zjevné duplicity: 0 (referenční)', refCount(dead, 2) === 0);
  check('solve() na neřešitelném zadání vrací null', Sudoku.solve(dead) === null);

  check('vstup: špatná délka vyhodí chybu', throwsErr(() => Sudoku.countSolutions(new Int8Array(80))));
  const bad = new Int8Array(81);
  bad[3] = 10;
  check('vstup: hodnota 10 vyhodí chybu', throwsErr(() => Sudoku.countSolutions(bad)));
  const neg = new Int8Array(81);
  neg[3] = -1;
  check('vstup: hodnota -1 vyhodí chybu', throwsErr(() => Sudoku.countSolutions(neg)));

  const orig = Int8Array.from(wiki);
  Sudoku.countSolutions(wiki, 2);
  Sudoku.solve(wiki);
  check('solver nemění vstupní pole', Array.from(wiki).join('') === Array.from(orig).join(''));
}

// ---------- 2. generátor plných mřížek ----------

section('2. Generátor plných mřížek');
{
  const seen = new Set();
  let allValid = true;
  for (let i = 0; i < 200; i++) {
    const g = Sudoku.generateFull();
    if (!isValidFull(g)) allValid = false;
    seen.add(Array.from(g).join(''));
  }
  check('200 plných mřížek je platných', allValid);
  check('mřížky se liší (>= 199 různých ze 200)', seen.size >= 199, 'různých: ' + seen.size);
}

// ---------- 3. defaultní režim: jednoznačnost, minimalita, rychlost ----------

section('3. Defaultní režim (bez cílového počtu čísel): ' + N_DEFAULT + ' zadání');
const times = [];
const clueHist = {};
{
  let subsetOk = 0;
  let uniqueOk = 0;
  let solValid = 0;
  let minimalChecked = 0;
  let minimalOk = 0;
  let engineAgree = 0;
  let engineChecked = 0;

  for (let n = 0; n < N_DEFAULT; n++) {
    const t0 = process.hrtime.bigint();
    const res = Sudoku.generate();
    const ms = Number(process.hrtime.bigint() - t0) / 1e6;
    times.push(ms);

    const { puzzle, solution, clues } = res;
    clueHist[clues] = (clueHist[clues] || 0) + 1;

    let subset = true;
    for (let i = 0; i < 81; i++) if (puzzle[i] !== 0 && puzzle[i] !== solution[i]) subset = false;
    if (subset) subsetOk++;
    if (isValidFull(solution)) solValid++;
    if (countClues(puzzle) === clues) engineAgree++;
    engineChecked++;

    // nezávislé ověření jednoznačnosti + že jediné řešení je to vrácené
    if (refCount(puzzle, 2) === 1) uniqueOk++;

    if (n < N_MINIMAL) {
      // minimalita: odebráním kteréhokoli čísla vzniknou >= 2 řešení (nezávislý solver)
      let allNeeded = true;
      for (let i = 0; i < 81; i++) {
        if (puzzle[i] === 0) continue;
        const v = puzzle[i];
        puzzle[i] = 0;
        if (refCount(puzzle, 2) < 2) allNeeded = false;
        puzzle[i] = v;
      }
      minimalChecked++;
      if (allNeeded) minimalOk++;
    }
  }

  check('čísla zadání jsou podmnožinou řešení', subsetOk === N_DEFAULT, subsetOk + '/' + N_DEFAULT);
  check('vrácené řešení je platná plná mřížka', solValid === N_DEFAULT, solValid + '/' + N_DEFAULT);
  check('pole `clues` odpovídá skutečnému počtu čísel', engineAgree === engineChecked);
  check('jednoznačné řešení (nezávislý solver)', uniqueOk === N_DEFAULT, uniqueOk + '/' + N_DEFAULT);
  check('zadání je minimální (žádné číslo nejde odebrat)', minimalOk === minimalChecked, minimalOk + '/' + minimalChecked);
  console.log('  jednoznačnost ověřena u ' + uniqueOk + '/' + N_DEFAULT + ', minimalita u ' + minimalOk + '/' + minimalChecked);
}

// ---------- 4. křížová kontrola obou solverů na nejednoznačných zadáních ----------

section('4. Křížová kontrola solverů (nejednoznačná zadání)');
{
  let agree = 0;
  const trials = 300;
  for (let n = 0; n < trials; n++) {
    const { puzzle } = Sudoku.generate();
    const extra = 1 + (n % 3); // odeber 1–3 další čísla -> víc řešení
    for (let k = 0; k < extra; k++) {
      const filled = [];
      for (let i = 0; i < 81; i++) if (puzzle[i] !== 0) filled.push(i);
      puzzle[filled[Math.floor(Math.random() * filled.length)]] = 0;
    }
    if (Sudoku.countSolutions(puzzle, 10) === refCount(puzzle, 10)) agree++;
  }
  check('oba solvery dávají stejný počet řešení (limit 10)', agree === trials, agree + '/' + trials);
}

// ---------- 5. cílový počet čísel ----------

section('5. Cílový počet čísel: ' + N_TARGET + ' zadání na cíl');
{
  const reachable = [60, 50, 40, 35, 30];
  for (const target of reachable) {
    let exact = 0;
    let unique = 0;
    let reached = 0;
    for (let n = 0; n < N_TARGET; n++) {
      const r = Sudoku.generate({ targetClues: target });
      if (r.clues === target) exact++;
      if (r.reachedTarget === true) reached++;
      if (refCount(r.puzzle, 2) === 1) unique++;
    }
    check('cíl ' + target + ': přesně ' + target + ' čísel', exact === N_TARGET, exact + '/' + N_TARGET);
    check('cíl ' + target + ': reachedTarget === true', reached === N_TARGET);
    check('cíl ' + target + ': jednoznačné řešení', unique === N_TARGET, unique + '/' + N_TARGET);
  }

  console.log('\n  Dosažitelnost nízkých cílů (výchozí maxAttempts = 20):');
  console.log('  cíl | splněn | jednoznačné | průměr čísel | medián času [ms]');
  const lowTargets = [28, 27, 26, 25, 24, 23, 22, 17];
  for (const target of lowTargets) {
    let reached = 0;
    let unique = 0;
    let sum = 0;
    const tt = [];
    for (let n = 0; n < N_TARGET; n++) {
      const t0 = process.hrtime.bigint();
      const r = Sudoku.generate({ targetClues: target });
      tt.push(Number(process.hrtime.bigint() - t0) / 1e6);
      if (r.reachedTarget) reached++;
      if (refCount(r.puzzle, 2) === 1) unique++;
      sum += r.clues;
    }
    tt.sort((a, b) => a - b);
    check('nízký cíl ' + target + ': vždy jednoznačné řešení', unique === N_TARGET, unique + '/' + N_TARGET);
    console.log(
      '  ' + String(target).padStart(3) + ' | ' + String(reached + '/' + N_TARGET).padStart(7) +
      ' | ' + String(unique + '/' + N_TARGET).padStart(11) +
      ' | ' + (sum / N_TARGET).toFixed(2).padStart(12) +
      ' | ' + pct(tt, 50).toFixed(1).padStart(10)
    );
  }

  check('cíl 16 vyhodí chybu', throwsErr(() => Sudoku.generate({ targetClues: 16 })));
  check('cíl 82 vyhodí chybu', throwsErr(() => Sudoku.generate({ targetClues: 82 })));
  check('cíl 30.5 vyhodí chybu', throwsErr(() => Sudoku.generate({ targetClues: 30.5 })));
  check('cíl "30" (řetězec) vyhodí chybu', throwsErr(() => Sudoku.generate({ targetClues: '30' })));
}

// ---------- 6. determinismus se seedem ----------

section('6. Determinismus se seedem');
{
  const a = Sudoku.generate({ seed: 12345 });
  const b = Sudoku.generate({ seed: 12345 });
  const c = Sudoku.generate({ seed: 54321 });
  check('stejný seed -> stejné zadání', Array.from(a.puzzle).join('') === Array.from(b.puzzle).join(''));
  check('stejný seed -> stejné řešení', Array.from(a.solution).join('') === Array.from(b.solution).join(''));
  check('jiný seed -> jiné zadání', Array.from(a.puzzle).join('') !== Array.from(c.puzzle).join(''));
  const t1 = Sudoku.generate({ seed: 7, targetClues: 35 });
  const t2 = Sudoku.generate({ seed: 7, targetClues: 35 });
  check('stejný seed i s cílem -> stejné zadání', Array.from(t1.puzzle).join('') === Array.from(t2.puzzle).join(''));
}

// ---------- souhrn ----------

section('Rychlost generování (defaultní režim, Node na tomto stroji)');
{
  times.sort((a, b) => a - b);
  const mean = times.reduce((s, x) => s + x, 0) / times.length;
  console.log(
    '  n=' + times.length +
    '  medián ' + pct(times, 50).toFixed(1) + ' ms' +
    '  průměr ' + mean.toFixed(1) + ' ms' +
    '  p95 ' + pct(times, 95).toFixed(1) + ' ms' +
    '  p99 ' + pct(times, 99).toFixed(1) + ' ms' +
    '  max ' + times[times.length - 1].toFixed(1) + ' ms'
  );
  console.log('\n  Rozdělení počtu čísel v zadání (defaultní režim):');
  const keys = Object.keys(clueHist).map(Number).sort((a, b) => a - b);
  let total = 0;
  let wsum = 0;
  for (const k of keys) {
    total += clueHist[k];
    wsum += k * clueHist[k];
  }
  for (const k of keys) {
    const share = (100 * clueHist[k]) / total;
    console.log('  ' + String(k).padStart(2) + ' čísel: ' + String(clueHist[k]).padStart(5) + '  ' + share.toFixed(1).padStart(5) + ' %  ' + '#'.repeat(Math.round(share)));
  }
  console.log('  průměr: ' + (wsum / total).toFixed(2) + ', min ' + keys[0] + ', max ' + keys[keys.length - 1]);
}

console.log('\n' + (failures === 0 ? 'VŠE V POŘÁDKU' : 'SELHÁNÍ: ' + failures) + ' (úspěšných kontrol: ' + passes + ')');
process.exit(failures === 0 ? 0 : 1);
