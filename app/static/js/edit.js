/* StockEleK — components/edit.html */
function stepField(id, delta) {
    const el  = document.getElementById(id);
    const val = parseFloat(el.value) || 0;
    const min = parseFloat(el.min ?? 0);
    el.value  = Math.max(min, val + delta);
    el.dispatchEvent(new Event('input'));
}

function autoCalcTotal() {
    const unit = parseFloat(document.getElementById('f-unit-price').value) || 0;
    const qty  = parseFloat(document.getElementById('f-quantity').value)   || 0;
    const display = document.getElementById('total-display');
    const ext  = document.getElementById('f-ext-price');
    if (unit > 0 && qty > 0) {
        const total = (unit * qty).toFixed(2);
        ext.placeholder = total;
        if (display) display.textContent = total + ' €';
    } else {
        ext.placeholder = '0.00';
        if (display) display.textContent = '—';
    }
}
document.getElementById('f-quantity').addEventListener('input', autoCalcTotal);
autoCalcTotal();

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
