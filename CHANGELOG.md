# Changelog — StockElectory

---

## v2.0 — Refonte majeure 🎉

> Release publique. Réécriture complète du design, nouvelles fonctionnalités atelier, plan Gridfinity.

### 🎨 Design system v2
- Nouveau design sombre violet/indigo (`#7c6cff`) — fini le bleu
- Typographie **Inter** (Google Fonts) avec poids 800 pour les titres
- Navbar avec backdrop blur, liens actifs avec bordure subtile
- Boutons, badges et alertes redessinés de zéro
- CSS modulaire : `style.css` de 40 lignes avec `@import` vers 15 modules dans `modules/`

### 🏠 Page d'accueil repensée
- Grande barre de recherche centrée (style Google) avec soumission automatique au bout de 400ms
- Compteurs discrets : références, pièces totales, alertes
- 5 raccourcis rapides (Stock, Ajouter, Projets, Alertes, Commander)
- Tableau des 5 derniers composants ajoutés, pleine largeur
- Route `/` → page d'accueil, `/stock` → tableau complet

### 📋 Historique des mouvements
- Table `stock_movements` en base — chaque +/− enregistré automatiquement
- Page `/history` filtrable par type (entrée / sortie / ajustement) et par limite
- Types : 📥 Entrée, 📤 Sortie, 🔧 Ajustement, 🌱 Initialisation

### 🛒 Réapprovisionnement
- Page `/reorder` : liste automatique des composants en rupture ou sous le seuil
- Quantité suggérée (3× le seuil), prix estimé de la commande, liens directs LCSC

### ⬇️ Export CSV
- Un clic pour télécharger tout le stock en `.csv` (`/export/csv`)

### 📦 Plan Gridfinity ⭐ *nouveauté*
- Page visuelle pour planifier l'organisation physique de son atelier
- Grille de cases cliquables représentant les plateaux Gridfinity imprimés en 3D
- Plusieurs plateaux configurables (ID, nom, colonnes × rangées)
- Navigation par **tabs** — un onglet par plateau, affichage instantané sans rechargement
- Barre de progression : taux d'occupation de chaque plateau
- Popup de recherche et d'assignation — n'affiche que les composants sans emplacement
- Sauvegarde automatique en BDD dès l'assignation, mise à jour du champ `location`

### ⚙️ Paramètres
- Bouton **🗑️ Vider l'historique** avec confirmation
- Vider l'historique ne touche pas au stock

### 🔧 Serveur de production
- Remplacement du serveur de développement Flask par **Waitress**
- Démarrage propre, sans warning, avec fallback automatique si Waitress absent
- `pip install waitress` pour l'activer

### 🐛 Bugs corrigés
| Composant | Bug | Correction |
|---|---|---|
| CSS | `.td-qty-wrap { display:flex }` cassait l'alignement vertical | Supprimé du `legacy.css` |
| CSS | `.proj-cat-row { display:flex }` cassait le tableau projets | Supprimé du `legacy.css` |
| Dashboard | `{% continue %}` non supporté Jinja2 | Remplacé par `{% if vis %}` |
| Migration DB | Table `stock_movements` sans colonne `quantity` | Détection et recréation automatique |
| Navbar | Lien brand pointait vers route supprimée | Corrigé vers `components.home` |
| Étiquettes | Aperçu affichait l'image brute sans structure | Reconstruction HTML inline |

---

## v1.x — Historique complet

<details>
<summary>Voir l'historique des versions 1.x</summary>

## v1.0 — Base de l'application
- Architecture **Flask + SQLite + MVC**
- Tableau paginé, recherche, tri multi-colonnes
- Import CSV LCSC (format export commande)
- Ajout / édition / suppression de composants
- Fiche détail complète — thème sombre

## v1.1 — Enrichissement LCSC
- Service `lcsc_scraper.py` : scraping `wmsc.lcsc.com`
- Récupération automatique catégorie, image, datasheet
- Thread daemon avec pause ~0.6s entre requêtes

## v1.2 — Déduplication et pagination
- Déduplication à l'import par référence LCSC (UNIQUE en base)
- Pagination (25 / 50 / 100 par page)

## v1.3 — Ajout rapide depuis LCSC
- Bloc "⚡ Import rapide LCSC" : saisie ref → prévisualisation → pré-remplissage

## v1.4 — Projets et alertes stock
- CRUD projets avec image bannière
- Vérification disponibilité en temps réel, boutons Débiter / Restituer (AJAX)
- Champ `min_stock`, page 🔔 Alertes + bandeau rouge

## v1.5 — Catégories hiérarchiques
- Filtre avec `<optgroup>` par sous-catégorie, macro Jinja réutilisable

## v1.6 — Import BOM KiCad
- Upload CSV KiCad → rapport ✅/⚠️/❌
- Formats : KiCad 7/8, plugin JLCPCB, bom2csv

## v1.7 — Images de projets
- Upload + prévisualisation, cartes projet avec bannière

## v1.8 — Étiquettes imprimables + QR code
- Route `/labels?ids=1,2,3` : impression multi-étiquettes
- QR code généré en Python pur (`qr_generator.py`), zéro CDN externe
- Multi-sélection dans le tableau + barre flottante

## v1.9 — Symbole & Footprint EasyEDA
- Téléchargement PNG symbole + footprint, cache dans `instance/easyeda_pngs/`
- Galerie sur la fiche détail, lightbox unifiée

## v1.10 — Support export panier LCSC
- Import CSV format `export_cart_*.csv` détecté automatiquement

## v1.11 — Refonte page projet
- Tableau unique, barre de stats compacte, formulaire rétractable

## v1.12 — Configuration des étiquettes
- Page `/label-settings` avec aperçu en temps réel
- Format, couleurs, tailles de police, 11 toggles on/off

## v1.13 — Paramètres enrichis
- Nom de l'application, sauvegarde ZIP, stats base, enrichissement en masse

## v1.14 à v1.21 — Corrections et ajouts divers
- Mode ajout en série, catégories personnalisées, upload d'image manuelle
- Téléchargement EasyEDA en masse + réconciliation, nettoyages CSS

</details>
