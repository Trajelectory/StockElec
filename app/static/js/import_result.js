/* StockEleK — components/import_result.html */
// Polling léger : vérifie au bout de 4s, 8s, 15s, 30s si les composants ont été enrichis

const delays = [4000, 4000, 7000, 15000];
let enrichedCount = 0;

function checkEnrich() {
    if (!ENRICH_IDS.length) return;
    fetch('/api/components?ids=' + ENRICH_IDS.join(','))
        .then(r => r.json())
        .then(data => {
            const done = data.filter(c => c.attributes || c.image_path).length;
            if (done > enrichedCount) {
                enrichedCount = done;
                document.getElementById('enrich-text').innerHTML =
                    `<strong>${done}/${ENRICH_IDS.length}</strong> ${t_import_result_enrich_done_label}`;
            }
            if (done >= ENRICH_IDS.length) {
                document.getElementById('enrich-spinner').style.display = 'none';
                document.getElementById('enrich-text').style.display = 'none';
                document.getElementById('enrich-done').style.display = 'inline';
            }
        })
        .catch(() => {});
}

let idx = 0;
function scheduleNext() {
    if (idx < delays.length) {
        setTimeout(() => { checkEnrich(); idx++; scheduleNext(); }, delays[idx]);
    }
}
scheduleNext();
