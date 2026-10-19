/* ================= PRO PDF EDITOR ================= */
Object.assign(ICONS, {
  cursor: '<path d="m4 4 7 17 2.5-7.5L21 11z"/>',
  type: '<path d="M4 7V4h16v3M9 20h6M12 4v16"/>',
  typeplus: '<path d="M3 7V4h12v3M9 4v14M6 18h6M19 13v8M15 17h8"/>',
  pen: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
  marker: '<path d="m9 11-6 6v3h9l3-3"/><path d="m22 12-4.6 4.6a2 2 0 0 1-2.8 0l-5.2-5.2a2 2 0 0 1 0-2.8L14 4"/>',
  square: '<rect x="3" y="3" width="18" height="18" rx="2"/>',
  eraser: '<path d="m7 21-4.3-4.3a1 1 0 0 1 0-1.4l10-10a1 1 0 0 1 1.4 0l5.6 5.6a1 1 0 0 1 0 1.4L13 19"/><path d="M22 21H7M5 11l9 9"/>',
  wand: '<path d="m15 4 5 5M3 21l11-11"/><path d="M14 4V2M18 8h2M17 3l1-1M20 6l1-1M9 3l.6 1.6L11 5l-1.4.6L9 7l-.6-1.4L7 5l1.4-.4z"/>',
  sign: '<path d="M3 17c3-5 5-8 7-8s-1 8 1 8 3-4 4-4 1 3 3 3 2-1 3-2"/><path d="M3 21h18"/>',
  undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
  redo: '<path d="m15 14 5-5-5-5"/><path d="M20 9H9.5a5.5 5.5 0 0 0 0 11H13"/>',
  zin: '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3M11 8v6M8 11h6"/>',
  zout: '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3M8 11h6"/>',
  up: '<path d="m18 15-6-6-6 6"/>'
});
const ed = {src: null, draft: null, pages: [], page: 0, zoom: 1, base: 1, tool: 'select', layout: null, sel: null,
  undo: [], redo: [], editing: null, busy: false, dirty: false, placeFile: null, placeW: 150, placeAR: 1, fileMode: 'add',
  hl: '#facc15', magicR: 10, shape: {kind: 'rect', width: 1.5, fill: false, fillColor: '#e9d5ff'}, bgc: null, bgk: 1, scan: {}};
const peOv = $('#peOv'), pePage = $('#pePage'), peImg = $('#peImg'), peInk = $('#peInk'), peSide = $('#peSide');
const FAMCSS = {serif: "'Times New Roman', Times, serif", sans: 'Helvetica, Arial, sans-serif', mono: "'Courier New', monospace"};
const IMG_FX = [['auto_enhance', 'Auto-enhance'], ['grayscale', 'Black & white'], ['brighter', 'Brighter'], ['darker', 'Darker'],
  ['contrast', 'More contrast'], ['sharpen', 'Sharpen'], ['blur', 'Blur'], ['sepia', 'Sepia'], ['invert', 'Invert'],
  ['rotate', 'Rotate 90°'], ['flip_h', 'Flip ↔'], ['flip_v', 'Flip ↕'], ['remove_bg', 'Remove BG']];
const S = () => ed.base * ed.zoom;
const edOpen = () => !$('#pdfEditor').classList.contains('hidden');
const place = (el, b, s) => { el.style.left = b[0] * s + 'px'; el.style.top = b[1] * s + 'px'; el.style.width = (b[2] - b[0]) * s + 'px'; el.style.height = (b[3] - b[1]) * s + 'px'; };
const norm = b => [Math.min(b[0], b[2]), Math.min(b[1], b[3]), Math.max(b[0], b[2]), Math.max(b[1], b[3])];
const toPdf = e => { const r = pePage.getBoundingClientRect(), s = S(); return [(e.clientX - r.left) / s, (e.clientY - r.top) / s]; };
function showBusy(t) { $('#peBusyText').textContent = t || 'Applying…'; $('#peBusy').classList.remove('hidden'); }
function hideBusy() { $('#peBusy').classList.add('hidden'); }

