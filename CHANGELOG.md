# Changelog — StockElec

---

## v1.0 — Base de l'application

- Architecture **Flask + SQLite + MVC**
- Tableau paginé, recherche, tri multi-colonnes
- Import CSV LCSC (format export commande)
- Ajout / édition / suppression de composants
- Fiche détail complète
- Thème sombre

---

## v1.1 — Enrichissement LCSC

- Service `lcsc_scraper.py` : scraping `wmsc.lcsc.com`
- Récupération automatique catégorie, image, datasheet
- Téléchargement local des images dans `instance/images/`
- Thread daemon avec pause ~0.6s entre requêtes
- Bouton 📷 pour relancer manuellement

---

## v1.2 — Déduplication et pagination

- Déduplication à l'import par référence LCSC (UNIQUE en base)
- Pagination (25 / 50 / 100 par page)

---

## v1.3 — Ajout rapide depuis LCSC

- Bloc "⚡ Import rapide LCSC" : saisie ref → prévisualisation → pré-remplissage
- Détection doublon avant ajout
- Route `GET /api/lcsc-preview?ref=C149504`

---

## v1.4 — Projets et alertes stock

### Projets
- CRUD complet avec image bannière (upload JPG/PNG/WEBP)
- Composants liés avec quantité nécessaire
- Vérification disponibilité en temps réel
- Boutons Débiter / Restituer (AJAX)

### Alertes
- Champ `min_stock` par composant
- Page 🔔 Alertes + bandeau rouge accueil

### Ajustement rapide
- Boutons +/− AJAX dans le tableau et sur la fiche détail

---

## v1.5 — Catégories hiérarchiques

- Filtre avec `<optgroup>` HTML par sous-catégorie
- Macro Jinja `category_select.html` réutilisable
- Arborescence LCSC complète en base

---

## v1.6 — Import BOM KiCad

- Upload CSV KiCad → rapport ✅/⚠️/❌/—
- Formats reconnus : KiCad 7/8, plugin JLCPCB, bom2csv
- Colonnes LCSC reconnues : `LCSC Part Number`, `LCSC#`, `LCSC Part #`…
- Détection doublon dans le projet

---

## v1.7 — Images de projets

- Champ `image_path` sur la table `projects`
- Upload + prévisualisation dans le formulaire
- Cartes projet avec bannière image (160px)
- Route serving `instance/project_images/`

---

## v1.8 — Étiquettes imprimables + QR code

- Route `GET /labels?ids=1,2,3` : impression multi-étiquettes
- Format 6×3cm par défaut, CSS `@media print` mm
- QR code généré **en Python pur** (`qr_generator.py`), zéro CDN externe
- Cases à cocher multi-sélection dans le tableau + barre flottante
- Bouton 🏷️ sur chaque fiche composant

---

## v1.9 — Symbole & Footprint EasyEDA

- Appel `easyeda.com/api/products/<ref>/svgs`
- Téléchargement PNG (symbole via champ `png` EasyEDA, footprint via SVG)
- Redimensionnement 400×400 avec Pillow, fond blanc
- Cache dans `instance/easyeda_pngs/`
- Galerie sur la fiche détail (Photo / Symbole / Footprint)
- Lightbox unifiée, clic pour charger à la demande

---

## v1.10 — Support export panier LCSC

- Import CSV format `export_cart_*.csv`
- Détection automatique du format (commande vs panier)
- Page import BOM mise à jour

---

## v1.11 — Refonte page projet

- Tableau unique avec lignes séparateurs de catégorie (colonnes alignées)
- Barre de stats compacte avec barre de progression %
- Formulaire d'ajout rétractable
- Boutons d'action épurés : 🛒 − + 🗑
- Images cliquables → lightbox

---

## v1.12 — Configuration des étiquettes

- Page `/label-settings` avec aperçu en temps réel
- Format, couleurs, tailles de police, 11 toggles on/off
- Config sauvegardée en base, appliquée à l'impression via CSS Jinja

---

