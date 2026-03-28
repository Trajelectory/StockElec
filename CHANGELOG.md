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
- Thread daemon avec pause ~0.6s entre requêtes
- Bouton 📷 pour relancer manuellement

---

## v1.2 — Déduplication et pagination

- Déduplication à l'import par référence LCSC (UNIQUE en base)
- Pagination (25 / 50 / 100 par page)

---

## v1.3 — Ajout rapide depuis LCSC

- Bloc "⚡ Import rapide LCSC" : saisie ref → prévisualisation → pré-remplissage
- Route `GET /api/lcsc-preview?ref=C149504`

---

## v1.4 — Projets et alertes stock

- CRUD projets avec image bannière
- Vérification disponibilité en temps réel, boutons Débiter / Restituer (AJAX)
- Champ `min_stock`, page 🔔 Alertes + bandeau rouge accueil
- Boutons +/− AJAX dans le tableau et sur la fiche détail

---

## v1.5 — Catégories hiérarchiques

- Filtre avec `<optgroup>` par sous-catégorie
- Macro Jinja `category_select.html` réutilisable

---

## v1.6 — Import BOM KiCad

- Upload CSV KiCad → rapport ✅/⚠️/❌/—
- Formats reconnus : KiCad 7/8, plugin JLCPCB, bom2csv

---

## v1.7 — Images de projets

- Upload + prévisualisation dans le formulaire
- Cartes projet avec bannière image

---

## v1.8 — Étiquettes imprimables + QR code

- Route `GET /labels?ids=1,2,3` : impression multi-étiquettes
- QR code généré **en Python pur** (`qr_generator.py`), zéro CDN externe
- Cases à cocher multi-sélection dans le tableau + barre flottante

---

## v1.9 — Symbole & Footprint EasyEDA

- Téléchargement PNG symbole + footprint, cache dans `instance/easyeda_pngs/`
- Galerie sur la fiche détail (Photo / Symbole / Footprint)
- Lightbox unifiée, clic pour charger à la demande

---

## v1.10 — Support export panier LCSC

- Import CSV format `export_cart_*.csv` détecté automatiquement

---

## v1.11 — Refonte page projet

- Tableau unique colonnes alignées, barre de stats compacte, formulaire rétractable
- Boutons d'action épurés, images cliquables → lightbox

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
- Suppression API officielle LCSC, `save_easyeda_svgs()`, `get_categories()`
- Correction `adjust_quantity()` — résidu `note=` retiré

---

## v1.15 — Refonte visuelle complète

### Page stock
- Barre de stats compacte (4 chiffres inline), badges RoHS/DS inline, seuil ⚡ discret

### Formulaires ajout / édition
- Layout deux colonnes : infos à gauche, stock/prix sticky à droite
- Grille 3 colonnes pour les références, calcul auto prix total
- Bloc "Import rapide LCSC" intégré dans la colonne principale (même largeur que les sections)

### Fiche composant
- Galerie : grande photo (180×180) + 2 vignettes symbole/footprint côte à côte
- Champs vides masqués, datasheet en badge violet, ref LCSC cliquable
- Valeur totale en stock calculée, toolbar supprimée (actions dans la sidebar)

### Page import CSV
- Deux cartes format (commande + panier), zone de drop améliorée
- Warning API obsolète supprimé, bouton désactivé sans fichier

### Page projets (liste)
- Grille `auto-fill` responsive, badge statut sur l'image, cartes hauteur uniforme

### Rapport BOM KiCad
- Barre de stats compacte, en-têtes de section avec bordure colorée

### Page impression étiquettes
- Toolbar compacte tout-en-un, bloc "Composants sélectionnés" supprimé
- Étiquettes plus grandes (4.8x), grille auto-fill

### CSS global
- 46Ko → 40Ko — 52 blocs et classes morts supprimés
- CSS formulaire centralisé dans `style.css`

---

## v1.16 — Mode ajout en série