async function openEditor(fileId) {
  if (!fileId) return;
  closeTools();
  $('#pdfEditor').classList.remove('hidden'); showBusy('Opening…');
  try {
    const j = await api('/api/pdf/open', {file_id: fileId});
    Object.assign(ed, {src: j.source, draft: j.draft, pages: j.pages, page: 0, zoom: 1, undo: [], redo: [], dirty: false, sel: null, editing: null, placeFile: null, scan: {}});
    $('#peName').textContent = j.source.name;
    computeBase(); setTool('select'); renderThumbs(); await loadPage(); updateUndo();
  } catch (e) { toast('Could not open PDF: ' + e.message, 'err'); $('#pdfEditor').classList.add('hidden'); }
  finally { hideBusy(); }
}
function closeEditor(force) {
  if (!force && ed.dirty && !confirm('Close without saving your edits?')) return;
  if (ed.editing) cancelEdit();
  $('#pdfEditor').classList.add('hidden'); ed.dirty = false;
}
function computeBase() {
  const pw = ed.pages[ed.page]?.w || 595, avail = Math.max(260, $('#peStage').clientWidth - 56);
  ed.base = Math.min(avail / pw, 1.7);
}
function loadImg(url) { return new Promise((res, rej) => { peImg.onload = () => res(); peImg.onerror = () => rej(new Error('Page render failed')); peImg.src = url; }); }
async function loadPage(reselect) {
  const pg = ed.pages[ed.page]; if (!pg) return;
  const s = S(), dpr = Math.min(devicePixelRatio || 1, 2), rs = Math.min(4.5, +(s * dpr).toFixed(2));
  pePage.style.width = pg.w * s + 'px'; pePage.style.height = pg.h * s + 'px';
  const [lay] = await Promise.all([
    fetch(`/api/pdf/${ed.draft.id}/layout/${ed.page}`, {headers: HDR}).then(r => r.json()),
    loadImg(`/api/pdf/${ed.draft.id}/render/${ed.page}?scale=${rs}`)]);
  ed.layout = lay;
  peInk.width = pg.w * s * dpr; peInk.height = pg.h * s * dpr;
  buildBg(); drawOverlays(); markThumb(); updateStatus();
  const pageArea = pg.w * pg.h, big = lay.images.find(m => (m.bbox[2] - m.bbox[0]) * (m.bbox[3] - m.bbox[1]) > pageArea * 0.4);
  if (!lay.runs.length && big && !ed.scan[ed.page]) runOcr(big.bbox, true);
  $('#peZoom').textContent = Math.round(ed.zoom * 100) + '%';
  if (reselect) reselectAt(reselect); else select(null);
}
function buildBg() {
  try { const c = document.createElement('canvas'); c.width = peImg.naturalWidth; c.height = peImg.naturalHeight;
    ed.bgc = c.getContext('2d', {willReadFrequently: true}); ed.bgc.drawImage(peImg, 0, 0); ed.bgk = peImg.naturalWidth / ed.pages[ed.page].w; } catch { ed.bgc = null; }
}
function sampleBg(b) {
  if (!ed.bgc) return '#ffffff';
  const k = ed.bgk, pts = [[b[0] - 2, (b[1] + b[3]) / 2], [b[2] + 2, (b[1] + b[3]) / 2], [b[0], b[1] - 1.5]];
  for (const [x, y] of pts) {
    const px = Math.round(x * k), py = Math.round(y * k);
    if (px < 0 || py < 0 || px >= ed.bgc.canvas.width || py >= ed.bgc.canvas.height) continue;
    const d = ed.bgc.getImageData(px, py, 1, 1).data; return `rgb(${d[0]},${d[1]},${d[2]})`;
  }
  return '#ffffff';
}
function drawOverlays() {
  const s = S(); peOv.innerHTML = '';
  for (const m of ed.layout.images) { const d = document.createElement('div'); d.className = 'pe-img'; d.dataset.img = m.index; place(d, m.bbox, s); d.innerHTML = '<span class="h"></span>'; peOv.appendChild(d); }
  for (const r of ed.layout.runs) { const d = document.createElement('div'); d.className = 'pe-run'; d.dataset.run = r.id; place(d, r.bbox, s); peOv.appendChild(d); }
  for (const r of ed.scan[ed.page] || []) { const d = document.createElement('div'); d.className = 'pe-run scan'; d.dataset.run = r.id; place(d, r.bbox, s); peOv.appendChild(d); }
}
async function runOcr(imgBbox, auto) {
  const pageAt = ed.page, draftAt = ed.draft.id;
  showBusy('Reading text in the image…');
  try {
    const q = imgBbox ? `?x0=${imgBbox[0]}&y0=${imgBbox[1]}&x1=${imgBbox[2]}&y1=${imgBbox[3]}` : '';
    const j = await (await fetch(`/api/pdf/${draftAt}/ocr/${pageAt}${q}`, {headers: HDR})).json();
    if (ed.draft.id !== draftAt || ed.page !== pageAt) return;
    const old = (ed.scan[pageAt] || []).filter(b => !j.boxes.some(n => overlap(n.bbox, b.bbox) > 0.3));
    ed.scan[pageAt] = old.concat(j.boxes.map((b, i) => ({...b, id: `s${Date.now() % 1e6}_${i}`})));
    drawOverlays(); if (ed.sel) select(ed.sel);
    if (j.boxes.length) { if (!auto || ed.tool === 'select') setTool('text'); toast(`Found ${j.boxes.length} line${j.boxes.length > 1 ? 's' : ''} of text — click one to edit it`); }
    else if (!auto) toast(j.error ? 'Text reading failed: ' + j.error : 'No readable text found in that image', 'err');
  } catch (e) { if (!auto) toast('Text reading failed: ' + e.message, 'err'); }
  finally { hideBusy(); }
}
function overlap(a, b) {
  const ix = Math.max(0, Math.min(a[2], b[2]) - Math.max(a[0], b[0])), iy = Math.max(0, Math.min(a[3], b[3]) - Math.max(a[1], b[1]));
  return ix * iy / Math.max(1e-6, Math.min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1])));
}
const runOf = el => el.classList.contains('scan') ? (ed.scan[ed.page] || []).find(r => r.id === el.dataset.run) : ed.layout.runs.find(r => String(r.id) === el.dataset.run);
const imgOf = el => ed.layout.images.find(m => String(m.index) === el.dataset.img);
function select(sel) {
  ed.sel = sel;
  peOv.querySelectorAll('.sel').forEach(x => x.classList.remove('sel'));
  if (sel?.type === 'img') peOv.querySelector(`.pe-img[data-img="${sel.m.index}"]`)?.classList.add('sel');
  if (sel?.type === 'run') peOv.querySelector(`.pe-run[data-run="${CSS.escape(String(sel.r.id))}"]`)?.classList.add('sel');
  renderSide();
}
function reselectAt(rect) {
  let best = null, sc = 0; const r = norm(rect);
  for (const m of ed.layout.images) {
    const b = m.bbox, ix = Math.max(0, Math.min(b[2], r[2]) - Math.max(b[0], r[0])), iy = Math.max(0, Math.min(b[3], r[3]) - Math.max(b[1], r[1]));
    const inter = ix * iy, uni = (b[2] - b[0]) * (b[3] - b[1]) + (r[2] - r[0]) * (r[3] - r[1]) - inter, v = inter / Math.max(1e-6, uni);
    if (v > sc) { sc = v; best = m; }
  }
  select(best && sc > 0.2 ? {type: 'img', m: best} : null);
}
function updateStatus() { $('#peStatus').textContent = `Page ${ed.page + 1}/${ed.pages.length}${ed.dirty ? ' · unsaved' : ''}`; }
function updateUndo() { $('#peUndo').disabled = !ed.undo.length; $('#peRedo').disabled = !ed.redo.length; updateStatus(); }

