/* rangement.js — StockEleK · logique page rangement
   Variables déclarées dans le template : COMPS_GRID, COMPONENTS, ESP32_URL,
   assignments, sizes, CONFIG, activePid, _T, _comp_loaded */

/* ── Couleurs catégorie ─────────────────────────────────────────── */
const CAT_MAP = {
  resistor:      ["resistor","résistance","resist"],
  capacitor:     ["capacitor","condensateur","capaci"],
  inductor:      ["inductor","inductance"],
  transistor:    ["transistor"],
  diode:         ["diode","zener"],
  led:           ["led ","led,"],
  amplifier:     ["amplif","op amp","comparator","audio"],
  ic:            ["microcontrol","logic","interface","memory","processor"],
  connector:     ["connector","header","socket","plug","terminal"],
  switch:        ["switch","tactile","push","relay"],
  crystal:       ["crystal","oscillator","timing","resonator"],
  sensor:        ["sensor","capteur"],
  power:         ["power","regulator","ldo","pmic","battery","charger"],
  rf:            ["rf ","radio","bluetooth","wifi","wireless","transceiver"],
};
function catColor(comp) {
  if (!comp?.category) return null;
  const cat = comp.category.toLowerCase();
  for (const [k, kws] of Object.entries(CAT_MAP))
    if (kws.some(w => cat.includes(w))) return LED_COLORS[k] || null;
  return null;
}

/* ── État global ────────────────────────────────────────────────── */
let liveConfig  = JSON.parse(JSON.stringify(CONFIG));
let editMode    = true;
let curCell     = null;
let curSize     = '1x1';
let ctxCell     = null;
let popupCatFilter = '';
let searchMatches   = [];
let searchMatchIdx  = 0;

/* ── Init ───────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  applyColors();
  switchTab(activePid, true);
  updateTabArrows();
  setMode('edit');

  // Raccourcis clavier
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') { closePopup(); closeCtx(); closeCfg(); clearSearch(); }
    if ((e.ctrlKey && e.key === 'f') || (e.key === '/' && !['INPUT','TEXTAREA'].includes(document.activeElement.tagName))) {
      e.preventDefault();
      const inp = document.getElementById('rg-search');
      if (inp) { inp.focus(); inp.select(); }
    }
    if (e.key === 'F3' || (e.ctrlKey && e.key === 'g')) { e.preventDefault(); nextMatch(e.shiftKey ? -1 : 1); }
  });

  document.getElementById('rg-tabs-bar')?.addEventListener('scroll', updateTabArrows);
});

/* ── Couleurs bandes ────────────────────────────────────────────── */
function applyColors() {
  for (const [cellId, compId] of Object.entries(assignments)) {
    const comp = COMPONENTS.find(c => c.id == compId);
    const color = catColor(comp);
    const bar = document.getElementById(`bar-${cellId}`);
    if (bar && color) bar.style.background = color;
  }
}

/* ── Mode ───────────────────────────────────────────────────────── */
function setMode(m) {
  editMode = m === 'edit';
  document.getElementById('btn-mode-read').classList.toggle('active', !editMode);
  document.getElementById('btn-mode-edit').classList.toggle('active',  editMode);
  document.getElementById('rg-grid-wrap')?.classList.toggle('rg-readonly', !editMode);
  const saveBtn = document.getElementById('btn-save');
  if (saveBtn) saveBtn.style.display = editMode ? '' : 'none';
}

/* ── Tabs ───────────────────────────────────────────────────────── */
function switchTab(pid, init) {
  activePid = pid;
  document.querySelectorAll('.rg-plateau').forEach(p => p.classList.toggle('active', p.dataset.pid === pid));
  document.querySelectorAll('.rg-tab').forEach(b => b.classList.toggle('active', b.dataset.pid === pid));
  updateStats(pid);
  if (!init) { const q = document.getElementById('rg-search')?.value; if (q) doSearch(q); }
}

function scrollTabs(d) {
  document.getElementById('rg-tabs-bar')?.scrollBy({ left: d * 200, behavior: 'smooth' });
}

function updateTabArrows() {
  const bar = document.getElementById('rg-tabs-bar');
  if (!bar) return;
  document.getElementById('tabs-l')?.classList.toggle('visible', bar.scrollLeft > 5);
  document.getElementById('tabs-r')?.classList.toggle('visible', bar.scrollLeft < bar.scrollWidth - bar.clientWidth - 5);
}

