/**
 * StockEleK — Label Editor v2
 * Éditeur d'étiquettes WYSIWYG complet.
 *
 * Nouvelles fonctionnalités v2 :
 *   - Sélection multiple (Shift+clic, Ctrl+A, sélection par rectangle)
 *   - Alignement et distribution des blocs
 *   - Collage aux bords du canvas
 *   - Guides magnétiques (snap aux bords des autres blocs)
 *   - Règles en mm sur les bords
 *   - Zoom (molette, boutons, Ctrl+0)
 *   - Verrouillage proportions au resize (Shift)
 *   - Plusieurs layouts nommés
 *   - Templates fournis
 *   - Prix total (unit_price × quantity)
 *   - Export SVG/PNG
 *   - Minimap
 */
'use strict';

// ─────────────────────────────────────────────────────────────────────
//  CONSTANTES
// ─────────────────────────────────────────────────────────────────────
const GRID        = 1;
const MIN_W       = 3;
const MIN_H       = 2;
const HANDLE_PX   = 8;
const GUIDE_SNAP  = 2;    // distance en mm pour snap magnétique
const RULER_PX    = 20;   // largeur des règles en px
const ZOOM_MIN    = 0.5;
const ZOOM_MAX    = 5.0;
const ZOOM_STEP   = 0.15;

const BLOCK_TYPES = {
    text:      { label:'Texte',      icon:'T',  color:'#818cf8' },
    image:     { label:'Image',      icon:'🖼',  color:'#34d399' },
    qr:        { label:'QR Code',    icon:'▦',  color:'#60a5fa' },
    badge:     { label:'Badge',      icon:'🏷',  color:'#f59e0b' },
    separator: { label:'Séparateur', icon:'—',  color:'#94a3b8' },
    rect:      { label:'Rectangle',  icon:'□',  color:'#e879f9' },
};

const COMP_FIELDS = [
    { value:'description',             label:'Description courte' },
    { value:'description_long',        label:'Description longue' },
    { value:'manufacture_part_number', label:'MPN (Réf fabricant)' },
    { value:'manufacturer',            label:'Fabricant' },
    { value:'lcsc_part_number',        label:'Réf LCSC' },
    { value:'mouser_part_number',      label:'Réf Mouser' },
    { value:'digikey_part_number',     label:'Réf DigiKey' },
    { value:'package',                 label:'Package / Boîtier' },
    { value:'category',                label:'Catégorie' },
    { value:'quantity',                label:'Quantité en stock' },
    { value:'unit_price',              label:'Prix unitaire' },
    { value:'total_price',             label:'Valeur totale (prix × qté)' },
    { value:'location',                label:'Emplacement' },
    { value:'notes',                   label:'Notes' },
    { value:'rohs',                    label:'Statut RoHS' },
    { value:'custom',                  label:'Texte libre…' },
];

const BADGE_FIELDS = [
    { value:'package',  label:'Package',     default_bg:'#ebebeb' },
    { value:'rohs',     label:'RoHS',        default_bg:'#d4f0dd' },
    { value:'quantity', label:'Quantité',    default_bg:'#d0e8ff' },
    { value:'location', label:'Emplacement', default_bg:'#fff3cc' },
    { value:'category', label:'Catégorie',   default_bg:'#efe8ff' },
    { value:'lcsc',     label:'Réf LCSC',    default_bg:'#e0e7ff' },
    { value:'price',    label:'Prix unitaire',default_bg:'#fce7f3' },
    { value:'total',    label:'Valeur totale',default_bg:'#fce7f3' },
    { value:'custom',   label:'Texte libre…', default_bg:'#f0f0f0' },
];

// Templates fournis
const BUILT_IN_TEMPLATES = {
    tiroir_simple: {
        label:'🗄️ Tiroir simple',
        canvas:{w:60,h:25,bg:'#ffffff'},
        blocks:[
            {id:'t1',type:'image',   x:0,  y:0,  w:12,h:13,fit:'contain',bg:'#f8f8f8',border:false,border_radius:0,opacity:1},
            {id:'t2',type:'text',    x:13, y:0,  w:35,h:6, field:'description',font_size:2.8,font_weight:'bold',color:'#111',align:'left',font_family:'Arial',line_clamp:2,opacity:1},
            {id:'t3',type:'text',    x:13, y:6.5,w:22,h:3, field:'manufacture_part_number',font_size:1.8,font_weight:'normal',color:'#555',align:'left',font_family:'Courier New',line_clamp:1,opacity:1},
            {id:'t4',type:'badge',   x:13, y:10, w:10,h:3.5,field:'package',bg:'#ebebeb',color:'#333',font_size:1.5,border_radius:1,font_weight:'600',prefix:''},
            {id:'t5',type:'badge',   x:24, y:10, w:9, h:3.5,field:'quantity',bg:'#d0e8ff',color:'#1a5080',font_size:1.5,border_radius:1,font_weight:'600',prefix:''},
            {id:'t6',type:'qr',      x:48, y:0,  w:12,h:12,show_label:true,label_size:1.1,bg:'#fff',fg:'#000'},
            {id:'t7',type:'badge',   x:0,  y:14, w:60,h:3.5,field:'location',bg:'#fff3cc',color:'#7a5a00',font_size:1.5,border_radius:1,font_weight:'600',prefix:'📍 '},
            {id:'t8',type:'text',    x:48, y:13, w:12,h:3, field:'unit_price',font_size:1.4,font_weight:'normal',color:'#888',align:'center',font_family:'Arial',line_clamp:1,opacity:1},
        ]
    },
    tiroir_compact: {
        label:'📦 Tiroir compact',
        canvas:{w:40,h:20,bg:'#ffffff'},
        blocks:[
            {id:'c1',type:'text',  x:0,  y:0,  w:28,h:6, field:'description',font_size:2.5,font_weight:'bold',color:'#111',align:'left',font_family:'Arial',line_clamp:2,opacity:1},
            {id:'c2',type:'text',  x:0,  y:6.5,w:20,h:3, field:'lcsc_part_number',font_size:1.8,font_weight:'normal',color:'#4a90d9',align:'left',font_family:'Courier New',line_clamp:1,opacity:1},
            {id:'c3',type:'badge', x:0,  y:10.5,w:9,h:3.5,field:'package',bg:'#ebebeb',color:'#333',font_size:1.4,border_radius:1,font_weight:'600',prefix:''},
            {id:'c4',type:'badge', x:10, y:10.5,w:9,h:3.5,field:'quantity',bg:'#d0e8ff',color:'#1a5080',font_size:1.4,border_radius:1,font_weight:'600',prefix:''},
            {id:'c5',type:'qr',    x:29, y:0,  w:11,h:11,show_label:false,label_size:1,bg:'#fff',fg:'#000'},
            {id:'c6',type:'badge', x:0,  y:15, w:40,h:3.5,field:'location',bg:'#fff3cc',color:'#7a5a00',font_size:1.4,border_radius:1,font_weight:'600',prefix:'📍 '},
        ]
    },
    sachet: {
        label:'🛍️ Sachet composant',
        canvas:{w:50,h:30,bg:'#ffffff'},
        blocks:[
            {id:'s1',type:'rect',    x:0,  y:0,  w:50,h:10,bg:'#1e1b4b',border:false,border_radius:0,opacity:1},
            {id:'s2',type:'text',    x:1,  y:1.5,w:36,h:7, field:'description',font_size:3.2,font_weight:'bold',color:'#ffffff',align:'left',font_family:'Arial',line_clamp:2,opacity:1},
            {id:'s3',type:'image',   x:37, y:0,  w:10,h:10,fit:'contain',bg:'#1e1b4b',border:false,border_radius:0,opacity:1},
            {id:'s4',type:'text',    x:1,  y:11, w:30,h:4, field:'manufacturer',font_size:2.0,font_weight:'600',color:'#333',align:'left',font_family:'Arial',line_clamp:1,opacity:1},
            {id:'s5',type:'text',    x:1,  y:15.5,w:30,h:3,field:'manufacture_part_number',font_size:1.8,font_weight:'normal',color:'#555',align:'left',font_family:'Courier New',line_clamp:1,opacity:1},
            {id:'s6',type:'badge',   x:1,  y:19.5,w:10,h:3.5,field:'package',bg:'#ebebeb',color:'#333',font_size:1.5,border_radius:1,font_weight:'600',prefix:''},
            {id:'s7',type:'badge',   x:12, y:19.5,w:10,h:3.5,field:'rohs',bg:'#d4f0dd',color:'#065f46',font_size:1.5,border_radius:1,font_weight:'600',prefix:''},
            {id:'s8',type:'badge',   x:23, y:19.5,w:12,h:3.5,field:'quantity',bg:'#d0e8ff',color:'#1a5080',font_size:1.5,border_radius:1,font_weight:'600',prefix:'Qté: '},
            {id:'s9',type:'qr',      x:38, y:10, w:12,h:12,show_label:true,label_size:1.1,bg:'#fff',fg:'#000'},
            {id:'s10',type:'text',   x:1,  y:24, w:49,h:3, field:'location',font_size:1.8,font_weight:'600',color:'#7a5a00',align:'left',font_family:'Arial',line_clamp:1,opacity:1},
            {id:'s11',type:'badge',  x:0,  y:23.5,w:50,h:0,bg:'#fff3cc',color:'#7a5a00',font_size:1.5,border_radius:0,font_weight:'600',prefix:''},
        ]
    },
    minimal: {
        label:'✂️ Minimal (texte seul)',
        canvas:{w:40,h:15,bg:'#ffffff'},
        blocks:[
            {id:'m1',type:'text',  x:1,y:1,  w:38,h:7,field:'description',font_size:3.5,font_weight:'bold',color:'#111',align:'center',font_family:'Arial',line_clamp:2,opacity:1},
            {id:'m2',type:'text',  x:1,y:8.5,w:20,h:3,field:'manufacture_part_number',font_size:2.0,font_weight:'normal',color:'#555',align:'center',font_family:'Courier New',line_clamp:1,opacity:1},
            {id:'m3',type:'badge', x:22,y:8.5,w:10,h:3,field:'package',bg:'#ebebeb',color:'#333',font_size:1.6,border_radius:1,font_weight:'600',prefix:''},
        ]
    },
    boite: {
        label:'📫 Grande boîte',
        canvas:{w:100,h:50,bg:'#ffffff'},
        blocks:[
            {id:'g1',type:'rect',  x:0, y:0, w:100,h:18,bg:'#f8f8ff',border:true,border_color:'#e0e0f0',border_width:0.3,border_radius:0,opacity:1},
            {id:'g2',type:'image', x:1, y:1, w:16, h:16,fit:'contain',bg:'#f8f8ff',border:false,border_radius:2,opacity:1},
            {id:'g3',type:'text',  x:19,y:1, w:60, h:9, field:'description',font_size:4.5,font_weight:'bold',color:'#111',align:'left',font_family:'Arial',line_clamp:2,opacity:1},
            {id:'g4',type:'text',  x:19,y:10,w:40, h:5, field:'manufacturer',font_size:3.0,font_weight:'normal',color:'#555',align:'left',font_family:'Arial',line_clamp:1,opacity:1},
            {id:'g5',type:'qr',    x:80,y:1, w:18, h:16,show_label:true,label_size:1.5,bg:'#fff',fg:'#000'},
            {id:'g6',type:'text',  x:0, y:19,w:50, h:5, field:'manufacture_part_number',font_size:2.5,font_weight:'600',color:'#333',align:'left',font_family:'Courier New',line_clamp:1,opacity:1},
            {id:'g7',type:'badge', x:0, y:25,w:18, h:5, field:'package',bg:'#ebebeb',color:'#333',font_size:2.0,border_radius:1,font_weight:'600',prefix:''},
            {id:'g8',type:'badge', x:19,y:25,w:18, h:5, field:'quantity',bg:'#d0e8ff',color:'#1a5080',font_size:2.0,border_radius:1,font_weight:'600',prefix:'Qté: '},
            {id:'g9',type:'badge', x:38,y:25,w:18, h:5, field:'rohs',bg:'#d4f0dd',color:'#065f46',font_size:2.0,border_radius:1,font_weight:'600',prefix:''},
            {id:'g10',type:'separator',x:0,y:32,w:100,h:0.5,direction:'horizontal',color:'#dde',thickness:0.4,dash:false},
            {id:'g11',type:'text', x:0, y:33,w:100,h:5, field:'location',font_size:3.0,font_weight:'bold',color:'#7a5a00',align:'center',font_family:'Arial',line_clamp:1,opacity:1},
            {id:'g12',type:'text', x:0, y:39,w:100,h:5, field:'notes',font_size:2.2,font_weight:'normal',color:'#888',align:'left',font_family:'Arial',line_clamp:2,opacity:0.8},
        ]
    },
};

