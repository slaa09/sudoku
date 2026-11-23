/*
 * app.js — uživatelské rozhraní sudoku. Využívá globální objekt Sudoku ze sudoku.js.
 * Stav hry je v jednom objektu `game`; po každé změně se ukládá do localStorage
 * (viz „ukládání rozehrané hry“) a při startu se přísně validuje.
 */
(function () {
  'use strict';

  // ---------- nastavení ----------

  const SETTINGS_KEY = 'sudoku.settings.v1';
  const MIN_TARGET = 24; // pod 24 čísel generátor cíl spolehlivě nesplní
  const MAX_TARGET = 60;
  const DEFAULT_SETTINGS = { limitClues: false, targetClues: 30, showConflicts: false };

  function loadSettings() {
    const s = Object.assign({}, DEFAULT_SETTINGS);
    try {
      const raw = localStorage.getItem(SETTINGS_KEY);
      if (!raw) return s;
      const p = JSON.parse(raw);
      if (p && typeof p === 'object') {
        if (typeof p.limitClues === 'boolean') s.limitClues = p.limitClues;
        if (typeof p.showConflicts === 'boolean') s.showConflicts = p.showConflicts;
        if (Number.isInteger(p.targetClues)) {
          s.targetClues = Math.min(MAX_TARGET, Math.max(MIN_TARGET, p.targetClues));
        }
      }
    } catch (e) {
      /* poškozená nebo nedostupná data: použijí se výchozí hodnoty */
    }
    return s;
  }

  function saveSettings() {
    try {
      localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
    } catch (e) {
      /* úložiště nemusí být dostupné; nastavení pak platí jen do zavření */
    }
  }

  let settings = loadSettings();

  // ---------- ukládání rozehrané hry ----------
  //
  // Stav se po každé změně zapíše do localStorage v kompaktní podobě (řetězce
  // místo polí). Jeden krok historie je řetězec o 324 znacích: 81 číslic hodnot
  // + 81 × 3 hex znaky poznámek. Při načtení se vše přísně ověřuje; cokoli
  // nesedí, se zahodí a začne nová hra.

  const GAME_KEY = 'sudoku.game.v1';
  const GAME_VERSION = 1;
  const MAX_HISTORY = 500; // celá historie se zapisuje při každém tahu, proto strop
  const SNAPSHOT_LEN = 81 + 243;

  function encodeValues(values) {
    return Array.prototype.join.call(values, '');
  }

  function encodeNotes(notes) {
    let s = '';
    for (let i = 0; i < 81; i++) s += notes[i].toString(16).padStart(3, '0');
    return s;
  }

  function decodeValues(str) {
    if (typeof str !== 'string' || !/^[0-9]{81}$/.test(str)) return null;
    const out = new Int8Array(81);
    for (let i = 0; i < 81; i++) out[i] = str.charCodeAt(i) - 48;
    return out;
  }

  function decodeNotes(str) {
    if (typeof str !== 'string' || !/^[0-9a-f]{243}$/.test(str)) return null;
    const out = new Uint16Array(81);
    for (let i = 0; i < 81; i++) {
      const n = parseInt(str.substr(i * 3, 3), 16);
      if (n > 511) return null;
      out[i] = n;
    }
    return out;
  }

  function encodeSnapshot(values, notes) {
    return encodeValues(values) + encodeNotes(notes);
  }

  function isValidFullGrid(g) {
    for (let k = 0; k < 9; k++) {
      let row = 0;
      let col = 0;
      let box = 0;
      for (let j = 0; j < 9; j++) {
        const a = g[k * 9 + j];
        const b = g[j * 9 + k];
        const c = g[(Math.floor(k / 3) * 3 + Math.floor(j / 3)) * 9 + (k % 3) * 3 + (j % 3)];
        if (a < 1 || b < 1 || c < 1) return false;
        row |= 1 << a;
        col |= 1 << b;
        box |= 1 << c;
      }
      if (row !== 0x3fe || col !== 0x3fe || box !== 0x3fe) return false;
    }
    return true;
  }

  function checkFilled(g) {
    let filled = true;
    let correct = true;
    for (let i = 0; i < 81; i++) {
      if (g.values[i] === 0) filled = false;
      else if (g.values[i] !== g.solution[i]) correct = false;
    }
    return { filled: filled, correct: correct };
  }

  function persist() {
    try {
      if (game.solved) {
        localStorage.removeItem(GAME_KEY); // vyřešená hra se neobnovuje
        return;
      }
      localStorage.setItem(
        GAME_KEY,
        JSON.stringify({
          v: GAME_VERSION,
          puzzle: encodeValues(game.puzzle),
          solution: encodeValues(game.solution),
          values: encodeValues(game.values),
          notes: encodeNotes(game.notes),
          history: game.history,
          selected: game.selected,
          notesMode: game.notesMode,
        })
      );
    } catch (e) {
      /* úložiště plné nebo nedostupné: hra běží dál, jen se neuloží */
    }
  }

  function clearSavedGame() {
    try {
      localStorage.removeItem(GAME_KEY);
    } catch (e) {
      /* nic */
    }
  }

  // Vrátí stav hry, nebo null, pokud uložená hra chybí nebo je poškozená.
  function loadGame() {
    let raw;
    try {
      raw = localStorage.getItem(GAME_KEY);
    } catch (e) {
      return null;
    }
    if (!raw) return null;

    try {
      const o = JSON.parse(raw);
      if (!o || typeof o !== 'object' || o.v !== GAME_VERSION) throw new Error('verze');

      const puzzle = decodeValues(o.puzzle);
      const solution = decodeValues(o.solution);
      const values = decodeValues(o.values);
      const notes = decodeNotes(o.notes);
      if (!puzzle || !solution || !values || !notes) throw new Error('formát');
      if (!isValidFullGrid(solution)) throw new Error('řešení není platná mřížka');

      let clues = 0;
      for (let i = 0; i < 81; i++) {
        if (puzzle[i] === 0) continue;
        clues++;
        if (puzzle[i] !== solution[i] || values[i] !== puzzle[i]) throw new Error('zadání nesedí');
      }

      // zadání musí mít právě jedno řešení a to musí být uložené řešení
      if (Sudoku.countSolutions(puzzle, 2) !== 1) throw new Error('zadání není jednoznačné');
      const solved = Sudoku.solve(puzzle);
      for (let i = 0; i < 81; i++) if (solved[i] !== solution[i]) throw new Error('jiné řešení');

      for (let i = 0; i < 81; i++) if (values[i] !== 0) notes[i] = 0;

      // poškozená historie neruší hru, jen se zahodí
      let history = [];
      if (Array.isArray(o.history)) {
        const ok = o.history.every((h) => {
          if (typeof h !== 'string' || h.length !== SNAPSHOT_LEN) return false;
          const v = decodeValues(h.slice(0, 81));
          if (!v || !decodeNotes(h.slice(81))) return false;
          for (let i = 0; i < 81; i++) if (puzzle[i] !== 0 && v[i] !== puzzle[i]) return false;
          return true;
        });
        if (ok) history = o.history.slice(-MAX_HISTORY);
      }

      const g = {
        puzzle: puzzle,
        solution: solution,
        clues: clues,
        values: values,
        notes: notes,
        history: history,
        selected: Number.isInteger(o.selected) && o.selected >= -1 && o.selected <= 80 ? o.selected : -1,
        notesMode: o.notesMode === true,
        solved: false,
        message: '',
      };

      const st = checkFilled(g);
      if (st.filled && st.correct) throw new Error('vyřešená hra se neobnovuje');
      if (st.filled) g.message = 'Mřížka je vyplněná, ale obsahuje chybu.';
      return g;
    } catch (e) {
      clearSavedGame();
      return null;
    }
  }

  // ---------- sousedé políček ----------

  const PEERS = [];
  for (let i = 0; i < 81; i++) {
    const r = Math.floor(i / 9);
    const c = i % 9;
    const set = new Set();
    for (let k = 0; k < 9; k++) {
      set.add(r * 9 + k);
      set.add(k * 9 + c);
    }
    const br = r - (r % 3);
    const bc = c - (c % 3);
    for (let dr = 0; dr < 3; dr++) {
      for (let dc = 0; dc < 3; dc++) set.add((br + dr) * 9 + bc + dc);
    }
    set.delete(i);
    PEERS.push(Array.from(set));
  }

  // ---------- DOM ----------

  const $ = (id) => document.getElementById(id);
  const gridEl = $('grid');
  const padEl = $('pad');
  const infoEl = $('info');
  const statusEl = $('status');
  const btnUndo = $('btn-undo');
  const btnErase = $('btn-erase');
  const btnNotes = $('btn-notes');

  const cells = [];
  for (let i = 0; i < 81; i++) {
    const cell = document.createElement('div');
    cell.className = 'cell r' + Math.floor(i / 9) + ' c' + (i % 9);
    cell.setAttribute('role', 'gridcell');
    cell.dataset.i = String(i);
    const val = document.createElement('span');
    val.className = 'val';
    const notes = document.createElement('div');
    notes.className = 'notes';
    const noteSpans = [];
    for (let d = 0; d < 9; d++) {
      const sp = document.createElement('span');
      notes.appendChild(sp);
      noteSpans.push(sp);
    }
    cell.appendChild(val);
    cell.appendChild(notes);
    gridEl.appendChild(cell);
    cells.push({ el: cell, val: val, noteSpans: noteSpans });
  }

  for (let d = 1; d <= 9; d++) {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = String(d);
    b.dataset.d = String(d);
    b.setAttribute('aria-label', 'Číslice ' + d);
    padEl.appendChild(b);
  }

  // ---------- stav hry ----------

  let game = null;

  function startGame() {
    const opts = settings.limitClues ? { targetClues: settings.targetClues } : {};
    const res = Sudoku.generate(opts);
    game = {
      puzzle: res.puzzle,
      solution: res.solution,
      clues: res.clues,
      values: Int8Array.from(res.puzzle),
      notes: new Uint16Array(81),
      history: [],
      selected: -1,
      notesMode: false,
      solved: false,
      message: '',
    };
    hide($('dlg-win'));
    render();
  }

  function isGiven(i) {
    return game.puzzle[i] !== 0;
  }

  function pushHistory() {
    game.history.push(encodeSnapshot(game.values, game.notes));
    if (game.history.length > MAX_HISTORY) game.history.shift();
  }

  function afterChange() {
    game.message = '';
    const st = checkFilled(game);
    if (st.filled && st.correct) {
      game.solved = true;
      show($('dlg-win'));
    } else if (st.filled) {
      game.message = 'Mřížka je vyplněná, ale obsahuje chybu.';
    }
    render();
  }

  function select(i) {
    if (game.solved) return;
    game.selected = i;
    render();
  }

  function inputDigit(d) {
    if (game.solved || game.selected < 0) return;
    const i = game.selected;
    if (isGiven(i)) return;
    const bit = 1 << (d - 1);
    if (game.notesMode) {
      if (game.values[i] !== 0) return;
      pushHistory();
      game.notes[i] ^= bit;
    } else {
      if (game.values[i] === d) return;
      pushHistory();
      game.values[i] = d;
      game.notes[i] = 0;
      for (const p of PEERS[i]) game.notes[p] &= ~bit;
    }
    afterChange();
  }

  function erase() {
    if (game.solved || game.selected < 0) return;
    const i = game.selected;
    if (isGiven(i)) return;
    if (game.values[i] === 0 && game.notes[i] === 0) return;
    pushHistory();
    game.values[i] = 0;
    game.notes[i] = 0;
    afterChange();
  }

  function undo() {
    if (game.solved || game.history.length === 0) return;
    const snap = game.history.pop();
    game.values = decodeValues(snap.slice(0, 81));
    game.notes = decodeNotes(snap.slice(81));
    afterChange();
  }

  function toggleNotes() {
    game.notesMode = !game.notesMode;
    render();
  }

  function moveSelection(dr, dc) {
    if (game.solved) return;
    if (game.selected < 0) {
      game.selected = 0;
    } else {
      const r = Math.min(8, Math.max(0, Math.floor(game.selected / 9) + dr));
      const c = Math.min(8, Math.max(0, (game.selected % 9) + dc));
      game.selected = r * 9 + c;
    }
    render();
  }

  function computeConflicts() {
    const conflict = new Uint8Array(81);
    for (let i = 0; i < 81; i++) {
      const v = game.values[i];
      if (v === 0) continue;
      for (const p of PEERS[i]) {
        if (game.values[p] === v) {
          if (!isGiven(i)) conflict[i] = 1;
          if (!isGiven(p)) conflict[p] = 1;
        }
      }
    }
    return conflict;
  }

  // ---------- vykreslení ----------

  function render() {
    const sel = game.selected;
    const selVal = sel >= 0 ? game.values[sel] : 0;
    const peerSet = sel >= 0 ? new Set(PEERS[sel]) : null;
    const conflicts = settings.showConflicts ? computeConflicts() : null;

    for (let i = 0; i < 81; i++) {
      const c = cells[i];
      const v = game.values[i];
      const given = isGiven(i);

      c.el.classList.toggle('given', given);
      c.el.classList.toggle('selected', i === sel);
      c.el.classList.toggle('peer', peerSet !== null && peerSet.has(i));
      c.el.classList.toggle('same', selVal !== 0 && i !== sel && v === selVal);
      c.el.classList.toggle('conflict', conflicts !== null && conflicts[i] === 1);

      c.val.textContent = v === 0 ? '' : String(v);

      const mask = game.notes[i];
      const hasNotes = v === 0 && mask !== 0;
      c.el.classList.toggle('has-notes', hasNotes);
      for (let d = 0; d < 9; d++) {
        c.noteSpans[d].textContent = hasNotes && (mask & (1 << d)) ? String(d + 1) : '';
      }

      const pos = 'Řádek ' + (Math.floor(i / 9) + 1) + ', sloupec ' + ((i % 9) + 1) + ', ';
      c.el.setAttribute(
        'aria-label',
        pos + (v === 0 ? 'prázdné' : (given ? 'zadané číslo ' : 'číslo ') + v)
      );
      c.el.setAttribute('aria-selected', i === sel ? 'true' : 'false');
    }

    infoEl.textContent = game.clues + ' zadaných čísel';
    statusEl.textContent = game.message;
    btnNotes.setAttribute('aria-pressed', game.notesMode ? 'true' : 'false');
    btnUndo.disabled = game.solved || game.history.length === 0;

    persist();
  }

  // ---------- dialogy ----------

  function show(el) {
    el.hidden = false;
  }

  function hide(el) {
    el.hidden = true;
  }

  function anyOverlayOpen() {
    return !(($('dlg-new').hidden) && ($('dlg-win').hidden) && ($('dlg-settings').hidden));
  }

  function requestNewGame() {
    if (game.history.length > 0 && !game.solved) show($('dlg-new'));
    else startGame();
  }

  function refreshSettingsUi() {
    $('set-limit').checked = settings.limitClues;
    $('set-conflicts').checked = settings.showConflicts;
    $('set-target').value = String(settings.targetClues);
    $('set-target').disabled = !settings.limitClues;
    $('set-target-out').textContent = String(settings.targetClues);
    $('set-limit-hint').textContent = settings.limitClues
      ? 'Zadání bude mít ' + settings.targetClues + ' čísel. Víc čísel obvykle znamená snazší zadání.'
      : 'Bez omezení generátor odebírá čísla, dokud to jde (typicky 22–27 čísel). Taková zadání bývají náročná.';
  }

  // ---------- události ----------

  gridEl.addEventListener('click', (e) => {
    const cell = e.target.closest('.cell');
    if (cell) select(parseInt(cell.dataset.i, 10));
  });

  padEl.addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (b) inputDigit(parseInt(b.dataset.d, 10));
  });

  btnUndo.addEventListener('click', undo);
  btnErase.addEventListener('click', erase);
  btnNotes.addEventListener('click', toggleNotes);

  $('btn-new').addEventListener('click', requestNewGame);
  $('btn-settings').addEventListener('click', () => {
    refreshSettingsUi();
    show($('dlg-settings'));
  });

  $('dlg-new-cancel').addEventListener('click', () => hide($('dlg-new')));
  $('dlg-new-ok').addEventListener('click', () => {
    hide($('dlg-new'));
    startGame();
  });
  $('dlg-win-ok').addEventListener('click', startGame);
  $('dlg-settings-close').addEventListener('click', () => hide($('dlg-settings')));

  $('set-limit').addEventListener('change', (e) => {
    settings.limitClues = e.target.checked;
    saveSettings();
    refreshSettingsUi();
  });
  $('set-conflicts').addEventListener('change', (e) => {
    settings.showConflicts = e.target.checked;
    saveSettings();
    refreshSettingsUi();
    render();
  });
  $('set-target').addEventListener('input', (e) => {
    const n = parseInt(e.target.value, 10);
    if (Number.isInteger(n)) {
      settings.targetClues = Math.min(MAX_TARGET, Math.max(MIN_TARGET, n));
      saveSettings();
      refreshSettingsUi();
    }
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      hide($('dlg-new'));
      hide($('dlg-settings'));
      return;
    }
    if (anyOverlayOpen()) return;
    if ((e.ctrlKey || e.metaKey) && (e.key === 'z' || e.key === 'Z')) {
      e.preventDefault();
      undo();
    } else if (e.ctrlKey || e.metaKey || e.altKey) {
      return;
    } else if (e.key >= '1' && e.key <= '9') {
      inputDigit(parseInt(e.key, 10));
    } else if (e.key === '0' || e.key === 'Backspace' || e.key === 'Delete') {
      erase();
    } else if (e.key === 'n' || e.key === 'N') {
      toggleNotes();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      moveSelection(-1, 0);
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      moveSelection(1, 0);
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      moveSelection(0, -1);
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      moveSelection(0, 1);
    }
  });

  // ---------- start ----------

  game = loadGame();
  if (game) render();
  else startGame();

  // Service worker (offline režim). Vyžaduje HTTPS nebo localhost; jinde se tiše přeskočí.
  if (navigator.serviceWorker && typeof navigator.serviceWorker.register === 'function') {
    window.addEventListener('load', () => {
      try {
        navigator.serviceWorker.register('sw.js').catch(() => {
          /* bez service workeru aplikace funguje, jen ne offline */
        });
      } catch (e) {
        /* totéž: registrace může vyhodit výjimku i synchronně */
      }
    });
  }
})();
