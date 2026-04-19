/* StockEleK — projects/index.html */
const cards = [...document.querySelectorAll('.project-card-wrap')];

// Filtres par statut
document.querySelectorAll('.proj-filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.proj-filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const status = btn.dataset.status;
        cards.forEach(c => {
            c.classList.toggle('hidden', status && c.dataset.status !== status);
        });
    });
});

// Tri
function sortProjects(by) {
    const grid = document.getElementById('project-grid');
    const sorted = [...cards].sort((a, b) => {
        if (by === 'name')       return a.dataset.name.localeCompare(b.dataset.name);
        if (by === 'components') return +b.dataset.components - +a.dataset.components;
        return b.dataset.date.localeCompare(a.dataset.date);
    });
    sorted.forEach(c => grid.appendChild(c));
}
