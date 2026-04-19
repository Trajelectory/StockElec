/* StockEleK — base.html */
// Restaure le thème avant le rendu pour éviter le flash
    (function() {
        var t = localStorage.getItem('theme');
        if (t) document.documentElement.setAttribute('data-theme', t);
    })();

// ── Favicons dynamiques pour source_url ──────────────────────────────
// Charge le favicon du domaine via Google S2 Favicons API
// Utilise other.png comme fallback si indisponible
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('img.src-favicon[data-src-url]').forEach(function(img) {
        try {
            var url  = img.dataset.srcUrl;
            var fallback = img.dataset.fallback || img.src;
            var domain = new URL(url).hostname;
            var favicon = 'https://www.google.com/s2/favicons?domain=' + domain + '&sz=32';
            var test = new Image();
            test.onload = function() {
                // Google renvoie une image 1×1 transparente si pas de favicon
                // On vérifie que l'image a une taille raisonnable
                if (test.naturalWidth > 1) {
                    img.src = favicon;
                }
            };
            test.onerror = function() { /* garde le fallback */ };
            test.src = favicon;
        } catch(e) { /* URL invalide — garde other.png */ }
    });
});

