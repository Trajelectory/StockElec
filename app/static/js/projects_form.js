/* StockEleK — projects/form.html */
function previewImage(input) {
    if (!input.files || !input.files[0]) return;
    const reader = new FileReader();
    reader.onload = e => {
        document.getElementById('preview-img').src = e.target.result;
        document.getElementById('img-placeholder') &&
            (document.getElementById('img-placeholder').style.display = 'none');
        document.getElementById('img-preview').style.display = 'flex';
        document.getElementById('delete-image').value = '0';
    };
    reader.readAsDataURL(input.files[0]);
}

function removeImage() {
    document.getElementById('preview-img').src = '';
    document.getElementById('img-preview').style.display = 'none';
    const ph = document.getElementById('img-placeholder');
    if (ph) ph.style.display = 'flex';
    document.getElementById('image-input').value = '';
    document.getElementById('delete-image').value = '1';
}
