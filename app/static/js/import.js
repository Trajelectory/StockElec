/* StockEleK — components/import.html */
const dropZone  = document.getElementById('drop-zone');
const fileInput = document.getElementById('csv_file');
const submitBtn = document.getElementById('submit-btn');
const hint      = document.getElementById('import-hint');

function showFile(name) {
    document.getElementById('drop-idle').style.display    = 'none';
    document.getElementById('drop-selected').style.display = 'flex';
    document.getElementById('file-name').textContent       = name;
    dropZone.classList.add('has-file');
    submitBtn.disabled = false;
    hint.textContent   = `${t_import_csv_ready_file} "${name}"`;
}

function clearFile() {
    fileInput.value = '';
    document.getElementById('drop-idle').style.display     = 'flex';
    document.getElementById('drop-selected').style.display = 'none';
    dropZone.classList.remove('has-file');
    submitBtn.disabled = true;
    hint.textContent   = t_import_csv_select_hint;
}

fileInput.addEventListener('change', () => {
    if (fileInput.files.length) showFile(fileInput.files[0].name);
});

['dragover','dragenter'].forEach(e =>
    dropZone.addEventListener(e, ev => { ev.preventDefault(); dropZone.classList.add('drag-over'); }));
['dragleave','drop'].forEach(e =>
    dropZone.addEventListener(e, ev => { ev.preventDefault(); dropZone.classList.remove('drag-over'); }));

dropZone.addEventListener('drop', e => {
    if (!e.dataTransfer.files.length) return;
    const file = e.dataTransfer.files[0];
    const dt = new DataTransfer(); dt.items.add(file);
    fileInput.files = dt.files;
    showFile(file.name);
});

dropZone.addEventListener('click', e => {
    if (e.target.closest('button') || e.target === fileInput) return;
    fileInput.click();
});