// ─────────────────────────────────────────────────────────────────────
//  STATE
// ─────────────────────────────────────────────────────────────────────
const STATE = {
    canvas:      { w:60, h:30, bg:'#ffffff' },
    blocks:      [],
    selected:    null,    // id unique ou null
    multiSel:    new Set(),  // sélection multiple (ids)
    drag:        null,
    resize:      null,
    selRect:     null,    // sélection par rectangle { startX,startY,curX,curY }
    scale:       4.0,
    zoom:        1.0,     // zoom supplémentaire (1 = 100%)
    _nextId:     1,
    previewComp: null,
    snapEnabled: true,
    guidesEnabled: true,
    rulersEnabled: true,
    guides:      [],      // guides magnétiques calculés en temps réel
};

let _historyStack = [];
let _historyIdx   = -1;

// Layouts nommés sauvegardés
let _namedLayouts = {};   // { nom: { canvas, blocks } }

// ─────────────────────────────────────────────────────────────────────
//  UTILS
// ─────────────────────────────────────────────────────────────────────
function uid()         { return 'b' + (STATE._nextId++); }
function mm2px(mm)     { return mm * STATE.scale * STATE.zoom; }
function px2mm(px)     { return px / (STATE.scale * STATE.zoom); }
function snap(mm)      { return STATE.snapEnabled ? Math.round(mm / GRID) * GRID : mm; }
function clamp(v,a,b)  { return Math.max(a, Math.min(b, v)); }
function deepClone(o)  { return JSON.parse(JSON.stringify(o)); }

