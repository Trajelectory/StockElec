/* StockEleK — projects/import_bom.html */
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('bom_file');
const fileNameEl = document.getElementById('file-name');
fileInput.addEventListener('change', () => {
    if (fileInput.files.length) {
        fileNameEl.textContent = '✅ ' + fileInput.files[0].name;
        fileNameEl.style.display = 'block';
    }
});
['dragover','dragenter'].forEach(e =>
    dropZone.addEventListener(e, ev => { ev.preventDefault(); dropZone.classList.add('drag-over'); }));
['dragleave','drop'].forEach(e =>
    dropZone.addEventListener(e, ev => { ev.preventDefault(); dropZone.classList.remove('drag-over'); }));
dropZone.addEventListener('drop', e => {
    if (e.dataTransfer.files.length) {
        const dt = new DataTransfer(); dt.items.add(e.dataTransfer.files[0]);
        fileInput.files = dt.files;
        fileNameEl.textContent = '✅ ' + e.dataTransfer.files[0].name;
        fileNameEl.style.display = 'block';
    }
});
