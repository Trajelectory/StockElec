/* StockEleK — components/home.html */
let _t;
document.getElementById('home-search').addEventListener('input', function() {
    clearTimeout(_t);
    if (this.value.trim().length >= 2) {
        _t = setTimeout(() => document.getElementById('home-search-form').submit(), 400);
    }
});

// Mémorise le per_page choisi
document.querySelectorAll('.per-page-btn').forEach(function(btn) {
    btn.addEventListener('click', function(e) {
        try {
            const url = new URL(this.href);
            const pp = url.searchParams.get('per_page');
            if (pp) localStorage.setItem('home_per_page', pp);
        } catch(err) {}
    });
});

// Redirige vers le per_page mémorisé si l'URL n'en a pas
(function() {
    const url = new URL(window.location.href);
    if (!url.searchParams.has('per_page')) {
        const saved = localStorage.getItem('home_per_page');
        if (saved && saved !== '5') {
            url.searchParams.set('per_page', saved);
            window.location.replace(url.toString());
        }
    }
})();
