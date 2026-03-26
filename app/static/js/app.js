// Auto-dismiss alerts after 5 s
document.querySelectorAll('.alert').forEach(el => {
    setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity .4s'; }, 5000);
    setTimeout(() => el.remove(), 5400);
});