function escHtml(s) {
    return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ─────────────────────────────────────────────────────────────────────
//  HISTORIQUE
// ─────────────────────────────────────────────────────────────────────
function historyPush() {
    _historyStack = _historyStack.slice(0, _historyIdx + 1);
    _historyStack.push(deepClone({ blocks:STATE.blocks, canvas:STATE.canvas }));
    _historyIdx = _historyStack.length - 1;
    if (_historyStack.length > 60) { _historyStack.shift(); _historyIdx--; }
    updateUndoRedoBtns();
}

function historyUndo() {
    if (_historyIdx <= 0) return;
    _historyIdx--;
    const s = _historyStack[_historyIdx];
    STATE.blocks = deepClone(s.blocks);
    STATE.canvas = deepClone(s.canvas);
    STATE.selected = null; STATE.multiSel.clear();
    renderAll(); updateUndoRedoBtns();
}

function historyRedo() {
    if (_historyIdx >= _historyStack.length - 1) return;
    _historyIdx++;
    const s = _historyStack[_historyIdx];
    STATE.blocks = deepClone(s.blocks);
    STATE.canvas = deepClone(s.canvas);
    STATE.selected = null; STATE.multiSel.clear();
    renderAll(); updateUndoRedoBtns();
}

function updateUndoRedoBtns() {
    const u = document.getElementById('le-undo-btn');
    const r = document.getElementById('le-redo-btn');
    if (u) u.disabled = _historyIdx <= 0;
    if (r) r.disabled = _historyIdx >= _historyStack.length - 1;
}

// ─────────────────────────────────────────────────────────────────────
//  MODÈLES DE BLOCS
// ─────────────────────────────────────────────────────────────────────
function makeBlock(type, x, y) {
    const base = { id:uid(), type, x, y, w:20, h:8, locked:false };
    switch (type) {
        case 'text':
            return { ...base, w:30, h:6, field:'description', custom_text:'',
                font_size:2.5, font_weight:'bold', color:'#111111', align:'left',
                font_family:'Arial', line_clamp:0, opacity:1.0 };
        case 'image':
            return { ...base, w:15, h:15, fit:'contain', border_radius:2,
                bg:'#f8f8f8', border:false, border_color:'#e8e8e8', opacity:1.0 };
        case 'qr':
            return { ...base, w:12, h:12, show_label:true, label_size:1.2,
                bg:'#ffffff', fg:'#000000' };
        case 'badge':
            return { ...base, w:16, h:4, field:'package', custom_text:'',
                bg:'#ebebeb', color:'#333333', font_size:1.6, border_radius:1,
                font_weight:'600', prefix:'' };
        case 'separator':
            return { ...base, w:30, h:0.5, direction:'horizontal',
                color:'#cccccc', thickness:0.5, dash:false };
        case 'rect':
            return { ...base, w:20, h:8, bg:'#f0f4ff', border:true,
                border_color:'#c7d2fe', border_width:0.3, border_radius:2, opacity:1.0 };
        default: return base;
    }
}

// ─────────────────────────────────────────────────────────────────────
//  RENDU PRINCIPAL
// ─────────────────────────────────────────────────────────────────────
function renderAll() {
    renderCanvas();
    renderPanel();
    renderLayerList();
    updatePreviewDebounced();
    updateZoomDisplay();
}

function renderCanvas() {
    const zone = document.getElementById('le-canvas-zone');
    const cvs  = document.getElementById('le-canvas');
    const wrap = document.getElementById('le-canvas-wrap');
    if (!cvs || !zone) return;

    const zW = zone.clientWidth  - RULER_PX - 32;
    const zH = zone.clientHeight - RULER_PX - 32;
    const baseScale = Math.min(zW / STATE.canvas.w, zH / STATE.canvas.h, 8.0);
    STATE.scale = baseScale;

    const cW = Math.round(mm2px(STATE.canvas.w));
    const cH = Math.round(mm2px(STATE.canvas.h));

    cvs.style.width  = cW + 'px';
    cvs.style.height = cH + 'px';
    cvs.style.background = STATE.canvas.bg;

    // Supprimer blocs existants
    cvs.querySelectorAll('.le-block,.le-guide,.le-sel-rect').forEach(e => e.remove());

    // Rendre blocs
    STATE.blocks.forEach((blk, idx) => {
        cvs.appendChild(renderBlock(blk, idx));
    });

    // Guides magnétiques
    if (STATE.guidesEnabled) renderGuides(cvs);

    // Rectangle de sélection
    if (STATE.selRect) renderSelRect(cvs);

    // Règles
    if (STATE.rulersEnabled) renderRulers();

    document.getElementById('le-canvas-dims').textContent =
        `${STATE.canvas.w} × ${STATE.canvas.h} mm  |  ${Math.round(STATE.zoom*100)}%`;
}

function renderBlock(blk, zIdx) {
    const isSel   = blk.id === STATE.selected || STATE.multiSel.has(blk.id);
    const isMulti = STATE.multiSel.size > 1 && STATE.multiSel.has(blk.id);

    const el = document.createElement('div');
    el.className  = 'le-block' + (isSel ? ' le-block--selected' : '') + (isMulti ? ' le-block--multi' : '');
    el.dataset.id = blk.id;
    el.style.cssText = `
        position:absolute;
        left:${mm2px(blk.x)}px; top:${mm2px(blk.y)}px;
        width:${mm2px(blk.w)}px; height:${mm2px(blk.h)}px;
        z-index:${zIdx + 1};
        cursor:${blk.locked ? 'default' : 'move'};
        user-select:none; overflow:hidden; box-sizing:border-box;
    `;

    el.innerHTML = renderBlockContent(blk);

    // Poignées resize si sélectionné (unique)
    if (blk.id === STATE.selected && !blk.locked && STATE.multiSel.size <= 1) {
        ['nw','n','ne','e','se','s','sw','w'].forEach(h => {
            const hEl = document.createElement('div');
            hEl.className = `le-handle le-handle--${h}`;
            hEl.dataset.handle = h; hEl.dataset.id = blk.id;
            el.appendChild(hEl);
        });
    }

    if (!blk.locked) el.addEventListener('mousedown', onBlockMouseDown, { passive:false });
    el.addEventListener('click', e => { e.stopPropagation(); handleBlockClick(e, blk.id); });

    return el;
}

// ─────────────────────────────────────────────────────────────────────
//  CONTENU DES BLOCS
// ─────────────────────────────────────────────────────────────────────
function renderBlockContent(blk) {
    const comp = STATE.previewComp || {};
    switch (blk.type) {
        case 'text': {
            const text = getFieldValue(blk, comp);
            const cl   = blk.line_clamp > 0
                ? `display:-webkit-box;-webkit-line-clamp:${blk.line_clamp};-webkit-box-orient:vertical;overflow:hidden;` : '';
            return `<div style="width:100%;height:100%;font-family:${blk.font_family||'Arial'},sans-serif;font-size:${mm2px(blk.font_size)}px;font-weight:${blk.font_weight||'normal'};color:${blk.color||'#111'};text-align:${blk.align||'left'};opacity:${blk.opacity||1};line-height:1.3;word-break:break-word;${cl}padding:1px 2px;">${escHtml(text)}</div>`;
        }
        case 'image': {
            const imgUrl = comp.image_url || '';
            const br     = mm2px(blk.border_radius||0) + 'px';
            const brd    = blk.border ? `1px solid ${blk.border_color||'#ccc'}` : 'none';
            if (imgUrl)
                return `<div style="width:100%;height:100%;background:${blk.bg||'#f8f8f8'};border-radius:${br};border:${brd};overflow:hidden;opacity:${blk.opacity||1};display:flex;align-items:center;justify-content:center;"><img src="${imgUrl}" style="max-width:100%;max-height:100%;object-fit:${blk.fit||'contain'};" onerror="this.style.display='none'"/></div>`;
            return `<div style="width:100%;height:100%;background:${blk.bg||'#f8f8f8'};border-radius:${br};border:${brd};display:flex;align-items:center;justify-content:center;opacity:.35;font-size:${mm2px(Math.min(blk.w,blk.h)*0.5)}px;">📦</div>`;
        }
        case 'qr': {
            const qrUrl = comp.qr_url || '';
            const lbl   = blk.show_label && comp.lcsc ? `<div style="font-size:${mm2px(blk.label_size||1.2)}px;color:#999;text-align:center;word-break:break-all;line-height:1.1;">${comp.lcsc||''}</div>` : '';
            if (qrUrl) return `<div style="width:100%;height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:1px;background:${blk.bg||'#fff'};"><img src="${qrUrl}" style="flex:1;min-height:0;max-width:100%;image-rendering:pixelated;"/>${lbl}</div>`;
            // Placeholder SVG QR
            return `<div style="width:100%;height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;background:${blk.bg||'#fff'};opacity:.5;font-size:${mm2px(Math.min(blk.w,blk.h)*0.5)}px;">▦</div>`;
        }
        case 'badge': {
            const text = getBadgeValue(blk, comp);
            if (!text) return `<div style="width:100%;height:100%;background:${blk.bg||'#eee'};border-radius:${mm2px(blk.border_radius||1)}px;display:flex;align-items:center;justify-content:center;font-size:${mm2px(blk.font_size||1.6)}px;color:#aaa;font-style:italic;">${blk.field}</div>`;
            return `<div style="width:100%;height:100%;background:${blk.bg||'#eee'};border-radius:${mm2px(blk.border_radius||1)}px;display:flex;align-items:center;justify-content:center;font-family:Arial,sans-serif;font-size:${mm2px(blk.font_size||1.6)}px;font-weight:${blk.font_weight||'600'};color:${blk.color||'#333'};padding:0 2px;white-space:nowrap;overflow:hidden;">${escHtml((blk.prefix||'')+text)}</div>`;
        }
        case 'separator': {
            const isH = blk.direction !== 'vertical';
            const dash = blk.dash ? 'dashed' : 'solid';
            return isH
                ? `<div style="width:100%;height:100%;display:flex;align-items:center;"><div style="width:100%;border-top:${mm2px(blk.thickness||0.5)}px ${dash} ${blk.color||'#ccc'};"></div></div>`
                : `<div style="height:100%;width:100%;display:flex;justify-content:center;"><div style="height:100%;border-left:${mm2px(blk.thickness||0.5)}px ${dash} ${blk.color||'#ccc'};"></div></div>`;
        }
        case 'rect':
            return `<div style="width:100%;height:100%;background:${blk.bg||'#f0f4ff'};border:${blk.border?`${mm2px(blk.border_width||0.3)}px solid ${blk.border_color||'#ccc'}`:'none'};border-radius:${mm2px(blk.border_radius||0)}px;opacity:${blk.opacity||1};"></div>`;
        default: return '';
    }
}

function getFieldValue(blk, comp) {
    if (blk.field === 'custom')      return blk.custom_text || '';
    if (blk.field === 'total_price') {
        const p = parseFloat(comp.unit_price)||0;
        const q = parseInt(comp.quantity)||0;
        return p > 0 ? (p*q).toFixed(4)+' €' : '';
    }
    if (blk.field === 'unit_price' && comp.unit_price)
        return parseFloat(comp.unit_price).toFixed(4) + ' €';
    if (blk.field === 'category' && comp.category)
        return String(comp.category).includes(' / ') ? String(comp.category).split(' / ').pop() : String(comp.category);
    const v = comp[blk.field];
    if (v === undefined || v === null) return blk.field === 'description' ? 'Composant…' : '';
    return String(v);
}

function getBadgeValue(blk, comp) {
    if (blk.field === 'custom')  return blk.custom_text || '';
    const map = {
        package:  comp.package,
        rohs:     comp.rohs === 'YES' ? 'RoHS' : null,
        quantity: comp.quantity != null ? String(comp.quantity) : null,
        location: comp.location || null,
        category: comp.category ? (String(comp.category).includes(' / ') ? String(comp.category).split(' / ').pop() : comp.category) : null,
        lcsc:     comp.lcsc_part_number,
        price:    comp.unit_price ? parseFloat(comp.unit_price).toFixed(4)+' €' : null,
        total:    (comp.unit_price && comp.quantity) ? (parseFloat(comp.unit_price)*parseInt(comp.quantity)).toFixed(2)+' €' : null,
    };
    return map[blk.field] || '';
}

// ─────────────────────────────────────────────────────────────────────
//  GUIDES MAGNÉTIQUES
// ─────────────────────────────────────────────────────────────────────
function computeGuides(movingId) {
    const guides = [];
    const moving = STATE.blocks.find(b => b.id === movingId);
    if (!moving) return guides;

    STATE.blocks.forEach(b => {
        if (b.id === movingId) return;
        // Bords et centres
        [b.x, b.x+b.w, b.x+b.w/2].forEach(gx => {
            guides.push({ axis:'v', pos:gx, src:b.id });
        });
        [b.y, b.y+b.h, b.y+b.h/2].forEach(gy => {
            guides.push({ axis:'h', pos:gy, src:b.id });
        });
    });
    // Bords du canvas
    [0, STATE.canvas.w, STATE.canvas.w/2].forEach(gx => guides.push({ axis:'v', pos:gx, src:'canvas' }));
    [0, STATE.canvas.h, STATE.canvas.h/2].forEach(gy => guides.push({ axis:'h', pos:gy, src:'canvas' }));

    return guides;
}

function snapToGuides(blk, dx, dy) {
    if (!STATE.guidesEnabled) return { dx, dy, activeGuides:[] };
    const guides    = computeGuides(blk.id);
    const threshold = GUIDE_SNAP;
    const active    = [];
    let   sdx = dx, sdy = dy;

    // Snap horizontal (axe V)
    const edges_x = [blk.x+dx, blk.x+dx+blk.w/2, blk.x+dx+blk.w];
    guides.filter(g => g.axis === 'v').forEach(g => {
        edges_x.forEach((ex, ei) => {
            const d = g.pos - ex;
            if (Math.abs(d) < threshold) {
                sdx = dx + d + (ei === 0 ? 0 : ei === 1 ? -blk.w/2 : -blk.w);
                active.push({ axis:'v', pos:g.pos });
            }
        });
    });
    // Snap vertical (axe H)
    const edges_y = [blk.y+dy, blk.y+dy+blk.h/2, blk.y+dy+blk.h];
    guides.filter(g => g.axis === 'h').forEach(g => {
        edges_y.forEach((ey, ei) => {
            const d = g.pos - ey;
            if (Math.abs(d) < threshold) {
                sdy = dy + d + (ei === 0 ? 0 : ei === 1 ? -blk.h/2 : -blk.h);
                active.push({ axis:'h', pos:g.pos });
            }
        });
    });

    return { dx:sdx, dy:sdy, activeGuides:active };
}

function renderGuides(cvs) {
    STATE.guides.forEach(g => {
        const el = document.createElement('div');
        el.className = 'le-guide';
        if (g.axis === 'v') {
            el.style.cssText = `position:absolute;left:${mm2px(g.pos)-0.5}px;top:0;width:1px;height:100%;background:rgba(124,58,237,.7);pointer-events:none;z-index:999;`;
        } else {
            el.style.cssText = `position:absolute;left:0;top:${mm2px(g.pos)-0.5}px;width:100%;height:1px;background:rgba(124,58,237,.7);pointer-events:none;z-index:999;`;
        }
        cvs.appendChild(el);
    });
}

// ─────────────────────────────────────────────────────────────────────
//  RÈGLES
// ─────────────────────────────────────────────────────────────────────
function renderRulers() {
    const hRuler = document.getElementById('le-ruler-h');
    const vRuler = document.getElementById('le-ruler-v');
    if (!hRuler || !vRuler) return;

    const W = STATE.canvas.w;
    const H = STATE.canvas.h;
    const step = W > 100 ? 10 : W > 40 ? 5 : 2;

    // Règle horizontale
    let hSvg = `<svg width="${mm2px(W)}" height="${RULER_PX}" style="overflow:visible">`;
    for (let x = 0; x <= W; x += step) {
        const px = mm2px(x);
        hSvg += `<line x1="${px}" y1="${RULER_PX-6}" x2="${px}" y2="${RULER_PX}" stroke="#4a5a6a" stroke-width="1"/>`;
        hSvg += `<text x="${px+1}" y="${RULER_PX-8}" fill="#4a5a6a" font-size="7" font-family="monospace">${x}</text>`;
    }
    hSvg += '</svg>';
    hRuler.innerHTML = hSvg;
    hRuler.style.width = mm2px(W) + 'px';

    // Règle verticale
    let vSvg = `<svg width="${RULER_PX}" height="${mm2px(H)}" style="overflow:visible">`;
    for (let y = 0; y <= H; y += step) {
        const py = mm2px(y);
        vSvg += `<line x1="${RULER_PX-6}" y1="${py}" x2="${RULER_PX}" y2="${py}" stroke="#4a5a6a" stroke-width="1"/>`;
        vSvg += `<text x="2" y="${py-1}" fill="#4a5a6a" font-size="7" font-family="monospace" transform="rotate(-90,2,${py})">${y}</text>`;
    }
    vSvg += '</svg>';
    vRuler.innerHTML = vSvg;
    vRuler.style.height = mm2px(H) + 'px';
}

// ─────────────────────────────────────────────────────────────────────
//  RECTANGLE DE SÉLECTION
// ─────────────────────────────────────────────────────────────────────
function renderSelRect(cvs) {
    const r   = STATE.selRect;
    if (!r) return;
    const x   = Math.min(r.startX, r.curX);
    const y   = Math.min(r.startY, r.curY);
    const w   = Math.abs(r.curX - r.startX);
    const h   = Math.abs(r.curY - r.startY);
    const el  = document.createElement('div');
    el.className = 'le-sel-rect';
    el.style.cssText = `position:absolute;left:${x}px;top:${y}px;width:${w}px;height:${h}px;border:1px dashed #7c3aed;background:rgba(124,58,237,.08);pointer-events:none;z-index:1000;`;
    cvs.appendChild(el);
}

// ─────────────────────────────────────────────────────────────────────
//  SÉLECTION
// ─────────────────────────────────────────────────────────────────────
function handleBlockClick(e, id) {
    e.stopPropagation();
    if (e.shiftKey || e.ctrlKey || e.metaKey) {
        // Multi-sélection
        if (STATE.multiSel.has(id)) {
            STATE.multiSel.delete(id);
            if (STATE.selected === id) STATE.selected = [...STATE.multiSel][0] || null;
        } else {
            if (STATE.selected) STATE.multiSel.add(STATE.selected);
            STATE.multiSel.add(id);
            STATE.selected = id;
        }
    } else {
        STATE.multiSel.clear();
        STATE.selected = id;
    }
    renderCanvas();
    renderPanel();
}

function selectBlock(id) {
    STATE.multiSel.clear();
    STATE.selected = id;
    renderCanvas();
    renderPanel();
}

function deselectAll() {
    STATE.selected = null;
    STATE.multiSel.clear();
    renderCanvas();
    renderPanel();
}

function selectAll() {
    STATE.multiSel = new Set(STATE.blocks.map(b => b.id));
    STATE.selected = STATE.blocks.length > 0 ? STATE.blocks[STATE.blocks.length-1].id : null;
    renderCanvas();
    renderPanel();
}

function deleteSelected() {
    if (!STATE.selected && STATE.multiSel.size === 0) return;
    historyPush();
    const toDelete = STATE.multiSel.size > 0 ? new Set(STATE.multiSel) : new Set([STATE.selected]);
    STATE.blocks = STATE.blocks.filter(b => !toDelete.has(b.id));
    STATE.selected = null; STATE.multiSel.clear();
    renderAll();
}

function duplicateSelected() {
    if (!STATE.selected && STATE.multiSel.size === 0) return;
    historyPush();
    const ids = STATE.multiSel.size > 0 ? [...STATE.multiSel] : [STATE.selected];
    const newIds = [];
    ids.forEach(id => {
        const src = STATE.blocks.find(b => b.id === id);
        if (!src) return;
        const clone = deepClone(src);
        clone.id = uid();
        clone.x  = snap(clone.x + 2);
        clone.y  = snap(clone.y + 2);
        STATE.blocks.push(clone);
        newIds.push(clone.id);
    });
    STATE.multiSel = new Set(newIds);
    STATE.selected = newIds[newIds.length-1] || null;
    renderAll();
}

function moveBlockZ(dir) {
    const idx = STATE.blocks.findIndex(b => b.id === STATE.selected);
    if (idx === -1) return;
    historyPush();
    if (dir==='up'     && idx < STATE.blocks.length-1) [STATE.blocks[idx],STATE.blocks[idx+1]] = [STATE.blocks[idx+1],STATE.blocks[idx]];
    else if (dir==='down'   && idx > 0)                [STATE.blocks[idx],STATE.blocks[idx-1]] = [STATE.blocks[idx-1],STATE.blocks[idx]];
    else if (dir==='top')    { const b=STATE.blocks.splice(idx,1)[0]; STATE.blocks.push(b); }
    else if (dir==='bottom') { const b=STATE.blocks.splice(idx,1)[0]; STATE.blocks.unshift(b); }
    renderAll();
}

// ─────────────────────────────────────────────────────────────────────
//  ALIGNEMENT & DISTRIBUTION
// ─────────────────────────────────────────────────────────────────────
function getSelBlocks() {
    const ids = STATE.multiSel.size > 1 ? STATE.multiSel : (STATE.selected ? new Set([STATE.selected]) : new Set());
    return STATE.blocks.filter(b => ids.has(b.id));
}

function alignBlocks(dir) {
    const sel = getSelBlocks();
    if (sel.length === 0) return;
    historyPush();

    if (sel.length === 1) {
        // Aligner sur le canvas
        const b = sel[0];
        if (dir==='left')   b.x = 0;
        if (dir==='right')  b.x = STATE.canvas.w - b.w;
        if (dir==='cx')     b.x = (STATE.canvas.w - b.w) / 2;
        if (dir==='top')    b.y = 0;
        if (dir==='bottom') b.y = STATE.canvas.h - b.h;
        if (dir==='cy')     b.y = (STATE.canvas.h - b.h) / 2;
    } else {
        // Aligner entre eux
        const minX  = Math.min(...sel.map(b => b.x));
        const maxX  = Math.max(...sel.map(b => b.x + b.w));
        const minY  = Math.min(...sel.map(b => b.y));
        const maxY  = Math.max(...sel.map(b => b.y + b.h));
        const midX  = (minX + maxX) / 2;
        const midY  = (minY + maxY) / 2;

        sel.forEach(b => {
            if (dir==='left')   b.x = minX;
            if (dir==='right')  b.x = maxX - b.w;
            if (dir==='cx')     b.x = midX - b.w/2;
            if (dir==='top')    b.y = minY;
            if (dir==='bottom') b.y = maxY - b.h;
            if (dir==='cy')     b.y = midY - b.h/2;
        });
    }
    renderAll();
}

function distributeBlocks(axis) {
    const sel = getSelBlocks();
    if (sel.length < 3) return;
    historyPush();

    if (axis === 'h') {
        const sorted = [...sel].sort((a,b) => a.x - b.x);
        const totalW = sorted.reduce((s,b) => s+b.w, 0);
        const span   = sorted[sorted.length-1].x + sorted[sorted.length-1].w - sorted[0].x;
        const gap    = (span - totalW) / (sorted.length - 1);
        let cx = sorted[0].x + sorted[0].w + gap;
        for (let i = 1; i < sorted.length-1; i++) {
            sorted[i].x = cx; cx += sorted[i].w + gap;
        }
    } else {
        const sorted = [...sel].sort((a,b) => a.y - b.y);
        const totalH = sorted.reduce((s,b) => s+b.h, 0);
        const span   = sorted[sorted.length-1].y + sorted[sorted.length-1].h - sorted[0].y;
        const gap    = (span - totalH) / (sorted.length - 1);
        let cy = sorted[0].y + sorted[0].h + gap;
        for (let i = 1; i < sorted.length-1; i++) {
            sorted[i].y = cy; cy += sorted[i].h + gap;
        }
    }
    renderAll();
}

// ─────────────────────────────────────────────────────────────────────
//  DRAG & RESIZE
// ─────────────────────────────────────────────────────────────────────
function onBlockMouseDown(e) {
    if (e.button !== 0) return;
    e.stopPropagation();
    e.preventDefault();

    const el  = e.currentTarget;
    const id  = el.dataset.id;
    const blk = STATE.blocks.find(b => b.id === id);
    if (!blk || blk.locked) return;

    if (e.target.classList.contains('le-handle')) {
        startResize(e, blk, e.target.dataset.handle);
        return;
    }

    // Sélection
    if (!STATE.multiSel.has(id)) {
        STATE.multiSel.clear();
        STATE.selected = id;
        renderCanvas(); renderPanel();
    }

    const movingIds = STATE.multiSel.size > 0 ? [...STATE.multiSel] : [id];
    const origPositions = {};
    movingIds.forEach(mid => {
        const b = STATE.blocks.find(b => b.id === mid);
        if (b) origPositions[mid] = { x:b.x, y:b.y };
    });

    historyPush();

    const onMove = e2 => {
        const dx = px2mm(e2.clientX - e.clientX);
        const dy = px2mm(e2.clientY - e.clientY);

        // Snap magnétique pour le bloc principal
        let sdx = dx, sdy = dy;
        if (movingIds.length === 1) {
            const snapped = snapToGuides(blk, snap(dx), snap(dy));
            sdx = snapped.dx; sdy = snapped.dy;
            STATE.guides = snapped.activeGuides;
        } else {
            sdx = snap(dx); sdy = snap(dy);
            STATE.guides = [];
        }

        movingIds.forEach(mid => {
            const b = STATE.blocks.find(b => b.id === mid);
            if (!b) return;
            b.x = clamp(origPositions[mid].x + sdx, 0, STATE.canvas.w - b.w);
            b.y = clamp(origPositions[mid].y + sdy, 0, STATE.canvas.h - b.h);
        });

        renderCanvas();
        if (movingIds.length === 1) {
            updateCoordDisplay(blk);
        }
    };

    const onUp = () => {
        STATE.guides = [];
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
        renderAll();
    };

    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
}

function startResize(e, blk, handle) {
    e.stopPropagation(); e.preventDefault();
    historyPush();

    const ratio = blk.w / blk.h;  // pour verrouillage proportions

    STATE.resize = { id:blk.id, handle,
        startX:e.clientX, startY:e.clientY,
        origX:blk.x, origY:blk.y, origW:blk.w, origH:blk.h };

    const onMove = e2 => {
        if (!STATE.resize) return;
        const dx   = px2mm(e2.clientX - STATE.resize.startX);
        const dy   = px2mm(e2.clientY - STATE.resize.startY);
        const r    = STATE.resize;
        const lock = e2.shiftKey;  // verrouiller proportions

        let nx=r.origX, ny=r.origY, nw=r.origW, nh=r.origH;

        if (handle.includes('e')) nw = Math.max(MIN_W, snap(r.origW+dx));
        if (handle.includes('s')) nh = Math.max(MIN_H, snap(r.origH+dy));
        if (handle.includes('w')) {
            const dw = snap(r.origW-dx);
            nx = clamp(r.origX+r.origW-Math.max(MIN_W,dw), 0, r.origX+r.origW-MIN_W);
            nw = r.origX+r.origW-nx;
        }
        if (handle.includes('n')) {
            const dh = snap(r.origH-dy);
            ny = clamp(r.origY+r.origH-Math.max(MIN_H,dh), 0, r.origY+r.origH-MIN_H);
            nh = r.origY+r.origH-ny;
        }

        // Verrouillage proportions (Shift)
        if (lock) {
            if (handle.includes('e') || handle.includes('w')) nh = nw / ratio;
            else nw = nh * ratio;
            nw = Math.max(MIN_W, nw); nh = Math.max(MIN_H, nh);
        }

        blk.x=nx; blk.y=ny; blk.w=nw; blk.h=nh;
        renderCanvas();
        updateSizeDisplay(blk);
    };

    const onUp = () => {
        STATE.resize = null;
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
        renderAll();
    };

    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
}

// Sélection par rectangle (depuis le canvas)
function startSelRect(e) {
    const cvs  = document.getElementById('le-canvas');
    const rect = cvs.getBoundingClientRect();
    const sx   = e.clientX - rect.left;
    const sy   = e.clientY - rect.top;

    STATE.selRect = { startX:sx, startY:sy, curX:sx, curY:sy };

    const onMove = e2 => {
        STATE.selRect.curX = e2.clientX - rect.left;
        STATE.selRect.curY = e2.clientY - rect.top;
        renderCanvas();
    };

    const onUp = () => {
        if (STATE.selRect) {
            const r   = STATE.selRect;
            const rx1 = px2mm(Math.min(r.startX, r.curX));
            const ry1 = px2mm(Math.min(r.startY, r.curY));
            const rx2 = px2mm(Math.max(r.startX, r.curX));
            const ry2 = px2mm(Math.max(r.startY, r.curY));

            STATE.multiSel.clear();
            STATE.blocks.forEach(b => {
                if (b.x < rx2 && b.x+b.w > rx1 && b.y < ry2 && b.y+b.h > ry1) {
                    STATE.multiSel.add(b.id);
                }
            });
            STATE.selected = [...STATE.multiSel][STATE.multiSel.size-1] || null;
            STATE.selRect = null;
            renderAll();
        }
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
    };

    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
}

function updateCoordDisplay(blk) {
    const el = document.getElementById('le-coord-display');
    if (el) el.textContent = `x:${blk.x.toFixed(1)} y:${blk.y.toFixed(1)} mm`;
}
function updateSizeDisplay(blk) {
    const el = document.getElementById('le-coord-display');
    if (el) el.textContent = `${blk.w.toFixed(1)} × ${blk.h.toFixed(1)} mm`;
}

// ─────────────────────────────────────────────────────────────────────
//  ZOOM
// ─────────────────────────────────────────────────────────────────────
function setZoom(z) {
    STATE.zoom = clamp(z, ZOOM_MIN, ZOOM_MAX);
    renderCanvas();
    updateZoomDisplay();
}

function zoomIn()    { setZoom(STATE.zoom + ZOOM_STEP); }
function zoomOut()   { setZoom(STATE.zoom - ZOOM_STEP); }
function zoomReset() { STATE.zoom = 1.0; renderCanvas(); updateZoomDisplay(); }

function updateZoomDisplay() {
    const el = document.getElementById('le-zoom-display');
    if (el) el.textContent = Math.round(STATE.zoom*100) + '%';
}

// Zoom molette
document.addEventListener('wheel', e => {
    const zone = document.getElementById('le-canvas-zone');
    if (!zone || !zone.contains(e.target)) return;
    if (!e.ctrlKey && !e.metaKey) return;
    e.preventDefault();
    setZoom(STATE.zoom + (e.deltaY < 0 ? ZOOM_STEP : -ZOOM_STEP));
}, { passive:false });

// ─────────────────────────────────────────────────────────────────────
//  PANEL PROPRIÉTÉS
// ─────────────────────────────────────────────────────────────────────
function renderPanel() {
    const panel = document.getElementById('le-panel-content');
    if (!panel) return;

    const multiCount = STATE.multiSel.size;

    if (multiCount > 1) {
        panel.innerHTML = renderMultiPanel();
        return;
    }
    if (!STATE.selected) {
        panel.innerHTML = renderCanvasPanel();
        return;
    }
    const blk = STATE.blocks.find(b => b.id === STATE.selected);
    if (!blk) { panel.innerHTML = ''; return; }
    panel.innerHTML = renderBlockPanel(blk);
}

function renderMultiPanel() {
    const sel = getSelBlocks();
    return `
    <div class="le-panel-section">
        <div class="le-panel-title">⊞ ${STATE.multiSel.size} blocs sélectionnés</div>
    </div>
    <div class="le-panel-section">
        <div class="le-panel-title">⬡ Aligner</div>
        <div class="le-align-grid">
            <button onclick="alignBlocks('left')"   title="Aligner à gauche">⬅</button>
            <button onclick="alignBlocks('cx')"     title="Centrer H">⬌</button>
            <button onclick="alignBlocks('right')"  title="Aligner à droite">➡</button>
            <button onclick="alignBlocks('top')"    title="Aligner en haut">⬆</button>
            <button onclick="alignBlocks('cy')"     title="Centrer V">⬍</button>
            <button onclick="alignBlocks('bottom')" title="Aligner en bas">⬇</button>
        </div>
        <div class="le-panel-title" style="margin-top:8px">↔ Distribuer</div>
        <div class="le-action-row">
            <button onclick="distributeBlocks('h')" title="Distribuer horizontalement">↔ Horizontal</button>
            <button onclick="distributeBlocks('v')" title="Distribuer verticalement">↕ Vertical</button>
        </div>
    </div>
    <div class="le-panel-section le-panel-actions">
        <div class="le-action-row">
            <button onclick="duplicateSelected()">⧉ Dupliquer tout</button>
            <button onclick="deleteSelected()" class="le-btn-danger">🗑 Supprimer tout</button>
        </div>
    </div>`;
}

function renderCanvasPanel() {
    return `
    <div class="le-panel-section">
        <div class="le-panel-title">📐 Format de l'étiquette</div>
        <div class="le-prop-row"><label>Largeur (mm)</label>
            <div class="le-stepper-sm">
                <button onclick="canvasStep('w',-1)">−</button>
                <input type="number" id="cp-w" value="${STATE.canvas.w}" min="10" max="200" step="1" oninput="updateCanvas()"/>
                <button onclick="canvasStep('w',+1)">+</button>
            </div></div>
        <div class="le-prop-row"><label>Hauteur (mm)</label>
            <div class="le-stepper-sm">
                <button onclick="canvasStep('h',-1)">−</button>
                <input type="number" id="cp-h" value="${STATE.canvas.h}" min="5" max="150" step="1" oninput="updateCanvas()"/>
                <button onclick="canvasStep('h',+1)">+</button>
            </div></div>
        <div class="le-prop-row"><label>Fond</label>
            <div class="le-color-row">
                <input type="color" id="cp-bg" value="${STATE.canvas.bg}" oninput="updateCanvas()"/>
                <span id="cp-bg-val">${STATE.canvas.bg}</span>
            </div></div>
    </div>
    <div class="le-panel-section">
        <div class="le-panel-title">⬡ Aligner (1 bloc sélectionné)</div>
        <div class="le-align-grid">
            <button onclick="alignBlocks('left')"   title="Coller à gauche">⬅</button>
            <button onclick="alignBlocks('cx')"     title="Centrer H">⬌</button>
            <button onclick="alignBlocks('right')"  title="Coller à droite">➡</button>
            <button onclick="alignBlocks('top')"    title="Coller en haut">⬆</button>
            <button onclick="alignBlocks('cy')"     title="Centrer V">⬍</button>
            <button onclick="alignBlocks('bottom')" title="Coller en bas">⬇</button>
        </div>
    </div>
    <div class="le-panel-section">
        <div class="le-panel-title">⚡ Formats prédéfinis</div>
        <div class="le-preset-list">
            ${Object.entries(LE_PRESETS||{}).map(([k,p]) =>
                `<button class="le-preset-btn" onclick="applyPreset(${p.w},${p.h})">${p.label}</button>`
            ).join('')}
        </div>
    </div>
    <div class="le-panel-section">
        <div class="le-panel-title">🔧 Options</div>
        <label class="le-checkbox-row">
            <input type="checkbox" ${STATE.snapEnabled?'checked':''} onchange="STATE.snapEnabled=this.checked"/> Snap grille ${GRID}mm
        </label>
        <label class="le-checkbox-row">
            <input type="checkbox" ${STATE.guidesEnabled?'checked':''} onchange="STATE.guidesEnabled=this.checked"/> Guides magnétiques
        </label>
        <label class="le-checkbox-row">
            <input type="checkbox" ${STATE.rulersEnabled?'checked':''} onchange="STATE.rulersEnabled=this.checked;renderCanvas()"/> Règles (mm)
        </label>
    </div>`;
}

function renderBlockPanel(blk) {
    const typeLabel = BLOCK_TYPES[blk.type]?.label || blk.type;
    let props = '';

    // Géométrie
    props += `
    <div class="le-panel-section">
        <div class="le-panel-title">📐 Géométrie <span style="font-size:.6rem;color:#3a4a5a;margin-left:4px">Shift+resize = proportions</span></div>
        <div class="le-prop-grid4">
            <div class="le-prop-row"><label>X</label><input type="number" class="le-num-sm" id="bp-x" value="${blk.x.toFixed(1)}" step="0.5" oninput="updateBlkGeo()"/></div>
            <div class="le-prop-row"><label>Y</label><input type="number" class="le-num-sm" id="bp-y" value="${blk.y.toFixed(1)}" step="0.5" oninput="updateBlkGeo()"/></div>
            <div class="le-prop-row"><label>L</label><input type="number" class="le-num-sm" id="bp-w" value="${blk.w.toFixed(1)}" min="1" step="0.5" oninput="updateBlkGeo()"/></div>
            <div class="le-prop-row"><label>H</label><input type="number" class="le-num-sm" id="bp-h" value="${blk.h.toFixed(1)}" min="1" step="0.5" oninput="updateBlkGeo()"/></div>
        </div>
        <div class="le-align-grid" style="margin-top:6px">
            <button onclick="alignBlocks('left')"   title="⬅">⬅</button>
            <button onclick="alignBlocks('cx')"     title="⬌">⬌</button>
            <button onclick="alignBlocks('right')"  title="➡">➡</button>
            <button onclick="alignBlocks('top')"    title="⬆">⬆</button>
            <button onclick="alignBlocks('cy')"     title="⬍">⬍</button>
            <button onclick="alignBlocks('bottom')" title="⬇">⬇</button>
        </div>
    </div>`;

    // Props spécifiques
    switch (blk.type) {
        case 'text': props += `
    <div class="le-panel-section">
        <div class="le-panel-title">✍️ Texte</div>
        <div class="le-prop-row"><label>Contenu</label>
            <select id="bp-field" onchange="updateBlk('field',this.value);renderPanel()">
                ${COMP_FIELDS.map(f=>`<option value="${f.value}" ${blk.field===f.value?'selected':''}>${f.label}</option>`).join('')}
            </select></div>
        ${blk.field==='custom'?`<div class="le-prop-row"><label>Texte</label><input type="text" value="${escHtml(blk.custom_text||'')}" oninput="updateBlk('custom_text',this.value)" placeholder="Texte libre…"/></div>`:''}
        <div class="le-prop-row"><label>Taille (mm)</label>
            <input type="number" class="le-num-sm" value="${blk.font_size}" min="0.5" max="20" step="0.1" oninput="updateBlkN('font_size',this.value)"/></div>
        <div class="le-prop-row"><label>Graisse</label>
            <select onchange="updateBlk('font_weight',this.value)">
                ${['normal','500','600','bold','900'].map(w=>`<option value="${w}" ${blk.font_weight===w?'selected':''}>${w}</option>`).join('')}
            </select></div>
        <div class="le-prop-row"><label>Police</label>
            <select onchange="updateBlk('font_family',this.value)">
                ${['Arial','Helvetica','Courier New','Georgia','Verdana','Tahoma','Times New Roman'].map(f=>`<option value="${f}" ${(blk.font_family||'Arial')===f?'selected':''}>${f}</option>`).join('')}
            </select></div>
        <div class="le-prop-row"><label>Couleur</label>
            <div class="le-color-row"><input type="color" value="${blk.color||'#111111'}" oninput="updateBlk('color',this.value)"/><span>${blk.color||'#111'}</span></div></div>
        <div class="le-prop-row"><label>Alignement</label>
            <div class="le-align-btns">
                ${['left','center','right'].map(a=>`<button class="${blk.align===a?'active':''}" onclick="updateBlk('align','${a}')">${a==='left'?'⬅':a==='center'?'⬛':'➡'}</button>`).join('')}
            </div></div>
        <div class="le-prop-row"><label>Lignes max</label>
            <input type="number" class="le-num-sm" value="${blk.line_clamp||0}" min="0" max="10" step="1" oninput="updateBlkN('line_clamp',this.value)" title="0 = illimité"/></div>
        <div class="le-prop-row"><label>Opacité</label>
            <input type="range" value="${(blk.opacity||1)*100}" min="10" max="100" step="5" oninput="updateBlkN('opacity',this.value/100)"/></div>
    </div>`; break;

        case 'image': props += `
    <div class="le-panel-section">
        <div class="le-panel-title">🖼️ Image</div>
        <div class="le-prop-row"><label>Ajustement</label>
            <select onchange="updateBlk('fit',this.value)">
                ${['contain','cover','fill'].map(f=>`<option value="${f}" ${blk.fit===f?'selected':''}>${f}</option>`).join('')}
            </select></div>
        <div class="le-prop-row"><label>Fond</label>
            <input type="color" value="${blk.bg||'#f8f8f8'}" oninput="updateBlk('bg',this.value)"/></div>
        <div class="le-prop-row"><label>Rayon (mm)</label>
            <input type="number" class="le-num-sm" value="${blk.border_radius||0}" min="0" max="20" step="0.5" oninput="updateBlkN('border_radius',this.value)"/></div>
        <label class="le-checkbox-row"><input type="checkbox" ${blk.border?'checked':''} onchange="updateBlk('border',this.checked)"/> Bordure</label>
        <div class="le-prop-row"><label>Couleur bord</label>
            <input type="color" value="${blk.border_color||'#e8e8e8'}" oninput="updateBlk('border_color',this.value)"/></div>
        <div class="le-prop-row"><label>Opacité</label>
            <input type="range" value="${(blk.opacity||1)*100}" min="10" max="100" step="5" oninput="updateBlkN('opacity',this.value/100)"/></div>
    </div>`; break;

        case 'qr': props += `
    <div class="le-panel-section">
        <div class="le-panel-title">▦ QR Code</div>
        <div class="le-prop-row"><label>Fond</label><input type="color" value="${blk.bg||'#ffffff'}" oninput="updateBlk('bg',this.value)"/></div>
        <div class="le-prop-row"><label>QR couleur</label><input type="color" value="${blk.fg||'#000000'}" oninput="updateBlk('fg',this.value)"/></div>
        <label class="le-checkbox-row"><input type="checkbox" ${blk.show_label?'checked':''} onchange="updateBlk('show_label',this.checked)"/> Afficher réf LCSC</label>
        <div class="le-prop-row"><label>Taille réf (mm)</label>
            <input type="number" class="le-num-sm" value="${blk.label_size||1.2}" min="0.5" max="5" step="0.1" oninput="updateBlkN('label_size',this.value)"/></div>
    </div>`; break;

        case 'badge': props += `
    <div class="le-panel-section">
        <div class="le-panel-title">🏷️ Badge</div>
        <div class="le-prop-row"><label>Champ</label>
            <select onchange="updateBlk('field',this.value);renderPanel()">
                ${BADGE_FIELDS.map(f=>`<option value="${f.value}" ${blk.field===f.value?'selected':''}>${f.label}</option>`).join('')}
            </select></div>
        ${blk.field==='custom'?`<div class="le-prop-row"><label>Texte</label><input type="text" value="${escHtml(blk.custom_text||'')}" oninput="updateBlk('custom_text',this.value)"/></div>`:''}
        <div class="le-prop-row"><label>Préfixe</label>
            <input type="text" value="${escHtml(blk.prefix||'')}" oninput="updateBlk('prefix',this.value)" placeholder="Ex: 📍 "/></div>
        <div class="le-prop-row"><label>Fond</label><input type="color" value="${blk.bg||'#ebebeb'}" oninput="updateBlk('bg',this.value)"/></div>
        <div class="le-prop-row"><label>Texte</label><input type="color" value="${blk.color||'#333333'}" oninput="updateBlk('color',this.value)"/></div>
        <div class="le-prop-row"><label>Taille (mm)</label>
            <input type="number" class="le-num-sm" value="${blk.font_size||1.6}" min="0.5" max="10" step="0.1" oninput="updateBlkN('font_size',this.value)"/></div>
        <div class="le-prop-row"><label>Rayon bord (mm)</label>
            <input type="number" class="le-num-sm" value="${blk.border_radius||1}" min="0" max="10" step="0.5" oninput="updateBlkN('border_radius',this.value)"/></div>
    </div>`; break;

        case 'separator': props += `
    <div class="le-panel-section">
        <div class="le-panel-title">— Séparateur</div>
        <div class="le-prop-row"><label>Direction</label>
            <select onchange="updateBlk('direction',this.value)">
                <option value="horizontal" ${blk.direction!=='vertical'?'selected':''}>Horizontal</option>
                <option value="vertical"   ${blk.direction==='vertical'?'selected':''}>Vertical</option>
            </select></div>
        <div class="le-prop-row"><label>Couleur</label><input type="color" value="${blk.color||'#cccccc'}" oninput="updateBlk('color',this.value)"/></div>
        <div class="le-prop-row"><label>Épaisseur (mm)</label>
            <input type="number" class="le-num-sm" value="${blk.thickness||0.5}" min="0.1" max="5" step="0.1" oninput="updateBlkN('thickness',this.value)"/></div>
        <label class="le-checkbox-row"><input type="checkbox" ${blk.dash?'checked':''} onchange="updateBlk('dash',this.checked)"/> Pointillés</label>
    </div>`; break;

        case 'rect': props += `
    <div class="le-panel-section">
        <div class="le-panel-title">□ Rectangle</div>
        <div class="le-prop-row"><label>Fond</label><input type="color" value="${blk.bg||'#f0f4ff'}" oninput="updateBlk('bg',this.value)"/></div>
        <div class="le-prop-row"><label>Opacité</label>
            <input type="range" value="${(blk.opacity||1)*100}" min="10" max="100" step="5" oninput="updateBlkN('opacity',this.value/100)"/></div>
        <label class="le-checkbox-row"><input type="checkbox" ${blk.border?'checked':''} onchange="updateBlk('border',this.checked)"/> Bordure</label>
        <div class="le-prop-row"><label>Couleur bord</label><input type="color" value="${blk.border_color||'#c7d2fe'}" oninput="updateBlk('border_color',this.value)"/></div>
        <div class="le-prop-row"><label>Épaisseur bord (mm)</label>
            <input type="number" class="le-num-sm" value="${blk.border_width||0.3}" min="0.1" max="5" step="0.1" oninput="updateBlkN('border_width',this.value)"/></div>
        <div class="le-prop-row"><label>Rayon coins (mm)</label>
            <input type="number" class="le-num-sm" value="${blk.border_radius||2}" min="0" max="20" step="0.5" oninput="updateBlkN('border_radius',this.value)"/></div>
    </div>`; break;
    }

    // Actions
    props += `
    <div class="le-panel-section le-panel-actions">
        <div class="le-panel-title">${BLOCK_TYPES[blk.type]?.icon||''} ${typeLabel} <span class="le-blk-id">${blk.id}</span></div>
        <div class="le-action-row">
            <button onclick="moveBlockZ('top')"    title="Premier plan">⤒</button>
            <button onclick="moveBlockZ('up')"     title="Monter">↑</button>
            <button onclick="moveBlockZ('down')"   title="Descendre">↓</button>
            <button onclick="moveBlockZ('bottom')" title="Arrière-plan">⤓</button>
        </div>
        <div class="le-action-row">
            <button onclick="duplicateSelected()">⧉ Dupliquer</button>
            <button onclick="deleteSelected()" class="le-btn-danger">🗑 Supprimer</button>
        </div>
        <label class="le-checkbox-row">
            <input type="checkbox" ${blk.locked?'checked':''} onchange="updateBlk('locked',this.checked)"/> Verrouiller position
        </label>
    </div>`;

    return props;
}

// ─────────────────────────────────────────────────────────────────────
//  MISE À JOUR PROPS
// ─────────────────────────────────────────────────────────────────────
function updateCanvas() {
    const w  = parseFloat(document.getElementById('cp-w')?.value) || STATE.canvas.w;
    const h  = parseFloat(document.getElementById('cp-h')?.value) || STATE.canvas.h;
    const bg = document.getElementById('cp-bg')?.value || STATE.canvas.bg;
    const v  = document.getElementById('cp-bg-val');
    if (v) v.textContent = bg;
    STATE.canvas.w  = Math.max(10, Math.min(200, w));
    STATE.canvas.h  = Math.max(5,  Math.min(150, h));
    STATE.canvas.bg = bg;
    renderAll();
}

function canvasStep(prop, delta) {
    const el = document.getElementById('cp-' + prop);
    if (el) { el.value = (parseFloat(el.value)||0) + delta; updateCanvas(); }
}

function applyPreset(w, h) {
    STATE.canvas.w = w; STATE.canvas.h = h;
    const cw = document.getElementById('cp-w');
    const ch = document.getElementById('cp-h');
    if (cw) cw.value = w;
    if (ch) ch.value = h;
    deselectAll(); renderAll();
}

function applyTemplate(key) {
    const tpl = BUILT_IN_TEMPLATES[key];
    if (!tpl) return;
    if (!confirm(`Appliquer le template "${tpl.label}" ? Le layout actuel sera remplacé.`)) return;
    historyPush();
    STATE.canvas = deepClone(tpl.canvas);
    STATE.blocks  = deepClone(tpl.blocks);
    STATE._nextId = Math.max(...tpl.blocks.map(b => parseInt(b.id.replace(/\D/g,''))||0), 0) + 1;
    STATE.selected = null; STATE.multiSel.clear();
    renderAll();
}

function updateBlk(prop, value) {
    const blk = STATE.blocks.find(b => b.id === STATE.selected);
    if (!blk) return;
    blk[prop] = value;
    renderCanvas(); updatePreviewDebounced();
}

function updateBlkN(prop, value) { updateBlk(prop, parseFloat(value)||0); }

function updateBlkGeo() {
    const blk = STATE.blocks.find(b => b.id === STATE.selected);
    if (!blk) return;
    const x = parseFloat(document.getElementById('bp-x')?.value); if (!isNaN(x)) blk.x = x;
    const y = parseFloat(document.getElementById('bp-y')?.value); if (!isNaN(y)) blk.y = y;
    const w = parseFloat(document.getElementById('bp-w')?.value); if (!isNaN(w)) blk.w = Math.max(MIN_W,w);
    const h = parseFloat(document.getElementById('bp-h')?.value); if (!isNaN(h)) blk.h = Math.max(MIN_H,h);
    renderCanvas(); updatePreviewDebounced();
}

// ─────────────────────────────────────────────────────────────────────
//  LISTE DES COUCHES
// ─────────────────────────────────────────────────────────────────────
function renderLayerList() {
    const list = document.getElementById('le-layers');
    if (!list) return;

    const hdr = document.getElementById('le-layers-header');
    if (hdr) hdr.textContent = `Couches (${STATE.blocks.length}) — glisser pour réordonner`;

    list.innerHTML = [...STATE.blocks].reverse().map(blk => {
        const type  = BLOCK_TYPES[blk.type] || {};
        const isSel = blk.id === STATE.selected || STATE.multiSel.has(blk.id);
        return `<div class="le-layer-item ${isSel?'le-layer-selected':''}" data-id="${blk.id}" onclick="selectBlock('${blk.id}')">
            <span class="le-layer-icon" style="color:${type.color||'#888'}">${type.icon||'?'}</span>
            <span class="le-layer-label">${type.label||blk.type}${blk.field?' · '+blk.field:''}</span>
            <span class="le-layer-dims">${blk.w.toFixed(0)}×${blk.h.toFixed(0)}</span>
            ${blk.locked?'<span>🔒</span>':''}
        </div>`;
    }).join('');

    list.querySelectorAll('.le-layer-item').forEach(item => {
        item.draggable = true;
        item.addEventListener('dragstart', e => e.dataTransfer.setData('text/plain', item.dataset.id));
        item.addEventListener('dragover',  e => { e.preventDefault(); item.classList.add('le-layer-over'); });
        item.addEventListener('dragleave', ()  => item.classList.remove('le-layer-over'));
        item.addEventListener('drop', e => {
            e.preventDefault(); item.classList.remove('le-layer-over');
            const fromId = e.dataTransfer.getData('text/plain');
            const toId   = item.dataset.id;
            if (fromId === toId) return;
            historyPush();
            const fi = STATE.blocks.findIndex(b => b.id === fromId);
            const ti = STATE.blocks.findIndex(b => b.id === toId);
            const [b] = STATE.blocks.splice(fi, 1);
            STATE.blocks.splice(ti, 0, b);
            renderAll();
        });
    });
}

// ─────────────────────────────────────────────────────────────────────
//  LAYOUTS NOMMÉS
// ─────────────────────────────────────────────────────────────────────
function saveNamedLayout() {
    const name = prompt('Nom du layout :', 'Mon étiquette');
    if (!name || !name.trim()) return;
    _namedLayouts[name.trim()] = deepClone({ canvas:STATE.canvas, blocks:STATE.blocks });
    persistNamedLayouts();
    renderLayoutsList();
    showToast(`Layout "${name}" sauvegardé`);
}

function loadNamedLayout(name) {
    const layout = _namedLayouts[name];
    if (!layout) return;
    if (!confirm(`Charger "${name}" ? Le layout actuel sera remplacé.`)) return;
    historyPush();
    STATE.canvas = deepClone(layout.canvas);
    STATE.blocks  = deepClone(layout.blocks);
    STATE._nextId = Math.max(...layout.blocks.map(b => parseInt(b.id.replace(/\D/g,''))||0), 0) + 1;
    STATE.selected = null; STATE.multiSel.clear();
    renderAll();
    showToast(`Layout "${name}" chargé`);
}

function deleteNamedLayout(name) {
    if (!confirm(`Supprimer le layout "${name}" ?`)) return;
    delete _namedLayouts[name];
    persistNamedLayouts();
    renderLayoutsList();
}

function persistNamedLayouts() {
    try { localStorage.setItem('le_named_layouts', JSON.stringify(_namedLayouts)); } catch(e){}
}

function loadPersistedLayouts() {
    try {
        const s = localStorage.getItem('le_named_layouts');
        if (s) _namedLayouts = JSON.parse(s);
    } catch(e) { _namedLayouts = {}; }
}

function renderLayoutsList() {
    const el = document.getElementById('le-layouts-list');
    if (!el) return;
    const names = Object.keys(_namedLayouts);
    if (names.length === 0) {
        el.innerHTML = '<div style="font-size:.65rem;color:#2a3a4a;padding:4px 0">Aucun layout sauvegardé</div>';
        return;
    }
    el.innerHTML = names.map(n =>
        `<div class="le-named-layout-item">
            <span onclick="loadNamedLayout('${escHtml(n)}')" title="Charger">${escHtml(n)}</span>
            <button onclick="deleteNamedLayout('${escHtml(n)}')" title="Supprimer">✕</button>
        </div>`
    ).join('');
}

// ─────────────────────────────────────────────────────────────────────
//  EXPORT SVG / PNG
// ─────────────────────────────────────────────────────────────────────
function exportSVG() {
    const W    = STATE.canvas.w;
    const H    = STATE.canvas.h;
    const SC   = 3.779528; // mm → px @96dpi

    let svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W*SC}px" height="${H*SC}px" viewBox="0 0 ${W*SC} ${H*SC}">`;
    svg += `<rect width="100%" height="100%" fill="${STATE.canvas.bg}"/>`;

    STATE.blocks.forEach(blk => {
        const x = blk.x*SC, y = blk.y*SC, w = blk.w*SC, h = blk.h*SC;
        switch (blk.type) {
            case 'rect':
                svg += `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${blk.bg||'#f0f4ff'}" opacity="${blk.opacity||1}" rx="${(blk.border_radius||0)*SC}"${blk.border?` stroke="${blk.border_color}" stroke-width="${(blk.border_width||0.3)*SC}"`:''}/>`;
                break;
            case 'separator':
                if (blk.direction === 'vertical')
                    svg += `<line x1="${x+w/2}" y1="${y}" x2="${x+w/2}" y2="${y+h}" stroke="${blk.color||'#ccc'}" stroke-width="${(blk.thickness||0.5)*SC}"${blk.dash?' stroke-dasharray="4,3"':''}/>`;
                else
                    svg += `<line x1="${x}" y1="${y+h/2}" x2="${x+w}" y2="${y+h/2}" stroke="${blk.color||'#ccc'}" stroke-width="${(blk.thickness||0.5)*SC}"${blk.dash?' stroke-dasharray="4,3"':''}/>`;
                break;
            case 'text': {
                const comp = STATE.previewComp || {};
                const text = getFieldValue(blk, comp);
                svg += `<text x="${x+1}" y="${y + blk.font_size*SC*0.85}" font-family="${blk.font_family||'Arial'}" font-size="${blk.font_size*SC}" font-weight="${blk.font_weight||'normal'}" fill="${blk.color||'#111'}" opacity="${blk.opacity||1}" text-anchor="${blk.align==='right'?'end':blk.align==='center'?'middle':'start'}">${escHtml(text)}</text>`;
                break;
            }
            case 'badge': {
                const comp = STATE.previewComp || {};
                const text = getBadgeValue(blk, comp);
                const br   = (blk.border_radius||1)*SC;
                svg += `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${blk.bg||'#eee'}" rx="${br}"/>`;
                svg += `<text x="${x+w/2}" y="${y+h/2+blk.font_size*SC*0.35}" font-family="Arial" font-size="${blk.font_size*SC}" font-weight="${blk.font_weight||'600'}" fill="${blk.color||'#333'}" text-anchor="middle">${escHtml((blk.prefix||'')+text)}</text>`;
                break;
            }
        }
    });

    svg += '</svg>';

    const blob = new Blob([svg], { type:'image/svg+xml' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url; a.download = 'etiquette.svg'; a.click();
    URL.revokeObjectURL(url);
    showToast('SVG exporté');
}

function exportPNG() {
    const SC   = 8;   // 8px/mm → haute résolution
    const W    = Math.round(STATE.canvas.w * SC);
    const H    = Math.round(STATE.canvas.h * SC);

    const canvas = document.createElement('canvas');
    canvas.width = W; canvas.height = H;
    const ctx = canvas.getContext('2d');

    // Fond
    ctx.fillStyle = STATE.canvas.bg;
    ctx.fillRect(0, 0, W, H);

    // Blocs (rendu simplifié texte + rect)
    STATE.blocks.forEach(blk => {
        const x = blk.x*SC, y = blk.y*SC, w = blk.w*SC, h = blk.h*SC;
        ctx.save();
        ctx.globalAlpha = blk.opacity || 1;

        switch (blk.type) {
            case 'rect':
                ctx.fillStyle = blk.bg || '#f0f4ff';
                if (blk.border_radius > 0) {
                    const r = blk.border_radius * SC;
                    ctx.beginPath();
                    ctx.roundRect(x,y,w,h,r);
                    ctx.fill();
                } else { ctx.fillRect(x,y,w,h); }
                if (blk.border) {
                    ctx.strokeStyle = blk.border_color || '#ccc';
                    ctx.lineWidth   = (blk.border_width||0.3) * SC;
                    ctx.strokeRect(x,y,w,h);
                }
                break;
            case 'badge': {
                const comp = STATE.previewComp || {};
                const text = (blk.prefix||'') + getBadgeValue(blk, comp);
                ctx.fillStyle = blk.bg || '#eee';
                const r = (blk.border_radius||1)*SC;
                ctx.beginPath(); ctx.roundRect(x,y,w,h,r); ctx.fill();
                ctx.fillStyle   = blk.color || '#333';
                ctx.font        = `${blk.font_weight||600} ${blk.font_size*SC}px ${blk.font_family||'Arial'}`;
                ctx.textAlign   = 'center';
                ctx.textBaseline= 'middle';
                ctx.fillText(text, x+w/2, y+h/2, w-4);
                break;
            }
            case 'text': {
                const comp = STATE.previewComp || {};
                const text = getFieldValue(blk, comp);
                ctx.fillStyle   = blk.color || '#111';
                ctx.font        = `${blk.font_weight||'normal'} ${blk.font_size*SC}px ${blk.font_family||'Arial'}`;
                ctx.textAlign   = blk.align || 'left';
                ctx.textBaseline= 'top';
                const tx = blk.align==='right' ? x+w : blk.align==='center' ? x+w/2 : x+2;
                ctx.fillText(text, tx, y+2, w-4);
                break;
            }
            case 'separator':
                ctx.strokeStyle = blk.color || '#ccc';
                ctx.lineWidth   = (blk.thickness||0.5) * SC;
                if (blk.dash) ctx.setLineDash([4,3]);
                ctx.beginPath();
                if (blk.direction==='vertical') { ctx.moveTo(x+w/2,y); ctx.lineTo(x+w/2,y+h); }
                else { ctx.moveTo(x,y+h/2); ctx.lineTo(x+w,y+h/2); }
                ctx.stroke();
                break;
        }
        ctx.restore();
    });

    canvas.toBlob(blob => {
        const url = URL.createObjectURL(blob);
        const a   = document.createElement('a');
        a.href = url; a.download = 'etiquette.png'; a.click();
        URL.revokeObjectURL(url);
        showToast('PNG exporté (' + W + '×' + H + 'px)');
    });
}

// ─────────────────────────────────────────────────────────────────────
//  PREVIEW IFRAME
// ─────────────────────────────────────────────────────────────────────
let _previewTimer = null;

function updatePreviewDebounced() {
    clearTimeout(_previewTimer);
    _previewTimer = setTimeout(updatePreview, 600);
}

function updatePreview() {
    const iframe  = document.getElementById('le-preview-iframe');
    if (!iframe || !window.LE_PREVIEW_ID) return;
    const layout  = JSON.stringify({ canvas:STATE.canvas, blocks:STATE.blocks });
    const loading = document.getElementById('le-preview-loading');
    if (loading) loading.style.display = 'flex';
    iframe.style.opacity = '0.4';
    iframe.src = `/labels/preview-layout/${LE_PREVIEW_ID}?layout=${encodeURIComponent(layout)}`;
}

function onPreviewLoaded() {
    const iframe  = document.getElementById('le-preview-iframe');
    const loading = document.getElementById('le-preview-loading');
    if (loading) loading.style.display = 'none';
    if (iframe)  iframe.style.opacity  = '1';
}

// ─────────────────────────────────────────────────────────────────────
//  TOAST NOTIFICATIONS
// ─────────────────────────────────────────────────────────────────────
function showToast(msg, duration) {
    let toast = document.getElementById('le-toast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'le-toast';
        toast.style.cssText = 'position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:#7c3aed;color:#fff;padding:8px 18px;border-radius:20px;font-size:.8rem;z-index:9999;pointer-events:none;transition:opacity .3s;white-space:nowrap;box-shadow:0 4px 16px rgba(0,0,0,.4)';
        document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.style.opacity = '1';
    clearTimeout(toast._t);
    toast._t = setTimeout(() => { toast.style.opacity = '0'; }, duration || 2000);
}

// ─────────────────────────────────────────────────────────────────────
//  AJOUT DE BLOCS
// ─────────────────────────────────────────────────────────────────────
function addBlock(type) {
    historyPush();
    const blk = makeBlock(type,
        snap(Math.max(0, STATE.canvas.w/2 - 10)),
        snap(Math.max(0, STATE.canvas.h/2 - 5)));
    STATE.blocks.push(blk);
    STATE.selected = blk.id; STATE.multiSel.clear();
    renderAll();
}

// ─────────────────────────────────────────────────────────────────────
//  SAUVEGARDE & CHARGEMENT GLOBAL
// ─────────────────────────────────────────────────────────────────────
function saveLayout() {
    const layout = { canvas:STATE.canvas, blocks:STATE.blocks };
    const btn    = document.getElementById('le-save-btn');
    if (btn) { btn.textContent='⏳…'; btn.disabled=true; }

    fetch('/label-editor/save', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify(layout),
    })
    .then(r => r.json())
    .then(data => {
        if (btn) { btn.textContent='💾 Sauvegarder'; btn.disabled=false; }
        showToast(data.ok ? '✓ Layout sauvegardé' : '✗ Erreur sauvegarde');
    })
    .catch(() => {
        if (btn) { btn.textContent='💾 Sauvegarder'; btn.disabled=false; }
        showToast('✗ Erreur réseau');
    });
}

function loadLayout(layoutJson) {
    try {
        const data = typeof layoutJson==='string' ? JSON.parse(layoutJson) : layoutJson;
        if (data.canvas) STATE.canvas = { w:60, h:30, bg:'#ffffff', ...data.canvas };
        if (data.blocks) {
            STATE.blocks  = data.blocks;
            STATE._nextId = Math.max(...data.blocks.map(b => parseInt(b.id.replace(/\D/g,''))||0), 0) + 1;
        }
        STATE.selected = null; STATE.multiSel.clear();
        historyPush(); renderAll();
    } catch(e) { console.error('[Editor] Erreur chargement:', e); }
}

function resetLayout() {
    if (!confirm('Effacer tout le layout ?')) return;
    historyPush();
    STATE.blocks=[]; STATE.selected=null; STATE.multiSel.clear();
    STATE.canvas={ w:60, h:30, bg:'#ffffff' };
    renderAll();
}

// ─────────────────────────────────────────────────────────────────────
//  CLAVIER
// ─────────────────────────────────────────────────────────────────────
document.addEventListener('keydown', e => {
    const tag = e.target.tagName;
    if (tag==='INPUT'||tag==='TEXTAREA'||tag==='SELECT') return;

    if (e.key==='Delete'||e.key==='Backspace')             { deleteSelected(); return; }
    if (e.key==='d' && (e.ctrlKey||e.metaKey))             { e.preventDefault(); duplicateSelected(); return; }
    if (e.key==='a' && (e.ctrlKey||e.metaKey))             { e.preventDefault(); selectAll(); return; }
    if (e.key==='z' && (e.ctrlKey||e.metaKey) && !e.shiftKey) { e.preventDefault(); historyUndo(); return; }
    if ((e.key==='z'&&(e.ctrlKey||e.metaKey)&&e.shiftKey)||(e.key==='y'&&(e.ctrlKey||e.metaKey))) { e.preventDefault(); historyRedo(); return; }
    if (e.key==='s' && (e.ctrlKey||e.metaKey))             { e.preventDefault(); saveLayout(); return; }
    if (e.key==='Escape')                                   { deselectAll(); return; }
    if (e.key==='0' && (e.ctrlKey||e.metaKey))             { e.preventDefault(); zoomReset(); return; }
    if (e.key==='=' && (e.ctrlKey||e.metaKey))             { e.preventDefault(); zoomIn(); return; }
    if (e.key==='-' && (e.ctrlKey||e.metaKey))             { e.preventDefault(); zoomOut(); return; }

    if (['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(e.key) && STATE.selected) {
        e.preventDefault();
        const blk  = STATE.blocks.find(b=>b.id===STATE.selected);
        if (!blk) return;
        const step = e.shiftKey ? 0.1 : GRID;
        if (e.key==='ArrowLeft')  blk.x = Math.max(0, blk.x-step);
        if (e.key==='ArrowRight') blk.x = Math.min(STATE.canvas.w-blk.w, blk.x+step);
        if (e.key==='ArrowUp')    blk.y = Math.max(0, blk.y-step);
        if (e.key==='ArrowDown')  blk.y = Math.min(STATE.canvas.h-blk.h, blk.y+step);
        renderCanvas(); updatePreviewDebounced();
    }
});

// ─────────────────────────────────────────────────────────────────────
//  CANVAS EVENTS
// ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    const cvs = document.getElementById('le-canvas');
    if (cvs) {
        cvs.addEventListener('mousedown', e => {
            if (e.target === cvs || e.target.id === 'le-canvas') {
                deselectAll();
                if (!e.shiftKey) startSelRect(e);
            }
        });
    }
    window.addEventListener('resize', () => renderCanvas());
});

// ─────────────────────────────────────────────────────────────────────
//  INIT
// ─────────────────────────────────────────────────────────────────────
function initEditor(previewId, previewComp, savedLayout, presets) {
    window.LE_PREVIEW_ID = previewId;
    window.LE_PRESETS    = presets || {};
    STATE.previewComp    = previewComp || {};

    loadPersistedLayouts();

    if (savedLayout) loadLayout(savedLayout);
    else historyPush();

    renderAll();
    renderLayoutsList();
    updateUndoRedoBtns();
}