/* ── Stats plateau ──────────────────────────────────────────────── */
function updateStats(pid) {
  const p = liveConfig.plateaux.find(x => x.id === pid);
  if (!p) return;
  const total  = p.cols * p.rows;
  const filled = Object.entries(assignments).filter(([k, v]) => k.startsWith(pid) && v).length;
  const pct    = total ? Math.round(filled / total * 100) : 0;
  document.getElementById('stat-nom').textContent  = p.label;
  document.getElementById('stat-dim').textContent  = `${p.cols}×${p.rows} ${_T.stat_cells}`;
  document.getElementById('stat-fill').textContent = `${filled}/${total} (${pct}%)`;
  document.getElementById('stat-bar').style.width  = pct + '%';
}

function updateTabCount(pid) {
  const p = liveConfig.plateaux.find(x => x.id === pid);
  if (!p) return;
  const total  = p.cols * p.rows;
  const filled = Object.entries(assignments).filter(([k, v]) => k.startsWith(pid) && v).length;
  const el  = document.querySelector(`.rg-tab-count[data-pid="${pid}"]`);
  const bar = document.querySelector(`.rg-tab[data-pid="${pid}"] .rg-tab-fill-inner`);
  if (el)  el.textContent = `${filled}/${total}`;
  if (bar) bar.style.width = (total ? Math.round(filled / total * 100) : 0) + '%';
}

/* ── Clic cellule ───────────────────────────────────────────────── */
function onCellClick(cellId) {
  if (!editMode) return;
  openPopup(cellId);
}

/* ── Popup ──────────────────────────────────────────────────────── */
function openPopup(cellId) {
  if (!_comp_loaded) {
    fetch('/api/components/for-rangement')
      .then(r => r.json())
      .then(data => { COMPONENTS = data; _comp_loaded = true; _doOpenPopup(cellId); })
      .catch(() => _doOpenPopup(cellId));
    return;
  }
  _doOpenPopup(cellId);
}

function _doOpenPopup(cellId) {
  curCell = cellId;
  curSize = sizes[cellId] || '1x1';
  const compId = assignments[cellId];
  const comp   = compId ? COMPONENTS.find(c => c.id == compId) : null;

  document.getElementById('popup-title').textContent = `${_T.cell_label} ${cellId}`;
  document.getElementById('popup-sub').textContent   = comp
    ? (comp.description || comp.lcsc_part_number || '?')
    : _T.cell_empty_popup;

  document.querySelectorAll('.rg-size-btn').forEach(b => b.classList.toggle('active', b.dataset.size === curSize));

  // Reset filtre catégorie
  popupCatFilter = '';
  document.querySelectorAll('.rg-popup-filter-btn').forEach(b => b.classList.toggle('active', b.dataset.cat === ''));

  document.getElementById('popup-search').value = '';
  filterPopup('');
  document.getElementById('rg-popup-bg').classList.add('open');
  setTimeout(() => document.getElementById('popup-search').focus(), 60);
}

function closePopup() {
  document.getElementById('rg-popup-bg')?.classList.remove('open');
  curCell = null;
}

function selectSize(s) {
  curSize = s;
  document.querySelectorAll('.rg-size-btn').forEach(b => b.classList.toggle('active', b.dataset.size === s));
}

function setCatFilter(cat) {
  popupCatFilter = cat;
  document.querySelectorAll('.rg-popup-filter-btn').forEach(b => b.classList.toggle('active', b.dataset.cat === cat));
  filterPopup(document.getElementById('popup-search').value);
}

