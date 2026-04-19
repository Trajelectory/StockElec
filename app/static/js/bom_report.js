/* StockEleK — projects/bom_report.html */
function syncQty(checkbox, hiddenId) {
    const hidden = document.getElementById(hiddenId);
    if (hidden) hidden.disabled = !checkbox.checked;
}
function syncMissingQty(checkbox, hiddenId) {
    const hidden = document.getElementById(hiddenId);
    if (hidden) hidden.disabled = !checkbox.checked;
}
document.querySelectorAll('.bom-check').forEach(cb => {
    const hid = cb.getAttribute('onchange')?.match(/qty-[a-z]+-\d+/)?.[0];
    if (hid) syncQty(cb, hid);
});
function toggleAll(group, checked) {
    document.querySelectorAll(`.bom-check-${group}`).forEach(cb => {
        cb.checked = checked;
        const hid = cb.getAttribute('onchange')?.match(/qty-[a-z]+-\d+/)?.[0];
        if (hid) {
            if (group === 'missing') syncMissingQty(cb, hid);
            else syncQty(cb, hid);
        }
    });
}