/* ---------- apply edits on the server (every edit is a new draft → exact preview + undo) ---------- */
async function applyOps(ops, opt = {}) {
  if (ed.busy) return false;
  ed.busy = true; showBusy(opt.label || 'Applying…');
  try {
    const r = await api(`/api/pdf/${ed.draft.id}/edit`, {ops});
    if (!r.ok) { toast(r.error, 'err'); return false; }
    ed.undo.push({draft: ed.draft, pages: ed.pages}); if (ed.undo.length > 80) ed.undo.shift(); ed.redo = [];
    ed.draft = r.draft; ed.pages = r.pages; ed.dirty = true;
    if (ops.some(o => o.op.startsWith('page_'))) ed.scan = {};
    else if (!ops.every(o => o.op === 'scan_text')) ops.forEach(o => { if (['move_image', 'image_filter', 'replace_image', 'delete_image', 'erase', 'magic_erase'].includes(o.op)) delete ed.scan[o.page]; });
    if (opt.onOk) opt.onOk();
    if (opt.page != null) ed.page = opt.page;
    ed.page = Math.max(0, Math.min(ed.page, ed.pages.length - 1));
    await loadPage(opt.reselect);
    if (ops.some(o => o.op.startsWith('page_'))) renderThumbs(); else refreshThumb(ed.page);
    return true;
  } catch (e) { toast(e.message, 'err'); return false; }
  finally { ed.busy = false; hideBusy(); updateUndo(); }
}
async function stepHistory(from, to) {
  if (ed.busy || !from.length) return;
  if (ed.editing) cancelEdit();
  to.push({draft: ed.draft, pages: ed.pages});
  const st = from.pop(); ed.draft = st.draft; ed.pages = st.pages; ed.dirty = true; ed.scan = {};
  ed.page = Math.min(ed.page, ed.pages.length - 1);
  renderThumbs(); await loadPage(); updateUndo();
}

/* ---------- thumbnails & page operations ---------- */
function renderThumbs() {
  $('#peThumbs').innerHTML = ed.pages.map((p, i) => `<div class="pe-th ${i === ed.page ? 'on' : ''}" data-p="${i}">
    <img loading="lazy" src="/api/pdf/${ed.draft.id}/render/${i}?scale=0.26" style="aspect-ratio:${p.w}/${p.h}" alt="">
    <div class="no">${i + 1}</div><div class="ops">
    <button data-pop="rotate" title="Rotate page">${ic('refresh', 13)}</button>${i > 0 ? `<button data-pop="up" title="Move up">${ic('up', 13)}</button>` : ''}
    ${i < ed.pages.length - 1 ? `<button data-pop="down" title="Move down">${ic('chev', 13)}</button>` : ''}<button data-pop="dup" title="Duplicate page">${ic('copy', 13)}</button>
    ${ed.pages.length > 1 ? `<button data-pop="del" title="Delete page">${ic('trash', 13)}</button>` : ''}</div></div>`).join('')
    + '<button class="pe-addpage" id="peAddPage">+ Blank page</button>';
}
function refreshThumb(i) { const img = $(`#peThumbs .pe-th[data-p="${i}"] img`); if (img) img.src = `/api/pdf/${ed.draft.id}/render/${i}?scale=0.26`; }
function markThumb() { document.querySelectorAll('#peThumbs .pe-th').forEach(t => t.classList.toggle('on', +t.dataset.p === ed.page)); }
async function gotoPage(i) {
  if (ed.busy || i === ed.page || i < 0 || i >= ed.pages.length) return;
  if (ed.editing) await commitEdit();
  ed.page = i; computeBase(); await loadPage();
  $(`#peThumbs .pe-th[data-p="${i}"]`)?.scrollIntoView({block: 'nearest'});
}
$('#peThumbs').addEventListener('click', e => {
  if (e.target.closest('#peAddPage')) return applyOps([{op: 'page_insert', after: ed.page}], {page: ed.page + 1, label: 'Adding page…'});
  const th = e.target.closest('.pe-th'); if (!th) return; const i = +th.dataset.p;
  const b = e.target.closest('[data-pop]');
  if (!b) return gotoPage(i);
  const a = b.dataset.pop;
  if (a === 'rotate') applyOps([{op: 'page_rotate', page: i, angle: 90}], {page: i});
  else if (a === 'up') applyOps([{op: 'page_move', page: i, to: i - 1}], {page: i - 1});
  else if (a === 'down') applyOps([{op: 'page_move', page: i, to: i + 1}], {page: i + 1});
  else if (a === 'dup') applyOps([{op: 'page_duplicate', page: i}], {page: i + 1});
  else if (a === 'del' && confirm(`Delete page ${i + 1}?`)) applyOps([{op: 'page_delete', page: i}], {page: Math.max(0, i - 1)});
});

/* ---------- tools & style props ---------- */
function setTool(t) {
  if (ed.editing) commitEdit();
  if (t !== 'place') { ed.placeFile = null; $('.pe-ghost')?.remove(); }
  if (t === 'image') { ed.fileMode = 'add'; $('#peFile').click(); return; }
  if (t === 'sign') { openSign(); return; }
  ed.tool = t; peOv.dataset.tool = t;
  document.querySelectorAll('#peTools button').forEach(b => b.classList.toggle('on', b.dataset.tool === t));
  if (t !== 'select') select(null); else renderSide();
}
$('#peTools').addEventListener('click', e => { const b = e.target.closest('[data-tool]'); if (b) setTool(b.dataset.tool); });
const props = () => ({color: $('#peColor').value, family: $('#peFamily').value, size: parseFloat($('#peSize').value) || 12,
  bold: $('#peBold').classList.contains('on'), italic: $('#peItalic').classList.contains('on')});