function filterPopup(q) {
  const lq     = q.toLowerCase();
  const list   = document.getElementById('popup-list');
  const curId  = assignments[curCell];
  const placed = new Set(Object.values(assignments).map(v => String(v)));

  let filtered = COMPONENTS.filter(c => String(c.id) === String(curId) || !placed.has(String(c.id)));
  if (popupCatFilter) filtered = filtered.filter(c => c.category?.startsWith(popupCatFilter));
  if (q) filtered = filtered.filter(c =>
    (c.description || '').toLowerCase().includes(lq) ||
    (c.lcsc_part_number || '').toLowerCase().includes(lq) ||
    (c.manufacture_part_number || '').toLowerCase().includes(lq) ||
    (c.package || '').toLowerCase().includes(lq)
  );
  filtered = filtered.slice(0, 60);

  if (!filtered.length) {
    list.innerHTML = `<div style="text-align:center;padding:2rem;color:var(--text-muted);font-size:.85rem">${_T.empty_search}</div>`;
    return;
  }

  list.innerHTML = '';
  for (const c of filtered) {
    const isCur = curId == c.id;
    const dup   = Object.entries(assignments).find(([k, v]) => v == c.id && k !== curCell);
    const color = catColor(c);
    const qtyColor = c.quantity <= 0 ? 'var(--danger)' : c.quantity < 5 ? 'var(--warning)' : 'var(--text-muted)';

    const div = document.createElement('div');
    div.className = 'rg-comp-item' + (isCur ? ' selected' : '');
    div.innerHTML = `
      <div class="rg-comp-thumb">
        ${color ? `<div class="rg-comp-cat-bar" style="background:${color}"></div>` : ''}
        ${c.image_path
          ? `<img src="/images/${c.image_path.split('images/').pop()}" loading="lazy"/>`
          : `<span style="font-size:1.1rem">📦</span>`}
      </div>
      <div class="rg-comp-info">
        <div class="rg-comp-name" style="color:${isCur ? 'var(--accent)' : 'var(--text)'}">${_esc(c.description || c.manufacture_part_number || '—')}</div>
        <div class="rg-comp-meta">
          ${c.lcsc_part_number ? `<span style="font-family:var(--mono)">${_esc(c.lcsc_part_number)}</span>` : ''}
          ${c.package ? `<span class="rg-pkg-badge">${_esc(c.package)}</span>` : ''}
          <span class="rg-comp-qty" style="color:${qtyColor}">${c.quantity} pcs</span>
          ${dup ? `<span class="rg-comp-dup">📍${dup[0]}</span>` : ''}
        </div>
      </div>
      ${isCur ? `<span class="rg-comp-check">✓</span>` : ''}`;
    div.addEventListener('click', () => pickComp(c.id));
    list.appendChild(div);
  }
}

function _esc(s) {
  const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML;
}

/* ── Sélectionner / vider → save → reload ───────────────────────── */
function pickComp(compId) {
  if (!curCell) return;
  for (const [k, v] of Object.entries(assignments)) if (v == compId && k !== curCell) delete assignments[k];
  assignments[curCell] = compId;
  sizes[curCell] = curSize;
  closePopup();
  saveAndReload();
}

function emptyCell() {
  if (!curCell) return;
  delete assignments[curCell];
  sizes[curCell] = '1x1';
  closePopup();
  saveAndReload();
}

function saveAndReload() {
  const btn = document.getElementById('btn-save');
  if (btn) btn.textContent = '⏳';
  fetch(SAVE_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ assignments, sizes })
  }).then(() => window.location.href = '/rangement/' + ATELIER_ID + '?pid=' + activePid);
}

function doSave() {
  const btn = document.getElementById('btn-save');
  if (btn) { btn.textContent = '⏳'; btn.disabled = true; }
  fetch(SAVE_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ assignments, sizes })
  }).then(r => r.json()).then(() => {
    if (btn) { btn.textContent = '✅'; setTimeout(() => { btn.textContent = _T.btn_save; btn.disabled = false; }, 1800); }
  }).catch(() => { if (btn) { btn.textContent = '❌'; btn.disabled = false; } });
}

/* ── Vider plateau ──────────────────────────────────────────────── */
function clearPlateau() {
  const p = liveConfig.plateaux.find(x => x.id === activePid);
  if (!p || !confirm(`Vider "${p.label}" ?`)) return;
  const total = p.cols * p.rows;
  for (let i = 1; i <= total; i++) { const k = activePid + i; delete assignments[k]; sizes[k] = '1x1'; }
  Object.keys(assignments).filter(k => k.startsWith(activePid)).forEach(k => { delete assignments[k]; sizes[k] = '1x1'; });
  saveAndReload();
}

