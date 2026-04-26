/* StockEleK — components/add.html */
let _smartPreviewData = null;

// ── Détection automatique LCSC / Mouser / DigiKey ───────────────
function isLCSC(ref) {
    return /^C\d+$/i.test(ref.trim());
}
function isDigiKey(ref) {
    // Refs DigiKey : contiennent "-ND" ou "-1-ND" ou commencent par des chiffres-lettres typiques
    return /-ND$/i.test(ref.trim()) || /-\d+-ND$/i.test(ref.trim());
}
function detectSourceType(ref) {
    if (!ref) return null;
    if (isLCSC(ref))    return 'lcsc';
    if (isDigiKey(ref)) return 'digikey';
    return 'mouser';
}

function detectSource(val) {
    const badge = document.getElementById('smart-source-badge');
    const ref   = val.trim();
    if (!ref) { badge.style.display = 'none'; return; }
    badge.style.display = 'inline-flex';
    const src = detectSourceType(ref);
    if (src === 'lcsc') {
        badge.innerHTML = `<img src="/static/img/lcsc.png" style="width:13px;height:13px;object-fit:contain;border-radius:2px;margin-right:.2rem"> LCSC`;
        badge.className = 'nadd-src-badge'; badge.style.background='color-mix(in srgb,#00b4d8 12%,transparent)'; badge.style.color='#00b4d8';
    } else if (src === 'digikey') {
        badge.innerHTML = `<img src="/static/img/digikey.png" style="width:13px;height:13px;object-fit:contain;border-radius:2px;margin-right:.2rem"> DigiKey`;
        badge.className = 'nadd-src-badge'; badge.style.background='color-mix(in srgb,#cc0000 12%,transparent)'; badge.style.color='#cc0000';
    } else {
        badge.innerHTML = `<img src="/static/img/mouser.png" style="width:13px;height:13px;object-fit:contain;border-radius:2px;margin-right:.2rem"> Mouser`;
        badge.className = 'nadd-src-badge'; badge.style.background='color-mix(in srgb,#e8600a 12%,transparent)'; badge.style.color='#e8600a';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('smart-ref-input');
    if (input) input.addEventListener('keydown', e => {
        if (e.key === 'Enter') { e.preventDefault(); lookupSmart(); }
    });
});

function lookupSmart() {
    const ref    = document.getElementById('smart-ref-input').value.trim();
    const btn    = document.getElementById('smart-lookup-btn');
    const status = document.getElementById('smart-lookup-status');
    const box    = document.getElementById('smart-preview-box');
    if (!ref) return;

    const source = detectSourceType(ref);
    const url = source === 'lcsc'
        ? `/api/lcsc-preview?ref=${encodeURIComponent(ref.toUpperCase())}`
        : source === 'digikey'
        ? `/api/digikey-preview?ref=${encodeURIComponent(ref)}`
        : `/api/mouser-preview?ref=${encodeURIComponent(ref)}`;

    btn.disabled = true;
    btn.textContent = '⏳ Recherche…';
    status.style.display = 'none';
    box.style.display = 'none';
    _smartPreviewData = null;

    fetch(url)
        .then(r => r.json())
        .then(data => {
            btn.disabled = false;
            btn.textContent = t_form_search_btn;
            if (!data.ok) {
                status.className = 'nadd-import-status nadd-import-status--error';
                status.textContent = '❌ ' + data.error;
                status.style.display = 'block';
                return;
            }
            data._source = source;
            _smartPreviewData = data;

            const img = document.getElementById('smart-preview-img');
            img.src = data.image_url || '';
            img.style.display = data.image_url ? 'block' : 'none';

            document.getElementById('smart-preview-name').textContent =
                data.description || data.lcsc_part_number || ref;
            document.getElementById('smart-preview-meta').textContent =
                [data.manufacturer, data.package || data.manufacture_part_number,
                 data.unit_price ? parseFloat(data.unit_price).toFixed(4) + ' €' : '']
                .filter(Boolean).join(' · ');

            box.style.display = 'flex';
        })
        .catch(() => {
            btn.disabled = false;
            btn.textContent = t_form_search_btn;
            status.className = 'nadd-import-status nadd-import-status--error';
            status.textContent = '❌ ' + t_form_error_network;
            status.style.display = 'block';
        });
}