## v1.13 — Page Paramètres enrichie

- Nom de l'application, adresse de base QR codes, seuil d'alerte par défaut
- Sauvegarde ZIP, stats base, enrichissement en masse, nettoyage images

---

## v1.14 — Nettoyage du code

- Suppression `movement.py`, `history.html`, `qr.js`, table `stock_movements`
- Suppression `save_easyeda_svgs()`, `get_categories()`, attributs SVG obsolètes
- Suppression API officielle LCSC jamais utilisée
- Correction `adjust_quantity()` — résidu `note=` retiré

---

## v1.15 — Refonte visuelle complète

### Page stock (index)
- **Barre de stats compacte** — 4 chiffres inline avec séparateurs verticaux, remplace les 4 grandes cartes
- **Badges RoHS/DS inline** — sur la même ligne que la description, plus petits (`badge-xs`)
- **Seuil d'alerte compact** — `⚡4` discret avec tooltip, remplace le label verbeux
- **Lignes plus denses** — padding vertical réduit

### Page d'ajout de composant
- **Layout deux colonnes** — infos à gauche, stock/prix sticky à droite
- **Grille 3 colonnes** pour les références (LCSC / Réf. fab. / Fabricant)
- **Calcul auto du prix total** — badge `= 12.50 €` en temps réel
- **Champ quantité mis en avant** — grand, centré, coloré

### Page d'édition de composant
- Alignée sur le même layout que la page d'ajout
- CSS partagé dans `style.css` (plus de styles inline)

### Fiche composant (detail)
- **Layout deux colonnes** — carte principale + colonne stock sticky
- **Galerie repensée** — grande photo principale (180×180) + 2 vignettes symbole/footprint côte à côte en dessous
- **Champs vides masqués** — N° client, emplacement, etc. n'apparaissent que s'ils sont remplis
- **Datasheet en badge violet** intégré dans la ligne de badges
- **Référence LCSC cliquable** vers lcsc.com
- **Valeur totale en stock calculée** automatiquement (prix × quantité)
- **Toolbar supprimée** — plus de doublons, actions dans la colonne de droite uniquement

### Page import CSV
- **Deux cartes format** — Export commande + Export panier, colonnes en tags monospace
- **Zone de drop améliorée** — état "fichier prêt" avec nom et bouton changer
- **Warning API LCSC obsolète supprimé**
- **Bouton Importer désactivé** tant qu'aucun fichier n'est sélectionné

### Page projets (liste)
- **Grille `auto-fill`** — s'adapte à la largeur (4 → 3 → 2 → 1 colonnes)
- **Badge statut sur l'image** avec `backdrop-filter: blur`
- **Cartes à hauteur uniforme**
- **Footer stats repensé** — "Aucun composant" si vide, date alignée à droite
- **Compteur dans le titre** — badge avec nombre total de projets

### Rapport BOM KiCad
- Barre de stats compacte en remplacement des grandes cartes
- En-têtes de section avec bordure colorée (vert/orange/rouge)

### CSS global
- **46Ko → 40Ko** — 52 blocs et classes mortes supprimés
- CSS du layout formulaire centralisé dans `style.css`

---

## Corrections de bugs notables

| Version | Bug | Correction |
|---|---|---|
| v1.1 | Thread enrichissement tué par le reloader | `use_reloader=False` dans `run.py` |
| v1.8 | QR code manquant sur les copies 2, 3… | Génération serveur Python pur |
| v1.10 | Import panier LCSC : champs vides | Mapping `LCSC#` → `lcsc_part_number` |
| v1.12 | Config étiquettes ignorée à l'impression | CSS généré dynamiquement par Jinja |
| v1.12 | Page impression blanche | `False` Python → `false` JS, parenthèses sur `\| tojson` |
| v1.14 | `TypeError: adjust_quantity() got unexpected kwarg 'note'` | Résidu `note=` retiré |
| v1.15 | Page édition sans layout (colonne unique) | CSS `add-layout` déplacé dans `style.css` |