/* StockEleK — label_settings */

// Ratio aperçu : 1mm = N px — sera recalculé dynamiquement
const BASE_MM_PX = 4.0;

function val(id) {
    const el = document.getElementById(id);
    return el ? (el.type === 'checkbox' ? el.checked : el.value) : null;
}

function stepNum(id, delta) {
    const el = document.getElementById(id);
    if (!el) return;
    const v = parseFloat(el.value) || 0;
    el.value = Math.max(parseFloat(el.min)||0, Math.min(parseFloat(el.max)||999, Math.round((v + delta) * 10) / 10));
    updatePreview();
}

function updatePreview() {
    const w  = parseFloat(val('lbl_width_mm'))  || 60;
    const h  = parseFloat(val('lbl_height_mm')) || 30;
    const bg = val('lbl_bg_color')   || '#ffffff';
    const fg = val('lbl_text_color') || '#111111';
    const descSize  = parseFloat(val('lbl_desc_size_mm'))  || 2.1;
    const refSize   = parseFloat(val('lbl_ref_size_mm'))   || 1.7;
    const badgeSize = parseFloat(val('lbl_badge_size_mm')) || 1.4;

    const zone = document.getElementById('ls-preview-zone');
    const zoneW = zone ? zone.clientWidth - 48 : 480;
    const zoneH = zone ? zone.clientHeight - 48 : 320;

    // Calculer l'échelle pour remplir la zone au maximum
    const scaleW = zoneW / (w * BASE_MM_PX);
    const scaleH = zoneH / (h * BASE_MM_PX);
    const scale  = Math.min(scaleW, scaleH, 2.5); // max 2.5x
    const pw = Math.round(w * BASE_MM_PX * scale);
    const ph = Math.round(h * BASE_MM_PX * scale);

    const label = document.getElementById('preview-label');
    label.style.width      = pw + 'px';
    label.style.height     = ph + 'px';
    label.style.minWidth   = pw + 'px';
    label.style.background = bg;
    label.style.color      = fg;

    document.getElementById('preview-dims').textContent = w + ' × ' + h + ' mm';

    const toPx = mm => Math.max(7, Math.round(mm * BASE_MM_PX * scale * 0.72)) + 'px';

    // Tailles de police
    const desc = document.getElementById('prev-desc');
    if (desc) desc.style.fontSize = toPx(descSize);
    document.querySelectorAll('#prev-refs > div').forEach(el => el.style.fontSize = toPx(refSize));
    document.querySelectorAll('#prev-badges > span').forEach(el => {
        el.style.fontSize = toPx(badgeSize);
        el.style.padding  = `0 ${Math.max(2, Math.round(scale*1.5))}px`;
    });
    const price = document.getElementById('prev-price');
    if (price) price.style.fontSize = toPx(refSize);

    // Image et QR
    const imgDiv = document.getElementById('prev-img');
    if (imgDiv) { imgDiv.style.width = ph + 'px'; imgDiv.style.height = ph + 'px'; }
    const qrDiv  = document.getElementById('prev-qr');
    if (qrDiv)  { qrDiv.style.width = Math.round(ph * 0.6) + 'px'; qrDiv.style.height = ph + 'px'; }

    // Visibilité
    toggle('prev-img',   val('lbl_show_image'));
    toggle('prev-qr',    val('lbl_show_qr'));
    toggle('prev-lcsc',  val('lbl_show_lcsc'));
    toggle('prev-mfr',   val('lbl_show_mfr_part'));
    toggle('prev-mfg',   val('lbl_show_mfg'));
    toggle('prev-pkg',   val('lbl_show_package'));
    toggle('prev-rohs',  val('lbl_show_rohs'));
    toggle('prev-qty',   val('lbl_show_qty'));
    toggle('prev-loc',   val('lbl_show_location'));
    toggle('prev-cat',   val('lbl_show_category'));
    toggle('prev-price', val('lbl_show_price'));

    // Couleurs badges
    setBadgeBg('prev-pkg',  val('lbl_color_pkg'));
    setBadgeBg('prev-rohs', val('lbl_color_rohs'));
    setBadgeBg('prev-qty',  val('lbl_color_qty'));
    setBadgeBg('prev-loc',  val('lbl_color_loc'));
    setBadgeBg('prev-cat',  val('lbl_color_cat'));

    // Labels hex des color pickers
    ['lbl_bg_color','lbl_text_color','lbl_color_pkg','lbl_color_rohs',
     'lbl_color_qty','lbl_color_loc','lbl_color_cat'].forEach(id => {
        const vEl = document.getElementById(id + '_val');
        const iEl = document.getElementById(id);
        if (vEl && iEl) vEl.textContent = iEl.value;
    });

    // Toggles visuels
    document.querySelectorAll('input[type=checkbox][id^="lbl_"]').forEach(cb => {
        const track = document.getElementById('tgl-' + cb.name);
        if (track) track.style.background = cb.checked ? 'var(--accent)' : 'var(--border)';
    });
}

function toggle(id, show) {
    const el = document.getElementById(id);
    if (el) el.style.display = show ? '' : 'none';
}
function setBadgeBg(id, color) {
    const el = document.getElementById(id);
    if (el && color) el.style.background = color;
}

function resetDefaults() {
    if (!confirm(CONFIRM_RESET)) return;
    Object.entries(DEFAULTS).forEach(([key, v]) => {
        const el = document.getElementById(key);
        if (!el) return;
        if (el.type === 'checkbox') el.checked = v === '1';
        else el.value = v;
    });
    updatePreview();
}

// Recalculer à chaque resize
window.addEventListener('resize', updatePreview);

// Init
updatePreview();