- Après validation, reste sur la page d'ajout au lieu de rediriger vers le stock
- Bandeau vert animé "✅ [Composant] ajouté — voir le stock →"
- Lien direct vers le stock depuis le bandeau

---

## v1.17 — Téléchargement EasyEDA en masse + réconciliation

### Téléchargement en masse
- Bouton dans ⚙️ Paramètres → "🖼️ Télécharger les manquants"
- Lance un thread en arrière-plan (0.5s entre requêtes)
- Compteur des composants sans symbole/footprint

### Réconciliation
- Bouton "🔗 Réconcilier avec les fichiers" dans les paramètres
- Scanne `instance/easyeda_pngs/` et met à jour les colonnes manquantes en base
- Résout le cas où les fichiers existent physiquement mais ne sont pas référencés en DB

---

## v1.18 — Nettoyage final

- Suppression des fichiers de debug : `debug_lcsc.py`, `debug_easyeda.py`
- Racine du projet réduite à l'essentiel : `run.py`, `requirements.txt`, `README.md`, `CHANGELOG.md`, `app/`

---

## Corrections de bugs notables

| Version | Bug | Correction |
|---|---|---|
| v1.1 | Thread enrichissement tué par le reloader | `use_reloader=False` dans `run.py` |
| v1.8 | QR code manquant sur les copies 2, 3… | Génération serveur Python pur |
| v1.10 | Import panier LCSC : champs vides | Mapping `LCSC#` → `lcsc_part_number` |
| v1.12 | Config étiquettes ignorée à l'impression | CSS généré dynamiquement par Jinja |
| v1.12 | Page impression blanche | `False` Python → `false` JS (`\| tojson`) |
| v1.14 | `TypeError: adjust_quantity() got unexpected kwarg 'note'` | Résidu `note=` retiré |
| v1.15 | Page édition sans layout (colonne unique) | CSS `add-layout` déplacé dans `style.css` |

---

## v1.19 — Catégories personnalisées

- Nouvelle page **⚙️ Paramètres → 🗂️ Gérer les catégories** (`/categories`)
- Création de groupes et sous-catégories personnalisées (IDs négatifs, sans conflit avec LCSC)
- Suppression individuelle (sous-catégorie) ou en masse (groupe entier + enfants)
- Les composants liés à une catégorie supprimée sont remis sans catégorie
- Les catégories custom apparaissent immédiatement dans les selects Ajouter/Éditer
- Les catégories LCSC restent intouchables
- Suggestion automatique des groupes existants via `<datalist>`
- Interface épurée : arborescence avec ligne verticale, boutons discrets (rouge au survol)

---

## v1.20 — Upload d'image manuelle

- Champ **🖼️ Image** dans les formulaires Ajouter et Éditer
- Prévisualisation instantanée avant upload (FileReader JS)
- Formats acceptés : JPG, PNG, WEBP
- Sauvegarde dans `instance/images/` — même dossier que les images LCSC
- Utile pour les composants hors LCSC (vis, fils, modules Arduino, etc.)
- Si un enrichissement LCSC se déclenche ensuite, l'image LCSC remplace la manuelle

---

## v1.21 — Améliorations diverses

### Alertes flash
- Classes `.alert-success`, `.alert-info`, `.alert-warning`, `.alert-danger` restaurées
- Avaient été supprimées par erreur lors du nettoyage CSS v1.15 (générées dynamiquement par Flask)

### Pagination
- Ajout de l'option **5 par page** dans le tableau stock (en plus de 25/50/100)

### EasyEDA — liste des composants manquants
- La section EasyEDA dans les paramètres affiche désormais la liste détaillée des composants sans symbole/footprint
- Chaque ligne : nom cliquable vers la fiche, référence LCSC, badges ✗ symbole / ✗ footprint
- Liste scrollable, limitée à 220px

### Corrections de bugs
- `NameError: new_qty is not defined` dans `ComponentModel.update()` — variable résiduelle remplacée par `int(data.get("quantity") or 0)`
- `scrollIntoView('add-form')` dans `applyPreview()` supprimé — élément inexistant depuis la fusion des blocs
