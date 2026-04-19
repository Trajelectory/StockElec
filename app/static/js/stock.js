/* StockEleK — components/index.html */
function adjustQty(id, delta, btn) {
    btn.disabled = true;
    fetch(`/component/${id}/adjust`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({delta})
    })
    .then(r => r.ok ? r.json() : Promise.reject(r.status))
    .then(data => {
        if (data.ok) {
            const qtyEl = document.getElementById(`qty-${id}`);
            qtyEl.textContent = data.new_qty;
            qtyEl.className = 'qty-value' +
                (data.new_qty === 0 ? ' qty-zero' : data.is_low ? ' qty-low' : '');
            const row = document.getElementById(`row-${id}`);
            row.classList.remove('row-empty', 'row-low');
            if (data.new_qty === 0) row.classList.add('row-empty');
            else if (data.is_low) row.classList.add('row-low');
        } else {
            alert(data.error || t_stock_error_generic);
        }
        btn.disabled = false;
    })
    .catch(() => { btn.disabled = false; alert(t_stock_error_network); });
}

function enrichComponent(id, btn) {
    btn.textContent = '⏳'; btn.disabled = true;
    fetch(`/enrich/${id}`, {method:'POST'})
        .then(r => r.json())
        .then(data => {
            if (data.ok) location.reload();
            else { btn.textContent = '❌'; btn.title = data.error || t_stock_error_generic;
                   setTimeout(() => { btn.textContent='📷'; btn.disabled=false; }, 3000); }
        })
        .catch(() => { btn.textContent = '❌'; btn.title = t_stock_error_network;
                       setTimeout(() => { btn.textContent='📷'; btn.disabled=false; }, 3000); });
}

function openLightbox(src, caption) {
    document.getElementById('lightbox-img').src = src;
    document.getElementById('lightbox-caption').textContent = caption;
    document.getElementById('lightbox').classList.add('open');
}
function closeLightbox() { document.getElementById('lightbox').classList.remove('open'); }
document.addEventListener('keydown', e => { if (e.key==='Escape') closeLightbox(); });

// ── Sélection multiple ──────────────────────────────────────────────
function toggleAll(checked) {
    document.querySelectorAll('.row-check').forEach(cb => { cb.checked = checked; });
    onCheckChange();
}

function onCheckChange() {
    const checked = getChecked();
    const bar = document.getElementById('selection-bar');
    const count = document.getElementById('selection-count');
    if (checked.length > 0) {
        count.textContent = checked.length + ' ' + t_stock_stats_parts;
        bar.style.display = 'flex';
    } else {
        bar.style.display = 'none';
    }
    // Synchronise la case "tout sélectionner"
    const all = document.querySelectorAll('.row-check');
    document.getElementById('check-all').indeterminate = checked.length > 0 && checked.length < all.length;
    document.getElementById('check-all').checked = checked.length === all.length && all.length > 0;
}

function getChecked() {
    return [...document.querySelectorAll('.row-check:checked')].map(cb => cb.value);
}

function printSelected() {
    const ids = getChecked();
    if (!ids.length) return;
    window.open('/labels?ids=' + ids.join(','), '_blank');
}

function clearSelection() {
    document.querySelectorAll('.row-check').forEach(cb => { cb.checked = false; });
    document.getElementById('check-all').checked = false;
    document.getElementById('check-all').indeterminate = false;
    document.getElementById('selection-bar').style.display = 'none';
}

// ── Filtre rapide catégories sidebar ─────────────────────────────
function filterCats(q) {
    q = q.toLowerCase().trim();
    document.querySelectorAll('.sk-cat-group').forEach(group => {
        let visible = 0;
        group.querySelectorAll('.sk-cat-btn').forEach(btn => {
            const match = !q || btn.textContent.toLowerCase().includes(q);
            btn.style.display = match ? '' : 'none';
            if (match) visible++;
        });
        // Masquer le groupe entier si aucun résultat
        group.style.display = visible === 0 ? 'none' : '';
    });
}