function setProps(p) {
  if (p.color) $('#peColor').value = /^#[0-9a-f]{6}$/i.test(p.color) ? p.color : '#111111';
  if (p.family) $('#peFamily').value = p.family;
  if (p.size) $('#peSize').value = +(+p.size).toFixed(1);
  $('#peBold').classList.toggle('on', !!p.bold); $('#peItalic').classList.toggle('on', !!p.italic);
}
function liveStyle() {
  const E = ed.editing; if (!E) return; const p = props(), s = S();
  Object.assign(E.el.style, {color: p.color, fontFamily: FAMCSS[p.family], fontSize: p.size * s + 'px', fontWeight: p.bold ? '700' : '400', fontStyle: p.italic ? 'italic' : 'normal'});
  if (!E.run) E.el.style.lineHeight = p.size * 1.2 * s + 'px';
}
['peColor', 'peFamily', 'peSize'].forEach(id => $('#' + id).addEventListener('input', liveStyle));
['peBold', 'peItalic'].forEach(id => $('#' + id).addEventListener('mousedown', e => { e.preventDefault(); $('#' + id).classList.toggle('on'); liveStyle(); }));

/* ---------- text editing ---------- */
function selectAll(el) { const r = document.createRange(); r.selectNodeContents(el); const s = getSelection(); s.removeAllRanges(); s.addRange(r); }
function bindEditKeys(el) {
  el.addEventListener('keydown', e => {
    e.stopPropagation();
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); commitEdit(); }
    else if (e.key === 'Escape') { e.preventDefault(); cancelEdit(); }
  });
  el.addEventListener('paste', e => { e.preventDefault(); document.execCommand('insertText', false, (e.clipboardData || window.clipboardData).getData('text/plain')); });
}
function startEdit(r) {
  if (ed.editing) commitEdit();
  select({type: 'run', r});
  const s = S(), el = document.createElement('div'), h = r.bbox[3] - r.bbox[1];
  el.className = 'pe-edit'; el.contentEditable = 'true'; el.spellcheck = false;
  Object.assign(el.style, {left: r.bbox[0] * s + 'px', top: r.bbox[1] * s + 'px', minWidth: (r.bbox[2] - r.bbox[0]) * s + 'px',
    lineHeight: h * s + 'px', background: r.bg || sampleBg(r.bbox)});
  el.textContent = r.text; peOv.appendChild(el);
  setProps(r); ed.editing = {el, run: r, start: props()}; liveStyle();
  bindEditKeys(el); el.focus(); selectAll(el);
}
function startAdd(p) {
  const s = S(), el = document.createElement('div');
  el.className = 'pe-edit'; el.contentEditable = 'true'; el.spellcheck = false;
  Object.assign(el.style, {left: p[0] * s + 'px', top: p[1] * s + 'px', background: 'rgba(255,255,255,.55)'});
  peOv.appendChild(el); ed.editing = {el, run: null, at: p, start: props()}; liveStyle();
  bindEditKeys(el); setTimeout(() => el.focus(), 0);
}
function cancelEdit() { if (ed.editing) { ed.editing.el.remove(); ed.editing = null; } }
async function commitEdit() {
  const E = ed.editing; if (!E) return; ed.editing = null;
  const text = E.el.innerText.replace(/ /g, ' ').replace(/\n+$/, ''); E.el.remove();
  const p = props();
  if (E.run?.scan) {
    if (text === E.run.text && p.color === E.start.color) return;
    const r = E.run, op = {op: 'scan_text', page: ed.page, bbox: r.bbox, text, orig: r.text};
    if (p.color !== E.start.color) op.color = p.color;
    await applyOps([op], {label: 'Rewriting text in image…', onOk: () => { r.text = text; if (op.color) r.color = op.color; }});
  } else if (E.run) {
    const diff = ['color', 'family', 'size', 'bold', 'italic'].filter(k => String(p[k]) !== String(E.start[k]));
    if (text === E.run.text && !diff.length) return;
    const op = {op: 'edit_text', page: ed.page, bbox: E.run.bbox, text}; diff.forEach(k => op[k] = p[k]);
    await applyOps([op], {label: 'Updating text…'});
  } else if (text.trim()) {
    await applyOps([{op: 'add_text', page: ed.page, x: E.at[0], y: E.at[1] + p.size * 0.88, text, size: p.size, color: p.color,
      family: p.family, bold: p.bold, italic: p.italic}], {label: 'Adding text…'});
  }
}

