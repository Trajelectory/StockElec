/* StockEleK — base.html */
// Restaure le thème avant le rendu pour éviter le flash
    (function() {
        var t = localStorage.getItem('theme');
        if (t) document.documentElement.setAttribute('data-theme', t);
    })();