/* ── Recherche ──────────────────────────────────────────────────── */
function doSearch(q) {
  const lq = q.trim().toLowerCase();
  const clearBtn = document.getElementById('rg-search-clear');
  const navWrap  = document.getElementById('rg-search-nav');
  const status   = document.getElementById('rg-search-status');
  if (clearBtn) clearBtn.style.display = lq ? 'inline' : 'none';

  if (!lq) {
    document.querySelectorAll('.rg-cell').forEach(c => c.classList.remove('match', 'match-current', 'dimmed'));
    document.querySelectorAll('.rg-tab-dot').forEach(d => d.style.display = 'none');
    if (navWrap) navWrap.classList.remove('visible');
    if (status)  status.textContent = '';
    searchMatches = []; searchMatchIdx = 0;
    return;
  }

  const matchIds = new Set(COMPONENTS.filter(c =>
    (c.description || '').toLowerCase().includes(lq) ||
    (c.lcsc_part_number || '').toLowerCase().includes(lq) ||
    (c.manufacture_part_number || '').toLowerCase().includes(lq) ||
    (c.package || '').toLowerCase().includes(lq) ||
    (c.category || '').toLowerCase().includes(lq)
  ).map(c => String(c.id)));

  const matchCells = Object.entries(assignments)
    .filter(([, v]) => v && matchIds.has(String(v)))
    .map(([k]) => k);

  const matchPids = new Set(matchCells.map(k => k.match(/^([A-Z]+)/)?.[1]).filter(Boolean));

  document.querySelectorAll('.rg-cell').forEach(cell => {
    const isMatch = matchCells.includes(cell.dataset.cell);
    const isEmpty = !assignments[cell.dataset.cell];
    cell.classList.toggle('match',  isMatch);
    cell.classList.toggle('dimmed', !isMatch && !isEmpty);
    cell.classList.remove('match-current');
  });

  document.querySelectorAll('.rg-tab-dot').forEach(d => {
    d.style.display = (matchPids.has(d.dataset.pid) && d.dataset.pid !== activePid) ? 'block' : 'none';
  });

  searchMatches  = matchCells;
  searchMatchIdx = matchCells.findIndex(k => k.startsWith(activePid));
  if (searchMatchIdx < 0) searchMatchIdx = 0;

  highlightCurrent();

  if (status) {
    status.textContent = matchCells.length
      ? `${searchMatchIdx + 1}/${matchCells.length}`
      : _T.find_no_result;
    status.style.color = matchCells.length ? 'var(--accent)' : 'var(--danger)';
  }
  if (navWrap) navWrap.classList.toggle('visible', matchCells.length > 0);
}

function nextMatch(d) {
  if (!searchMatches.length) return;
  searchMatchIdx = (searchMatchIdx + d + searchMatches.length) % searchMatches.length;
  const cellId = searchMatches[searchMatchIdx];
  const pid    = cellId.match(/^([A-Z]+)/)?.[1];
  if (pid && pid !== activePid) switchTab(pid);
  highlightCurrent();
  document.getElementById('rg-search-status').textContent = `${searchMatchIdx + 1}/${searchMatches.length}`;
  setTimeout(() => document.getElementById(`cell-${cellId}`)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 100);
}

function highlightCurrent() {
  document.querySelectorAll('.rg-cell.match-current').forEach(c => c.classList.remove('match-current'));
  const cellId = searchMatches[searchMatchIdx];
  if (cellId) document.getElementById(`cell-${cellId}`)?.classList.add('match-current');
}

function clearSearch() {
  const inp = document.getElementById('rg-search');
  if (inp) { inp.value = ''; inp.focus(); }
  doSearch('');
}

/* ── Tooltip ────────────────────────────────────────────────────── */
let _tipTimer = null;
function showTip(e, cellId) {
  const compId = assignments[cellId];
  if (!compId) return;
  const comp = COMPONENTS.find(c => c.id == compId);
  if (!comp) return;
  clearTimeout(_tipTimer);
  _tipTimer = setTimeout(() => {
    const tt = document.getElementById('rg-tip');
    tt.querySelector('.rg-tip-id').textContent   = `${_T.cell_label} ${cellId}`;
    tt.querySelector('.rg-tip-name').textContent  = comp.description || comp.lcsc_part_number || '?';
    tt.querySelector('.rg-tip-lcsc').textContent  = comp.lcsc_part_number || '';
    tt.querySelector('.rg-tip-mfr').textContent   = comp.manufacturer ? `🏭 ${comp.manufacturer}` : '';
    tt.querySelector('.rg-tip-hint').textContent  = editMode ? _T.tooltip_right_click : '';

    const tags = tt.querySelector('.rg-tip-tags');
    tags.innerHTML = '';
    const qtyColor = comp.quantity <= 0 ? 'var(--danger)' : comp.quantity < 5 ? 'var(--warning)' : 'var(--accent)';
    tags.innerHTML += `<span class="rg-tip-tag" style="color:${qtyColor};font-weight:700">${comp.quantity} pcs</span>`;
    if (comp.package) tags.innerHTML += `<span class="rg-tip-tag">${_esc(comp.package)}</span>`;
    if (comp.location) tags.innerHTML += `<span class="rg-tip-tag">📍 ${_esc(comp.location)}</span>`;

    const img  = tt.querySelector('.rg-tip-img');
    const icon = tt.querySelector('.rg-tip-icon');
    if (comp.image_path) {
      img.src = '/images/' + comp.image_path.split('images/').pop();
      img.style.display = 'block'; icon.style.display = 'none';
    } else {
      img.style.display = 'none'; icon.style.display = 'inline';
    }

    tt.style.display = 'block';
    const x = Math.min(e.clientX + 14, window.innerWidth  - tt.offsetWidth  - 14);
    const y = Math.min(e.clientY + 14, window.innerHeight - tt.offsetHeight - 14);
    tt.style.left = x + 'px'; tt.style.top = y + 'px';
  }, 220);
}