/* ---------- pointer interactions ---------- */
peOv.addEventListener('pointerdown', e => {
  if (ed.busy || e.button > 0 || e.target.closest('.pe-edit')) return;
  if (ed.editing) { e.preventDefault(); commitEdit(); return; }
  const p = toPdf(e), t = ed.tool, runEl = e.target.closest('.pe-run'), imgEl = e.target.closest('.pe-img');
  if (t === 'text') { if (runEl) { e.preventDefault(); startEdit(runOf(runEl)); } else { e.preventDefault(); startAdd(p); } return; }
  if (t === 'select') {
    if (imgEl) { e.preventDefault(); select({type: 'img', m: imgOf(imgEl)}); startDrag(e, imgEl, e.target.classList.contains('h')); return; }
    if (runEl) { select({type: 'run', r: runOf(runEl)}); return; }
    return select(null);
  }
  e.preventDefault();
  if (t === 'addtext') startAdd(p);
  else if (t === 'draw') startInk(p);
  else if (t === 'magic') startMagic(p);
  else if (['highlight', 'shape', 'erase'].includes(t)) startRubber(p, t);
  else if (t === 'place') placeImage(p);
});
peOv.addEventListener('dblclick', e => { const r = e.target.closest('.pe-run'); if (r && ed.tool === 'select') startEdit(runOf(r)); });
peOv.addEventListener('pointermove', e => {
  if (ed.tool !== 'place' || !ed.placeFile) return;
  let g = $('.pe-ghost');
  if (!g) { g = document.createElement('img'); g.className = 'pe-ghost'; g.src = `/api/thumb/${ed.placeFile.id}?size=400`; peOv.appendChild(g); }
  const p = toPdf(e), w = ed.placeW, h = w * ed.placeAR; place(g, [p[0] - w / 2, p[1] - h / 2, p[0] + w / 2, p[1] + h / 2], S());
});
function track(move, up) {
  const mv = ev => move(ev), u = ev => { removeEventListener('pointermove', mv); removeEventListener('pointerup', u); up(ev); };
  addEventListener('pointermove', mv); addEventListener('pointerup', u);
}
function startDrag(e, el, resize) {
  const s = S(), m = imgOf(el), b0 = [...m.bbox], sx = e.clientX, sy = e.clientY, ar = (b0[3] - b0[1]) / Math.max(1, b0[2] - b0[0]);
  let moved = false, nb = null;
  track(ev => {
    const dx = (ev.clientX - sx) / s, dy = (ev.clientY - sy) / s;
    if (Math.abs(dx) + Math.abs(dy) > 1.5) moved = true;
    if (resize) { const w = Math.max(8, b0[2] - b0[0] + dx); nb = [b0[0], b0[1], b0[0] + w, b0[1] + (ev.shiftKey ? Math.max(8, b0[3] - b0[1] + dy) : w * ar)]; }
    else nb = [b0[0] + dx, b0[1] + dy, b0[2] + dx, b0[3] + dy];
    place(el, nb, s);
  }, () => {
    if (moved && nb) { nb = nb.map(v => +v.toFixed(2)); applyOps([{op: 'move_image', page: ed.page, xref: m.xref, bbox: m.bbox, rect: nb}], {reselect: nb, label: resize ? 'Resizing…' : 'Moving…'}); }
  });
}
function startInk(p) {
  const s = S(), dpr = Math.min(devicePixelRatio || 1, 2), ctx = peInk.getContext('2d'), pr = props(), w = Math.max(0.6, pr.size / 6), pts = [p];
  ctx.setTransform(dpr * s, 0, 0, dpr * s, 0, 0); Object.assign(ctx, {strokeStyle: pr.color, lineWidth: w, lineCap: 'round', lineJoin: 'round'});
  ctx.beginPath(); ctx.moveTo(p[0], p[1]);
  track(ev => { const q = toPdf(ev), l = pts[pts.length - 1]; if (Math.hypot(q[0] - l[0], q[1] - l[1]) < 0.7) return; pts.push(q); ctx.lineTo(q[0], q[1]); ctx.stroke(); },
    async () => {
      if (pts.length > 1) await applyOps([{op: 'ink', page: ed.page, points: pts.map(q => [+q[0].toFixed(2), +q[1].toFixed(2)]), color: pr.color, width: w}], {label: 'Saving drawing…'});
      ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, peInk.width, peInk.height);
    });
}
function startMagic(p) {
  const s = S(), dpr = Math.min(devicePixelRatio || 1, 2), ctx = peInk.getContext('2d'), r = ed.magicR, pts = [p];
  ctx.setTransform(dpr * s, 0, 0, dpr * s, 0, 0);
  Object.assign(ctx, {strokeStyle: 'rgba(168,85,247,.55)', fillStyle: 'rgba(168,85,247,.55)', lineWidth: r * 2, lineCap: 'round', lineJoin: 'round'});
  ctx.globalCompositeOperation = 'copy'; ctx.beginPath(); ctx.arc(p[0], p[1], r, 0, 7); ctx.fill(); ctx.globalCompositeOperation = 'source-over';
  const redraw = () => { ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, peInk.width, peInk.height); ctx.restore();
    ctx.beginPath(); ctx.moveTo(pts[0][0], pts[0][1]); pts.forEach(q => ctx.lineTo(q[0], q[1])); if (pts.length === 1) ctx.lineTo(p[0] + .01, p[1]); ctx.stroke(); };
  redraw();
  track(ev => { const q = toPdf(ev), l = pts[pts.length - 1]; if (Math.hypot(q[0] - l[0], q[1] - l[1]) < Math.max(1, r / 4)) return; pts.push(q); redraw(); },
    async () => {
      await applyOps([{op: 'magic_erase', page: ed.page, points: pts.map(q => [+q[0].toFixed(2), +q[1].toFixed(2)]), radius: +r.toFixed(2)}], {label: 'Magic erasing… rebuilding the background'});
      ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, peInk.width, peInk.height);
    });
}
function startRubber(p, t) {
  const s = S(), el = document.createElement('div'); el.className = 'pe-rubber';
  if (t === 'highlight') el.style.background = 'rgba(250,204,21,.35)';
  if (t === 'erase') el.style.background = 'rgba(255,255,255,.75)';
  peOv.appendChild(el); let raw = [p[0], p[1], p[0], p[1]];
  track(ev => { const q = toPdf(ev); raw = [p[0], p[1], q[0], q[1]]; place(el, norm(raw), s); }, () => {
    el.remove(); const b = norm(raw).map(v => +v.toFixed(2));
    if (b[2] - b[0] < 3 && b[3] - b[1] < 3) return;
    if (t === 'highlight') applyOps([{op: 'highlight', page: ed.page, rect: b, color: ed.hl}], {label: 'Highlighting…'});
    else if (t === 'erase') applyOps([{op: 'erase', page: ed.page, rect: b}], {label: 'Erasing…'});
    else applyOps([{op: 'shape', page: ed.page, kind: ed.shape.kind, rect: ed.shape.kind === 'line' ? raw.map(v => +v.toFixed(2)) : b,
      color: props().color, width: ed.shape.width, fill: ed.shape.fill ? ed.shape.fillColor : null}], {label: 'Drawing…'});
  });
}

