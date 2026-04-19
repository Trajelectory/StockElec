/* StockEleK — components/alerts.html */
function adjustQty(id, delta, btn) {
    btn.disabled = true;
    fetch(`/component/${id}/adjust`, {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({delta})
    })
    .then(r=>r.json())
    .then(data => {
        if (data.ok) {
            document.getElementById(`qty-${id}`).textContent = data.new_qty;
            if (!data.is_low) {
                const row = document.getElementById(`row-${id}`);
                row.style.opacity = '0.4';
                row.style.transition = 'opacity .4s';
                setTimeout(() => row.remove(), 500);
            }
        } else alert(data.error);
        btn.disabled = false;
    });
}
