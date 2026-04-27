
/* StockEleK — components/detail.html */
function adjustQty(id, delta, btn) {
    btn.disabled = true;
    fetch(`/component/${id}/adjust`, {
        method:'POST',
        headers:{'Content-Type':'application/json', 'X-Requested-With':'XMLHttpRequest'},
        body: JSON.stringify({delta})
    })
    .then(r => r.json())
    .then(data => {
        if (data.ok) {
            const el = document.getElementById(`qty-${id}`);
            el.textContent = data.new_qty;
            el.className = 'cd-qty-val' +
                (data.new_qty === 0 ? ' qty-zero' : data.is_low ? ' qty-low' : '');
        } else alert(data.error || t_detail_error_generic);
        btn.disabled = false;
    })
    .catch(() => { btn.disabled = false; alert(t_detail_error_network); });
}

function openLightbox(src, title) {
    document.getElementById('lightbox-img').src = src;
    document.getElementById('lightbox-title').textContent = title || '';
    document.getElementById('lightbox').classList.add('open');
}
function closeLightbox() { document.getElementById('lightbox').classList.remove('open'); }
document.addEventListener('keydown', e => { if (e.key==='Escape') closeLightbox(); });

function loadPngs() {
    if (!LCSC_REF) return;
    ['sym-hint','fp-hint'].forEach(id => {
        const el = document.getElementById(id); if (el) el.textContent = '⏳';
    });
    fetch(`/api/easyeda-pngs/${encodeURIComponent(LCSC_REF)}`)
        .then(r => r.json())
        .then(data => {
            if (!data.ok) {
                ['sym-hint','fp-hint'].forEach(id => { const el = document.getElementById(id); if (el) el.textContent = '—'; });
                return;
            }
            if (data.symbol_png)    _replaceWithImg('sym-placeholder', '/easyeda-pngs/' + data.symbol_png.split('easyeda_pngs/').pop(), 'Symbole');
            if (data.footprint_png) _replaceWithImg('fp-placeholder',  '/easyeda-pngs/' + data.footprint_png.split('easyeda_pngs/').pop(), 'Footprint');
        })
        .catch(() => { ['sym-hint','fp-hint'].forEach(id => { const el = document.getElementById(id); if (el) el.textContent = '❌'; }); });
}

function _replaceWithImg(phId, src, title) {
    const ph = document.getElementById(phId); if (!ph) return;
    const img = document.createElement('img');
    img.src = src; img.alt = title;
    img.className = 'cd-img-thumb';
    img.title = 'Agrandir';
    img.onclick = () => openLightbox(src, title);
    ph.replaceWith(img);
}

function enrichComponent(id) {
    const btn = document.getElementById('enrich-btn');
    const orig = btn.textContent;
    btn.textContent = t_detail_btn_fetching; btn.disabled = true;
    fetch(`/enrich/${id}`, {method:'POST'})
    .then(r => r.json())
    .then(data => {
        if (data.ok) {
            btn.textContent = t_detail_btn_fetch_ok;
            setTimeout(() => location.reload(), 800);
        } else {
            btn.textContent = t_detail_btn_fetch_fail;
            btn.title = data.error || t_detail_error_unknown;
            setTimeout(() => { btn.textContent = orig; btn.disabled = false; btn.title = ''; }, 3000);
        }
    })
    .catch(() => {
        btn.textContent = t_detail_error_network;
        setTimeout(() => { btn.textContent = orig; btn.disabled = false; }, 3000);
    });
}

function flashLed(location, componentId) {
    const btn    = document.getElementById('detail-led-btn');
    const status = document.getElementById('detail-led-status');
    if (!btn) return;

    // Format: "atelier_id:CELLID" (ex: "principal:A7") ou ancien "A7"
    let atelierId = null;
    let cellId    = location;
    if (location && location.includes(':')) {
        const parts = location.split(':');
        atelierId   = parts[0];
        cellId      = parts[1];
    }

    btn.disabled = true;
    status.textContent = t_detail_led_sending;
    status.style.color = 'var(--text-muted)';

    const payload = {};
    if (componentId) payload.component_id = componentId;
    if (atelierId)   payload.atelier_id   = atelierId;
    fetch(`/api/led/${cellId}/on`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload),
    })
        .then(r => r.json())
        .then(data => {
            if (data.ok) {
                status.textContent = data.queued
                    ? '⏳ ' + t_detail_led_ok
                    : '💡 ' + t_detail_led_ok;
                status.style.color = data.queued ? 'var(--accent)' : 'var(--accent)';
                setTimeout(() => {
                    status.textContent = '';
                    btn.disabled = false;
                }, 3000);
            } else {
                status.textContent = t_detail_led_err;
                status.style.color = 'var(--danger)';
                btn.disabled = false;
            }
        })
        .catch(() => {
            status.textContent = t_detail_led_err;
            status.style.color = 'var(--danger)';
            btn.disabled = false;
        });
}