/* ---------- images: add / place / replace ---------- */
const arOf = f => { const d = (f.meta?.dims || '').split('×').map(Number); return d.length === 2 && d[0] ? d[1] / d[0] : 1; };
$('#peFile').onchange = async e => {
  const files = e.target.files; if (!files.length) return; e.target.value = '';
  showBusy('Uploading…'); const [f] = await uploadFiles(files, false); hideBusy();
  if (!f || f.status !== 'ready' || f.kind !== 'image') return toast('That file isn\'t a usable image', 'err');
  if (ed.fileMode === 'replace' && ed.sel?.type === 'img') {
    const m = ed.sel.m; return applyOps([{op: 'replace_image', page: ed.page, xref: m.xref, bbox: m.bbox, file_id: f.id}], {reselect: m.bbox, label: 'Replacing image…'});
  }
  startPlace(f, ed.fileMode === 'sign' ? 150 : Math.min(ed.pages[ed.page].w * 0.4, 240));
};
function startPlace(f, w) {
  ed.placeFile = f; ed.placeW = w; ed.placeAR = arOf(f);
  ed.tool = 'place'; peOv.dataset.tool = 'place';
  document.querySelectorAll('#peTools button').forEach(b => b.classList.remove('on'));
  toast('Click on the page where it should go'); renderSide();
}
function placeImage(p) {
  const f = ed.placeFile; if (!f) return;
  const w = ed.placeW, h = w * ed.placeAR, r = [p[0] - w / 2, p[1] - h / 2, p[0] + w / 2, p[1] + h / 2].map(v => +v.toFixed(2));
  ed.placeFile = null; $('.pe-ghost')?.remove(); setTool('select');
  applyOps([{op: 'add_image', page: ed.page, file_id: f.id, rect: r}], {reselect: r, label: 'Placing image…'});
}