function applySmartPreview() {
    if (!_smartPreviewData) return;
    const d = _smartPreviewData;

    if (d._source === 'lcsc') {
        setVal('f-lcsc',    d.lcsc_part_number);
        setVal('f-mouser',  '');
        setVal('f-digikey', '');
        setVal('f-package', d.package);
        const rohs = document.getElementById('f-rohs');
        if (d.rohs && rohs) rohs.value = d.rohs;
    } else if (d._source === 'digikey') {
        setVal('f-digikey', d.digikey_part_number);
        setVal('f-lcsc',    '');
        setVal('f-mouser',  '');
        setVal('f-package', d.package);
        const rohs = document.getElementById('f-rohs');
        if (d.rohs && rohs) rohs.value = d.rohs;
    } else {
        setVal('f-mouser',  d.mouser_part_number);
        setVal('f-lcsc',    '');
        setVal('f-digikey', '');
    }
    setVal('f-description',      d.description);
    setVal('f-description-long', d.description_long);
    setVal('f-mfr-part',         d.manufacture_part_number);
    setVal('f-manufacturer',     d.manufacturer);
    setVal('f-category',         d.category);
    setVal('f-datasheet',        d.datasheet_url);
    setVal('f-image-url',        d.image_url || '');
    if (d.unit_price) {
        setVal('f-unit-price', parseFloat(d.unit_price).toFixed(4));
        autoCalcTotal();
    }

    document.getElementById('smart-preview-box').style.display = 'none';
    const status = document.getElementById('smart-lookup-status');
    const src    = d._source === 'lcsc' ? 'LCSC' : d._source === 'digikey' ? 'DigiKey' : 'Mouser';
    status.className   = 'nadd-import-status nadd-import-status--ok';
    status.textContent = `✅ Formulaire pré-rempli depuis ${src} — vérifie la quantité puis enregistre.`;
    status.style.display = 'block';

    document.getElementById('f-quantity').focus();
    document.getElementById('f-quantity').select();
}

function autoCalcTotal() {
    const unit = parseFloat(document.getElementById('f-unit-price').value) || 0;
    const qty  = parseFloat(document.getElementById('f-quantity').value)   || 0;
    const hint = document.getElementById('total-auto-hint');
    const ext  = document.getElementById('f-ext-price');
    if (unit > 0 && qty > 0) {
        const total = (unit * qty).toFixed(2);
        ext.placeholder = total;
        hint.textContent = `= ${total} €`;
        hint.style.display = 'inline';
    } else {
        ext.placeholder = '0.00';
        hint.textContent = 'auto';
    }
}

document.getElementById('f-quantity').addEventListener('input', autoCalcTotal);

function setVal(id, val) {
    if (val === undefined || val === null || val === '') return;
    const el = document.getElementById(id);
    if (!el) return;
    if (el.tagName === 'SELECT') {
        for (const opt of el.options) {
            if (opt.value === val) { el.value = val; return; }
        }
        el.appendChild(new Option(val, val, true, true));
    } else {
        el.value = val;
    }
}

function previewImage(input) {
    if (!input.files || !input.files[0]) return;
    const reader = new FileReader();
    reader.onload = e => {
        const preview = document.getElementById('img-preview');
        const empty   = document.getElementById('img-preview-empty');
        if (preview) { preview.src = e.target.result; preview.style.display = 'block'; }
        if (empty)   { empty.style.display = 'none'; }
    };
    reader.readAsDataURL(input.files[0]);
}