// ── Vérification prix LCSC ──────────────────────────────────────
function checkPrice(lcscRef) {
    const btn    = document.getElementById('price-check-btn');
    const result = document.getElementById('price-check-result');
    if (!btn || !result) return;

    btn.disabled = true;
    btn.textContent = '⏳';
    result.textContent = '';

    fetch(`/api/price-check/${encodeURIComponent(lcscRef)}`)
        .then(r => r.json())
        .then(d => {
            btn.textContent = '↻';
            btn.disabled = false;

            if (!d.ok) {
                result.innerHTML = `<span style="color:var(--text-muted)">${d.error || 'Erreur'}</span>`;
                return;
            }

            // Affichage du prix actuel en USD
            const priceStr = `${d.current_usd.toFixed(4)} $`;

            if (d.trend === 'unknown' || d.delta_pct === null) {
                // Pas de prix stocké — on affiche juste le prix actuel
                result.innerHTML =
                    `<span style="color:var(--text-muted)" title="Prix actuel LCSC">` +
                    `LCSC : ${priceStr}</span>`;
                return;
            }

            const colors = { up: 'var(--danger)', down: 'var(--success)', stable: 'var(--text-muted)' };
            const arrows = { up: '↑', down: '↓', stable: '→' };
            const sign   = d.delta_pct > 0 ? '+' : '';
            const color  = colors[d.trend];
            const arrow  = arrows[d.trend];

            // Tooltip avec tous les paliers
            const ladderTip = d.ladders
                .map(l => `≥${l.qty} : ${l.price.toFixed(4)} $`)
                .join('\n');

            result.innerHTML =
                `<span style="color:${color};cursor:help" title="Prix actuel LCSC :\n${ladderTip}">` +
                `${arrow} ${sign}${d.delta_pct}% &nbsp;(${priceStr})</span>`;
        })
        .catch(() => {
            btn.textContent = '↻';
            btn.disabled = false;
            result.innerHTML = `<span style="color:var(--danger)">Erreur réseau</span>`;
        });
}

// ── Édition inline de la quantité ───────────────────────────────
function startQtyEdit(id, span) {
    const input = document.getElementById('qty-edit-' + id);
    if (!input) return;
    input.value = span.textContent.trim();
    span.style.display = 'none';
    input.style.display = 'inline-block';
    input.focus();
    input.select();
}

function cancelQtyEdit(id) {
    const span  = document.getElementById('qty-' + id);
    const input = document.getElementById('qty-edit-' + id);
    if (span)  span.style.display = '';
    if (input) input.style.display = 'none';
}

function saveQty(id) {
    const span  = document.getElementById('qty-' + id);
    const input = document.getElementById('qty-edit-' + id);
    if (!span || !input) return;

    const newQty = parseInt(input.value, 10);
    const oldQty = parseInt(span.textContent.trim(), 10);

    // Pas de changement
    if (isNaN(newQty) || newQty === oldQty) {
        cancelQtyEdit(id);
        return;
    }

    const delta = newQty - oldQty;
    input.disabled = true;

    fetch(`/component/${id}/adjust`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        body: JSON.stringify({delta, absolute: newQty}),
    })
    .then(r => r.json())
    .then(data => {
        if (data.ok) {
            span.textContent = data.new_qty;
            span.className = 'cd-qty-val' +
                (data.new_qty === 0 ? ' qty-zero' : data.is_low ? ' qty-low' : '');
        } else {
            alert(data.error || 'Erreur');
        }
        cancelQtyEdit(id);
        input.disabled = false;
    })
    .catch(() => { cancelQtyEdit(id); input.disabled = false; });
}