/* ---------- signature pad ---------- */
const sig = $('#sigPad'); let sigCtx = null, sigBox = null, sigOn = false;
function openSign() {
  $('#signModal').classList.remove('hidden');
  const r = sig.getBoundingClientRect(), dpr = Math.min(devicePixelRatio || 1, 2);
  sig.width = r.width * dpr; sig.height = r.height * dpr; sigCtx = sig.getContext('2d'); sigCtx.scale(dpr, dpr);
  Object.assign(sigCtx, {lineCap: 'round', lineJoin: 'round', lineWidth: 2.8}); sigBox = null;
}
const sigPos = e => { const r = sig.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
const grow = (p) => { sigBox = sigBox ? [Math.min(sigBox[0], p[0]), Math.min(sigBox[1], p[1]), Math.max(sigBox[2], p[0]), Math.max(sigBox[3], p[1])] : [p[0], p[1], p[0], p[1]]; };
sig.addEventListener('pointerdown', e => { sigOn = true; const p = sigPos(e); sigCtx.strokeStyle = $('#sigColor').value; sigCtx.beginPath(); sigCtx.moveTo(...p); grow(p); sig.setPointerCapture(e.pointerId); });
sig.addEventListener('pointermove', e => { if (!sigOn) return; const p = sigPos(e); sigCtx.lineTo(...p); sigCtx.stroke(); grow(p); });
sig.addEventListener('pointerup', () => sigOn = false);
$('#sigClear').onclick = () => { sigCtx.clearRect(0, 0, sig.width, sig.height); sigBox = null; };
$('#signClose').onclick = () => $('#signModal').classList.add('hidden');
$('#sigUpload').onclick = () => { $('#signModal').classList.add('hidden'); ed.fileMode = 'sign'; $('#peFile').click(); };
$('#sigUse').onclick = async () => {
  if (!sigBox) return toast('Draw your signature first ✍️');
  const dpr = sig.width / sig.getBoundingClientRect().width, pad = 6;
  const x = Math.max(0, (sigBox[0] - pad) * dpr), y = Math.max(0, (sigBox[1] - pad) * dpr);
  const w = Math.min(sig.width - x, (sigBox[2] - sigBox[0] + pad * 2) * dpr), h = Math.min(sig.height - y, (sigBox[3] - sigBox[1] + pad * 2) * dpr);
  const c = document.createElement('canvas'); c.width = w; c.height = h; c.getContext('2d').drawImage(sig, x, y, w, h, 0, 0, w, h);
  const blob = await new Promise(r => c.toBlob(r, 'image/png'));
  $('#signModal').classList.add('hidden'); showBusy('Preparing signature…');
  const [f] = await uploadFiles([new File([blob], 'signature.png', {type: 'image/png'})], false); hideBusy();
  if (f?.status === 'ready') startPlace(f, 150); else toast('Signature upload failed', 'err');
};

/* ---------- inspector panel ---------- */
function renderSide() {
  const sel = ed.sel, t = ed.tool; let h = '';
  if (sel?.type === 'img') {
    const m = sel.m, b = m.bbox;
    h = `<h4>Image ${m.index}</h4><div class="muted">${Math.round(b[2] - b[0])} × ${Math.round(b[3] - b[1])} pt on page${m.w ? ` · ${m.w}×${m.h}px` : ''}</div>
      ${m.xref ? `<img class="prev" src="/api/pdf/${ed.draft.id}/image/${m.xref}" alt="">` : ''}
      <div class="grid"><button class="btn wide" data-se="ocr">${ic('type', 14)}Edit text in this image</button><button class="btn" data-se="replace">${ic('refresh', 14)}Replace</button>
      ${m.xref ? `<a class="btn" href="/api/pdf/${ed.draft.id}/image/${m.xref}" download="image.png">${ic('download', 14)}Download</a>` : '<span></span>'}
      <button class="btn" data-se="center">Center</button><button class="btn danger" data-se="delimg">${ic('trash', 14)}Delete</button></div>
      <div class="sec">Adjust image</div><div class="grid">${IMG_FX.map(([k, l]) => `<button class="btn" data-fx="${k}">${l}</button>`).join('')}</div>
      <div class="muted" style="margin-top:12px">Drag to move · corner handle resizes (hold Shift to stretch) · <kbd>Del</kbd> deletes</div>`;
  } else if (sel?.type === 'run' && sel.r.scan) {
    const r = sel.r;
    h = `<h4>Text in image</h4><div class="muted" style="margin:6px 0;color:var(--text)">“${esc(r.text)}”</div>
      <div class="muted">Read with OCR. When you change it, Meow wipes the old letters, rebuilds the background and redraws your text in the closest matching font, size and colour.</div>
      <div class="grid"><button class="btn wide" data-se="edit">${ic('type', 14)}Edit text</button><button class="btn danger wide" data-se="scanerase">${ic('eraser', 14)}Remove text</button></div>
      <div class="muted" style="margin-top:12px">Tip: if OCR misread a letter, just type the whole line correctly. Colour can be changed in the toolbar; the font is matched automatically.</div>`;
  } else if (sel?.type === 'run') {
    const r = sel.r;
    h = `<h4>Text</h4><div class="muted" style="margin:6px 0;color:var(--text)">“${esc(r.text)}”</div>
      <div class="muted">${esc((r.font || '').split('+').pop())} · ${+r.size.toFixed(1)}pt · ${r.family}${r.bold ? ' · bold' : ''}${r.italic ? ' · italic' : ''}</div>
      <div class="grid"><button class="btn wide" data-se="edit">${ic('type', 14)}Edit text</button><button class="btn danger wide" data-se="deltext">${ic('trash', 14)}Delete text</button></div>
      <div class="muted" style="margin-top:12px">While editing you can change colour, font, size, bold and italic in the toolbar. New text keeps the original font when possible. <kbd>Enter</kbd> saves · <kbd>Shift+Enter</kbd> new line · <kbd>Esc</kbd> cancels.</div>`;
  } else if (t === 'shape') {
    const sh = ed.shape;
    h = `<h4>Shape</h4><div class="muted">Drag on the page to draw. Stroke colour comes from the toolbar.</div>
      <div class="row"><label>Type</label><select class="inp" id="shKind">${['rect', 'ellipse', 'line'].map(k => `<option ${k === sh.kind ? 'selected' : ''}>${k}</option>`).join('')}</select></div>
      <div class="row"><label>Line width</label><input class="inp" id="shW" type="number" min="0.5" step="0.5" value="${sh.width}"></div>
      <div class="row"><label>Fill</label><input type="checkbox" id="shFill" ${sh.fill ? 'checked' : ''}><input type="color" id="shFillC" value="${sh.fillColor}"></div>`;
  } else if (t === 'magic') {
    h = `<h4>Magic eraser</h4><div class="muted">Paint over anything — a person, stamp, logo, watermark, scribble or words — and Meow rebuilds what was behind it with AI (GPU when free). Works on photos, screenshots and scans.</div>
      <div class="row"><label>Brush</label><input type="range" id="mgR" min="3" max="60" step="1" value="${ed.magicR}" style="flex:1"><span id="mgRv">${ed.magicR}</span></div>
      <div class="muted">Tip: cover the whole object plus a little margin. Two short strokes beat one huge one.</div>`;
  } else if (t === 'highlight') {
    h = `<h4>Highlight</h4><div class="muted">Drag across text to highlight it.</div><div class="row" style="flex-wrap:wrap">${['#facc15', '#4ade80', '#60a5fa', '#f472b6', '#fb923c'].map(c => `<button class="btn" data-hl="${c}" style="width:36px;height:36px;padding:0;background:${c};${c === ed.hl ? 'outline:2px solid #fff' : ''}"></button>`).join('')}</div>`;
  } else {
    const tips = {select: 'Click an image to move, resize, replace or adjust it. Double-click text to edit it.',
      text: 'Click any text to edit it in place, in its original font. Click empty space to add new text.',
      addtext: 'Click anywhere to type new text. Pick font, size and colour in the toolbar first.',
      draw: 'Draw freehand with the toolbar colour. Size controls pen thickness.',
      erase: 'Drag a box to permanently remove everything inside it (text, images, lines).',
      place: 'Click where the image should go. You can move and resize it afterwards.'};
    h = `<h4>${{select: 'Select', text: 'Edit text', addtext: 'Add text', draw: 'Draw', erase: 'Erase', place: 'Place image'}[t] || 'Editor'}</h4>
      <div class="muted">${tips[t] || ''}</div><div class="sec">Shortcuts</div>
      <div class="muted" style="line-height:1.9"><kbd>V</kbd> select · <kbd>E</kbd> edit text · <kbd>T</kbd> add text · <kbd>I</kbd> image<br><kbd>D</kbd> draw · <kbd>H</kbd> highlight · <kbd>R</kbd> shape · <kbd>X</kbd> erase · <kbd>M</kbd> magic · <kbd>S</kbd> sign<br><kbd>Ctrl Z</kbd> undo · <kbd>Ctrl Y</kbd> redo · <kbd>Del</kbd> delete · <kbd>Esc</kbd> close</div>
      <div class="sec">Ask Meow</div><div class="muted">You can also just tell Meow in chat — “replace the logo with this image”, “change the date to 16 Oct 2026”, “make page 2 photo black & white”.</div>`;
  }
  peSide.innerHTML = h;
  peSide.classList.toggle('empty', !sel && ['select', 'text'].includes(t));
}
peSide.addEventListener('click', e => {
  const hl = e.target.closest('[data-hl]'); if (hl) { ed.hl = hl.dataset.hl; return renderSide(); }
  const fx = e.target.closest('[data-fx]');
  if (fx && ed.sel?.type === 'img') { const m = ed.sel.m; return applyOps([{op: 'image_filter', page: ed.page, xref: m.xref, bbox: m.bbox, action: fx.dataset.fx}], {reselect: m.bbox, label: fx.textContent + '…'}); }
  const b = e.target.closest('[data-se]'); if (!b) return;
  const a = b.dataset.se, sel = ed.sel;
  if (a === 'replace') { ed.fileMode = 'replace'; $('#peFile').click(); }
  else if (a === 'delimg') delSelection();
  else if (a === 'center' && sel?.type === 'img') { const m = sel.m, pg = ed.pages[ed.page], w = m.bbox[2] - m.bbox[0], h = m.bbox[3] - m.bbox[1];
    const nb = [(pg.w - w) / 2, (pg.h - h) / 2, (pg.w + w) / 2, (pg.h + h) / 2].map(v => +v.toFixed(2));
    applyOps([{op: 'move_image', page: ed.page, xref: m.xref, bbox: m.bbox, rect: nb}], {reselect: nb, label: 'Centering…'}); }
  else if (a === 'edit' && sel?.type === 'run') startEdit(sel.r);
  else if (a === 'ocr' && sel?.type === 'img') runOcr(sel.m.bbox, false);
  else if (a === 'scanerase' && sel?.type === 'run') { const r = sel.r; applyOps([{op: 'scan_text', page: ed.page, bbox: r.bbox, text: '', orig: r.text}], {label: 'Removing text…', onOk: () => { ed.scan[ed.page] = (ed.scan[ed.page] || []).filter(b => b !== r); }}); }
  else if (a === 'deltext') delSelection();
});
peSide.addEventListener('input', e => {
  if (e.target.id === 'shKind') ed.shape.kind = e.target.value;
  if (e.target.id === 'mgR') { ed.magicR = parseFloat(e.target.value) || 10; const v = $('#mgRv'); if (v) v.textContent = ed.magicR; return; }
  if (e.target.id === 'shW') ed.shape.width = parseFloat(e.target.value) || 1.5;
  if (e.target.id === 'shFill') ed.shape.fill = e.target.checked;
  if (e.target.id === 'shFillC') ed.shape.fillColor = e.target.value;
});
function delSelection() {
  const s = ed.sel; if (!s) return;
  if (s.type === 'img') applyOps([{op: 'delete_image', page: ed.page, xref: s.m.xref, bbox: s.m.bbox}], {label: 'Deleting image…'});
  if (s.type === 'run' && s.r.scan) { const r = s.r; applyOps([{op: 'scan_text', page: ed.page, bbox: r.bbox, text: '', orig: r.text}], {label: 'Removing text…', onOk: () => { ed.scan[ed.page] = (ed.scan[ed.page] || []).filter(b => b !== r); }}); }
  else if (s.type === 'run') applyOps([{op: 'delete_text', page: ed.page, bbox: s.r.bbox}], {label: 'Deleting text…'});
}

/* ---------- top bar ---------- */
$('#peUndo').onclick = () => stepHistory(ed.undo, ed.redo);
$('#peRedo').onclick = () => stepHistory(ed.redo, ed.undo);
const zoomTo = z => { ed.zoom = Math.max(0.3, Math.min(4, z)); loadPage(); };
$('#peZoomIn').onclick = () => zoomTo(ed.zoom * 1.2);
$('#peZoomOut').onclick = () => zoomTo(ed.zoom / 1.2);
$('#peZoom').onclick = () => zoomTo(1);
$('#peClose').onclick = () => closeEditor(false);
$('#peDownload').onclick = async () => { if (ed.editing) await commitEdit(); if (ed.src.kind === 'image') return $('#peSave').click(); location.href = `/api/files/${ed.draft.id}?dl=1`; };
$('#peSave').onclick = async () => {
  if (ed.editing) await commitEdit();
  if (ed.busy) return;
  showBusy('Saving…');
  try {
    const isImg = ed.src.kind === 'image', stem = ed.src.name.replace(/\.[^.]+$/, '').replace(/_edited$/, '');
    const ext = isImg ? ((ed.src.name.split('.').pop() || 'png').toLowerCase().replace(/^(heic|heif|gif|bmp|tiff?)$/, 'jpg')) : 'pdf';
    const r = await api(`/api/pdf/${ed.draft.id}/${isImg ? 'save_image' : 'save'}`, {name: `${stem}_edited.${ext}`});
    const f = r.file;
    let chat = activeChat(); if (!chat) { chat = newChat('Edited ' + ed.src.name); activeId = chat.id; }
    if (!chat.fileIds.includes(f.id)) chat.fileIds.push(f.id);
    chat.messages.push({role: 'assistant', mode: 'fast', content: `Here's your edited ${isImg ? 'image' : 'PDF'}, **${f.name}** ✨ Open it again with ✏️ to keep editing, or tell me what else to change.`,
      tools: [{op: 'editor', status: 'ok', file: f, message: 'Edited in the editor · ' + metaStr(f)}]});
    chat.updated = Date.now(); save(); renderChatList(); renderChat();
    closeEditor(true); toast('Saved ' + f.name);
  } catch (e) { toast('Save failed: ' + e.message, 'err'); }
  finally { hideBusy(); }
};
let resizeT = null;
addEventListener('resize', () => { if (!edOpen()) return; clearTimeout(resizeT); resizeT = setTimeout(() => { computeBase(); loadPage(); }, 200); });
document.addEventListener('keydown', e => {
  if (!edOpen()) return;
  if (!$('#signModal').classList.contains('hidden')) { if (e.key === 'Escape') $('#signModal').classList.add('hidden'); e.stopImmediatePropagation(); return; }
  if (ed.editing) return;                                   // the text box handles its own keys
  if (/INPUT|SELECT|TEXTAREA/.test(document.activeElement?.tagName || '')) { if (e.key === 'Escape') document.activeElement.blur(); return; }
  e.stopImmediatePropagation();
  const k = e.key.toLowerCase(), mod = e.ctrlKey || e.metaKey;
  if (mod && k === 'z' && !e.shiftKey) { e.preventDefault(); stepHistory(ed.undo, ed.redo); }
  else if (mod && (k === 'y' || (k === 'z' && e.shiftKey))) { e.preventDefault(); stepHistory(ed.redo, ed.undo); }
  else if (mod) return;
  else if (k === 'delete' || k === 'backspace') { if (ed.sel) { e.preventDefault(); delSelection(); } }
  else if (k === 'escape') { if (ed.sel) select(null); else if (ed.tool === 'place') setTool('select'); else closeEditor(false); }
  else if (k === 'arrowright' || k === 'pagedown') gotoPage(ed.page + 1);
  else if (k === 'arrowleft' || k === 'pageup') gotoPage(ed.page - 1);
  else { const map = {v: 'select', e: 'text', t: 'addtext', i: 'image', d: 'draw', h: 'highlight', r: 'shape', x: 'erase', m: 'magic', s: 'sign'}; if (map[k]) setTool(map[k]); }
}, true);