function hideTip() {
  clearTimeout(_tipTimer);
  document.getElementById('rg-tip').style.display = 'none';
}

/* ── Menu contextuel ────────────────────────────────────────────── */
function onCtx(e, cellId) {
  if (!editMode) return;
  e.preventDefault(); e.stopPropagation();
  hideTip(); ctxCell = cellId;
  const hasCom  = !!assignments[cellId];
  const hasESP  = !!ESP32_URL;
  document.getElementById('ctx-lbl').textContent = `${_T.cell_label} ${cellId}`;
  const clrBtn = document.getElementById('ctx-clear'); clrBtn.disabled = !hasCom; clrBtn.style.opacity = hasCom ? '1' : '.35';
  const ledBtn = document.getElementById('ctx-led');   ledBtn.disabled = !(hasCom && hasESP); ledBtn.style.opacity = (hasCom && hasESP) ? '1' : '.35';
  document.getElementById('ctx-led-lbl').textContent = _T.ctx_led_on;
  const menu = document.getElementById('rg-ctx');
  menu.style.display = 'block';
  const x = Math.min(e.clientX, window.innerWidth  - menu.offsetWidth  - 8);
  const y = Math.min(e.clientY, window.innerHeight - menu.offsetHeight - 8);
  menu.style.left = x + 'px'; menu.style.top = y + 'px';
}

function closeCtx() { document.getElementById('rg-ctx').style.display = 'none'; }
function ctxAssign() { const c = ctxCell; closeCtx(); ctxCell = null; if (c) openPopup(c); }
function ctxEmpty()  { const c = ctxCell; closeCtx(); ctxCell = null; if (!c) return; curCell = c; emptyCell(); }

/* ── LED ────────────────────────────────────────────────────────── */
function toast(msg, type) {
  const t = document.getElementById('rg-toast');
  clearTimeout(t._t);
  t.className = `rg-toast ${type}`;
  t.textContent = msg;
  requestAnimationFrame(() => {
    t.classList.add('show');
    t._t = setTimeout(() => t.classList.remove('show'), 3200);
  });
}

function ctxLed() {
  const cell = ctxCell; closeCtx();
  if (!cell || !ESP32_URL) return;
  const compId = assignments[cell]; if (!compId) return;
  const lbl = document.getElementById('ctx-led-lbl');
  if (lbl) lbl.textContent = _T.ctx_led_sending;
  fetch(`/api/led/${cell}/on`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ component_id: compId, atelier_id: ATELIER_ID })
  }).then(r => r.json()).then(d => {
    toast(d.ok ? (d.queued ? `⏳ ${_T.ctx_led_ok}` : `💡 ${_T.ctx_led_ok}`) : `❌ ${d.error || _T.ctx_led_err}`, d.ok ? (d.queued ? 'queued' : 'ok') : 'err');
    if (lbl) setTimeout(() => { if (lbl) lbl.textContent = _T.ctx_led_on; }, 2500);
  }).catch(() => {
    toast(_T.err_network, 'err');
    if (lbl) lbl.textContent = _T.ctx_led_on;
  });
}

/* ── Config ─────────────────────────────────────────────────────── */
function openCfg()  { document.getElementById('rg-cfg-overlay').classList.add('open');  document.getElementById('rg-cfg-panel').classList.add('open'); }
function closeCfg() { document.getElementById('rg-cfg-overlay').classList.remove('open'); document.getElementById('rg-cfg-panel').classList.remove('open'); }

