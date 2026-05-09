/* StockEleK — label_settings.js — Preview iframe temps réel */

// ── Helpers ────────────────────────────────────────────────────────────
function val(id) {
    const el = document.getElementById(id);
    if (!el) return null;
    if (el.type === 'checkbox') return el.checked;
    if (el.type === 'radio')   return document.querySelector(`input[name="${el.name}"]:checked`)?.value;
    return el.value;
}

function stepNum(id, delta) {
    const el = document.getElementById(id);
    if (!el) return;
    const v = parseFloat(el.value) || 0;
    el.value = Math.max(parseFloat(el.min)||0, Math.min(parseFloat(el.max)||999,
               Math.round((v + delta) * 10) / 10));
    schedulePreview();
}

// ── Preview iframe ────────────────────────────────────────────────────
const PREVIEW_ID = document.querySelector('[data-preview-id]')?.dataset?.previewId || null;
var _previewTimer = null;
var _previewPending = false;

function schedulePreview(delay) {
    clearTimeout(_previewTimer);
    _previewTimer = setTimeout(refreshPreview, delay || 600);
    // Mettre à jour les labels hex immédiatement (pas besoin d'attendre)
    updateColorLabels();
    updateDimsLabel();
    updateToggleStyles();
}

function refreshPreview() {
    if (!PREVIEW_ID) return;
    const iframe   = document.getElementById('ls-preview-iframe');
    const loading  = document.getElementById('ls-preview-loading');
    if (!iframe)   return;

    // Construire l'URL avec les params courants
    const params = collectParams();
    const url    = `/labels/preview/${PREVIEW_ID}?${params}`;

    if (loading) loading.style.display = 'flex';
    iframe.style.opacity = '0.4';
    iframe.src = url;
}

function iframeLoaded() {
    const iframe  = document.getElementById('ls-preview-iframe');
    const loading = document.getElementById('ls-preview-loading');
    if (loading) loading.style.display = 'none';
    if (iframe)  iframe.style.opacity  = '1';
    scaleiframe();
}

function scaleiframe() {
    // Le template embed gère lui-même le scale via CSS max-width/max-height
    // On met juste l'iframe à la bonne hauteur
    const iframe = document.getElementById('ls-preview-iframe');
    const zone   = document.getElementById('ls-preview-zone');
    if (!iframe || !zone) return;
    iframe.style.width  = '100%';
    iframe.style.height = zone.clientHeight + 'px';
}

function collectParams() {
    const keys = [
        'lbl_width_mm','lbl_height_mm','lbl_bg_color','lbl_text_color',
        'lbl_show_image','lbl_show_qr','lbl_show_lcsc','lbl_show_mfr_part',
        'lbl_show_mfg','lbl_show_package','lbl_show_rohs','lbl_show_qty',
        'lbl_show_location','lbl_show_category','lbl_show_price','lbl_show_note',
        'lbl_desc_size_mm','lbl_ref_size_mm','lbl_badge_size_mm',
        'lbl_color_pkg','lbl_color_rohs','lbl_color_qty','lbl_color_loc','lbl_color_cat',
        'lbl_copies','lbl_custom_note','lbl_qr_position',
    ];
    const p = new URLSearchParams();
    keys.forEach(k => {
        const el = document.getElementById(k);
        if (!el) return;
        if (el.type === 'checkbox') p.set(k, el.checked ? '1' : '0');
        else p.set(k, el.value || '');
    });
    // Orientation — radio button
    const ori = document.querySelector('input[name="lbl_orientation"]:checked');
    if (ori) p.set('lbl_orientation', ori.value);
    return p.toString();
}

// ── Rétrocompat : updatePreview() déclenche schedulePreview ──────────
function updatePreview() { schedulePreview(400); }

// ── Labels couleurs hex ──────────────────────────────────────────────
function updateColorLabels() {
    ['lbl_bg_color','lbl_text_color','lbl_color_pkg','lbl_color_rohs',
     'lbl_color_qty','lbl_color_loc','lbl_color_cat'].forEach(id => {
        const vEl = document.getElementById(id + '_val');
        const iEl = document.getElementById(id);
        if (vEl && iEl) vEl.textContent = iEl.value;
    });
}

// ── Dimensions dans la barre ─────────────────────────────────────────
function updateDimsLabel() {
    const w   = document.getElementById('lbl_width_mm')?.value  || '?';
    const h   = document.getElementById('lbl_height_mm')?.value || '?';
    const ori = document.querySelector('input[name="lbl_orientation"]:checked')?.value;
    const el  = document.getElementById('preview-dims');
    if (el) el.textContent = (ori === 'portrait') ? `${h} × ${w} mm` : `${w} × ${h} mm`;
}

// ── Toggles visuels (les petits switches) ────────────────────────────
function updateToggleStyles() {
    document.querySelectorAll('input[type=checkbox][id^="lbl_"]').forEach(cb => {
        const track = document.getElementById('tgl-' + cb.name);
        if (track) track.style.background = cb.checked ? 'var(--accent)' : 'var(--border)';
    });
}

// ── Presets ──────────────────────────────────────────────────────────
function applyPreset(w, h) {
    const wi = document.getElementById('lbl_width_mm');
    const hi = document.getElementById('lbl_height_mm');
    if (wi) wi.value = w;
    if (hi) hi.value = h;
    document.querySelectorAll('.ls-preset-btn').forEach(b => b.classList.remove('ls-preset-active'));
    if (event?.currentTarget) event.currentTarget.classList.add('ls-preset-active');
    schedulePreview(200);
}

// ── Reset défauts ────────────────────────────────────────────────────
function resetDefaults() {
    if (!confirm(CONFIRM_RESET)) return;
    Object.entries(DEFAULTS).forEach(([key, v]) => {
        const el = document.getElementById(key);
        if (!el) return;
        if (el.type === 'checkbox') el.checked = v === '1';
        else el.value = v;
    });
    schedulePreview(200);
}

// ── Note toggle ──────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function() {
    var toggleNote  = document.getElementById('lbl_show_note');
    var noteSection = document.getElementById('note-section');
    if (toggleNote && noteSection) {
        toggleNote.addEventListener('change', function() {
            noteSection.style.display = this.checked ? '' : 'none';
            schedulePreview();
        });
    }
    // Init
    updateColorLabels();
    updateDimsLabel();
    updateToggleStyles();
    // Déclencher le premier chargement de l'iframe
    setTimeout(refreshPreview, 300);
});

window.addEventListener('resize', function() {
    scaleiframe();
    updateDimsLabel();
});
