/* StockEleK — projects/detail.html */
function toggleAddForm() {
    const form = document.getElementById('add-form');
    const btn  = document.getElementById('btn-add-toggle');
    const open = form.style.display === 'none';
    form.style.display = open ? 'block' : 'none';
    btn.textContent    = open ? t_projects_btn_close_form : t_projects_btn_add_component;
    if (open) form.querySelector('select').focus();
}

function openLightbox(src) {
    document.getElementById('lightbox-img').src = src;
    document.getElementById('lightbox').classList.add('open');
}
function closeLightbox() {
    document.getElementById('lightbox').classList.remove('open');
}
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeLightbox(); });

function useComponent(projectId, componentId, qty, btn) {
    if (!confirm(`${t_projects_confirm_use}`.replace('{qty}', qty))) return;
    btn.disabled = true;
    const fd = new FormData(); fd.append('quantity', qty);
    fetch(`/projects/${projectId}/components/${componentId}/use`, {method:'POST', body:fd})
        .then(r => r.json())
        .then(data => {
            if (data.ok) document.getElementById(`stock-${componentId}`).textContent = data.new_qty;
            else alert(data.error || 'Erreur');
            btn.disabled = false;
        })
        .catch(() => { btn.disabled = false; alert(t_projects_err_network); });
}
function returnComponent(projectId, componentId, qty, btn) {
    if (!confirm(`${t_projects_confirm_return}`.replace('{qty}', qty))) return;
    btn.disabled = true;
    const fd = new FormData(); fd.append('quantity', qty);
    fetch(`/projects/${projectId}/components/${componentId}/return`, {method:'POST', body:fd})
        .then(r => r.json())
        .then(data => {
            if (data.ok) document.getElementById(`stock-${componentId}`).textContent = data.new_qty;
            else alert(data.error || 'Erreur');
            btn.disabled = false;
        })
        .catch(() => { btn.disabled = false; alert(t_projects_err_network); });
}

function prepareKit(projectId) {
    if (!confirm(t_projects_kit_confirm)) return;
    const btn = document.getElementById('btn-kit');
    btn.disabled = true;
    btn.textContent = '⏳';
    fetch(`/projects/${projectId}/kit`, { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.ok) {
                // Mettre à jour les quantités affichées
                data.details.forEach(d => {
                    const el = document.getElementById(`stock-${d.id}`);
                    if (el) el.textContent = d.new_qty;
                });
                btn.textContent = `✅ ${data.debited} débité(s)`;
                setTimeout(() => {
                    btn.textContent = t_projects_btn_kit;
                    btn.disabled = false;
                    location.reload();
                }, 1500);
            } else {
                alert(data.error || t_projects_kit_err);
                btn.textContent = t_projects_btn_kit;
                btn.disabled = false;
            }
        })
        .catch(() => {
            alert(t_projects_kit_err);
            btn.textContent = t_projects_btn_kit;
            btn.disabled = false;
        });
}

function filterCat(cat, btn) {
    // Mettre à jour le bouton actif (supporte .pd-cat-btn et .pd-cat-filter-btn)
    document.querySelectorAll('.pd-cat-btn, .pd-cat-filter-btn').forEach(b => b.classList.remove('pd-cat-active'));
    if (btn) btn.classList.add('pd-cat-active');

    const rows     = document.querySelectorAll('tr[data-cat]');
    const headers  = document.querySelectorAll('tr[data-cat-header]');

    if (cat === null) {
        // Tout afficher
        rows.forEach(r => r.style.display = '');
        headers.forEach(h => h.style.display = '');
        return;
    }

    // Masquer/afficher les lignes
    rows.forEach(r => {
        r.style.display = r.dataset.cat === cat ? '' : 'none';
    });

    // Masquer les headers de catégories qui n'ont plus de lignes visibles
    headers.forEach(h => {
        const hasCat = h.dataset.catHeader === cat;
        h.style.display = hasCat ? '' : 'none';
    });
}