function step(inp, d) {
  const v = parseInt(inp.value) || 1;
  inp.value = Math.min(parseInt(inp.max) || 30, Math.max(parseInt(inp.min) || 1, v + d));
}

function addPlateau() {
  const list = document.getElementById('cfg-list');
  const div  = document.createElement('div');
  div.className = 'rg-cfg-row';
  div.innerHTML = `
    <input type="text" value="" class="form-input cfg-pid" placeholder="ID"
           style="width:44px;text-align:center;font-weight:800;text-transform:uppercase;font-family:var(--mono);padding:.25rem;font-size:.8rem"/>
    <input type="text" value="${_T.ph_name}" class="form-input cfg-label"
           style="flex:1;padding:.25rem .4rem;font-size:.8rem"/>
    <div class="rg-stepper"><button onclick="step(this.nextElementSibling,-1)">−</button><input type="number" value="7" min="1" max="30" class="cfg-cols"/><button onclick="step(this.previousElementSibling,+1)">+</button></div>
    <span style="font-size:.7rem;color:var(--text-muted)">×</span>
    <div class="rg-stepper"><button onclick="step(this.nextElementSibling,-1)">−</button><input type="number" value="4" min="1" max="30" class="cfg-rows"/><button onclick="step(this.previousElementSibling,+1)">+</button></div>
    <button onclick="removePlateau(this)" class="btn btn-danger btn-sm" style="padding:.2rem .4rem;font-size:.75rem;flex-shrink:0">🗑</button>`;
  list.appendChild(div);
  list.scrollTop = list.scrollHeight;
}

function removePlateau(btn) {
  if (!confirm(_T.confirm_delete)) return;
  const row = btn.closest('.rg-cfg-row');
  const pid = row.querySelector('.cfg-pid').value.toUpperCase().trim();
  row.remove();
  if (pid) {
    Object.keys(assignments).filter(k => k.startsWith(pid)).forEach(k => delete assignments[k]);
    Object.keys(sizes).filter(k => k.startsWith(pid)).forEach(k => delete sizes[k]);
    liveConfig.plateaux = liveConfig.plateaux.filter(p => p.id !== pid);
  }
}

function saveCfg() {
  const rows = document.querySelectorAll('.rg-cfg-row');
  const plateaux = [...rows].map(r => ({
    id:    r.querySelector('.cfg-pid').value.toUpperCase().trim() || 'X',
    label: r.querySelector('.cfg-label').value.trim() || 'Plateau',
    cols:  parseInt(r.querySelector('.cfg-cols').value) || 5,
    rows:  parseInt(r.querySelector('.cfg-rows').value) || 4,
  }));
  const pids = new Set(plateaux.map(p => p.id));
  Object.keys(assignments).forEach(k => { const pid = k.match(/^([A-Z]+)/)?.[1]; if (pid && !pids.has(pid)) delete assignments[k]; });
  const btn = document.querySelector('[onclick="saveCfg()"]');
  if (btn) { btn.textContent = '⏳'; btn.disabled = true; }
  fetch(SAVE_URL, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ config: { plateaux }, assignments, sizes })
  }).then(r => r.json()).then(d => {
    if (d.ok !== false) window.location.reload();
    else { alert(_T.err_save); if (btn) { btn.textContent = _T.btn_apply; btn.disabled = false; } }
  }).catch(() => { alert(_T.err_network); if (btn) { btn.textContent = _T.btn_apply; btn.disabled = false; } });
}

/* ── Export impression ──────────────────────────────────────────── */
function exportPlateau() {
  const plateau = document.querySelector(`.rg-plateau[data-pid="${activePid}"]`);
  if (!plateau) return;
  const p       = liveConfig.plateaux.find(x => x.id === activePid);
  const cellPx  = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--cell')) || 88;
  const btn     = document.querySelector('[onclick="exportPlateau()"]');

  // Préparer le HTML de la grille avec des couleurs résolues (sans color-mix ni var())
  const clone = plateau.querySelector('.rg-grid').cloneNode(true);
  clone.style.gridTemplateColumns = `repeat(${p.cols}, ${cellPx}px)`;
  clone.style.gridTemplateRows    = `repeat(${p.rows}, ${cellPx}px)`;
  clone.style.gap  = '5px';
  clone.style.width = 'fit-content';
  // Résoudre les styles inline des cellules (remplacer les var() par des valeurs fixes)
  clone.querySelectorAll('[style]').forEach(el => {
    el.style.cssText = el.style.cssText
      .replace(/var\(--cell\)/g, cellPx + 'px')
      .replace(/var\(--gap\)/g,  '5px')
      .replace(/var\(--r\)/g,    '8px');
  });

  const gridW = p.cols * (cellPx + 5) - 5;
  const gridH = p.rows * (cellPx + 5) - 5;
  const label = p ? p.label : activePid;

  // Construire une page isolée dans un iframe caché — sans les CSS de l'app
  const iframe = document.createElement('iframe');
  iframe.style.cssText = 'position:fixed;left:-9999px;top:0;width:'+(gridW+60)+'px;height:'+(gridH+80)+'px;border:none;';
  document.body.appendChild(iframe);

  const html = `<!DOCTYPE html><html><head><meta charset="utf-8"/><style>
*{margin:0;padding:0;box-sizing:border-box;}
body{background:#0f111a;display:inline-block;padding:20px;}
.rg-grid{display:grid;gap:5px;}
.rg-cell{background:#1a1e2e;border:1.5px solid #2a3050;border-radius:8px;
  display:flex;flex-direction:column;align-items:center;justify-content:flex-start;
  overflow:hidden;position:relative;}
.rg-cell.filled{border-color:#4f46e550;background:#4f46e50a;}
.rg-cell-id{position:absolute;top:3px;left:4px;font-family:monospace;font-size:9px;
  font-weight:700;color:#64748b;opacity:.6;pointer-events:none;}
.rg-cell-bar{position:absolute;top:0;left:0;right:0;height:3px;border-radius:8px 8px 0 0;}
.rg-cell-img{object-fit:contain;border-radius:4px;flex-shrink:0;}
.rg-cell-icon{flex-shrink:0;}
.rg-cell-name{font-size:${Math.max(7, cellPx*0.09)}px;font-weight:600;color:#e2e8f0;
  text-align:center;line-height:1.25;padding:2px 4px 0;
  overflow:hidden;display:-webkit-box;-webkit-box-orient:vertical;
  -webkit-line-clamp:3;max-width:100%;word-break:break-word;}
.rg-cell-plus{color:#2a3050;font-size:24px;font-weight:300;margin:auto;}
.rg-cell-qty{position:absolute;bottom:3px;right:4px;font-family:monospace;
  font-size:8px;font-weight:700;color:#64748b;}
</style></head><body>${clone.outerHTML}</body></html>`;

  iframe.onload = () => {
    if (btn) { btn.textContent = '⏳ Export…'; btn.disabled = true; }

    // Charger html2canvas dans l'iframe
    const script = iframe.contentDocument.createElement('script');
    script.src = 'https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js';
    script.onload = () => {
      iframe.contentWindow.html2canvas(iframe.contentDocument.body, {
        backgroundColor: '#0f111a',
        scale: 2,
        useCORS: true,
        allowTaint: false,
        logging: false,
      }).then(canvas => {
        const link = document.createElement('a');
        link.download = `rangement-${activePid}-${label.replace(/[^a-zA-Z0-9]/g,'-')}.png`;
        link.href = canvas.toDataURL('image/png');
        link.click();
        if (btn) { btn.textContent = '🖨 Exporter'; btn.disabled = false; }
        setTimeout(() => document.body.removeChild(iframe), 500);
      }).catch(err => {
        console.error('Export PNG:', err);
        alert('Export PNG échoué : ' + err.message);
        if (btn) { btn.textContent = '🖨 Exporter'; btn.disabled = false; }
        document.body.removeChild(iframe);
      });
    };
    script.onerror = () => {
      alert('html2canvas non disponible (hors ligne ?). Essaie Ctrl+P pour imprimer.');
      if (btn) { btn.textContent = '🖨 Exporter'; btn.disabled = false; }
      document.body.removeChild(iframe);
    };
    iframe.contentDocument.head.appendChild(script);
  };

  iframe.srcdoc = html;
}

/* ── Fermeture globale ──────────────────────────────────────────── */
document.addEventListener('mousedown', e => {
  if (!document.getElementById('rg-ctx').contains(e.target)) { closeCtx(); ctxCell = null; }
  if (!document.getElementById('rg-tip').contains(e.target))   hideTip();
});
