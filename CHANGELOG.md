# Changelog — StockElec

Historique complet de toutes les fonctionnalités développées.

---

## v1.0 — Base de l'application

- Architecture **Flask + SQLite + MVC** (models / views / controllers)
- **Page d'accueil** : tableau de tous les composants avec stats (références, quantités, valeur totale, fabricants)
- **Import CSV LCSC** : glisser-déposer ou sélection, colonnes LCSC reconnues automatiquement
- **Ajout manuel** : formulaire complet (description, référence LCSC, fabricant, package, RoHS, quantité, prix, emplacement, notes)
- **Fiche détail** : vue complète d'un composant
- **Édition / suppression** de composants
- **Recherche** : filtrage par description, référence LCSC, référence fabricant, fabricant, package
- **Tri** : par description, fabricant, package, quantité, prix, date d'ajout
- **Catégories** : filtre par catégorie
- **Emplacement** : champ libre (boîte, tiroir…)
- **API JSON** : `GET /api/components?search=...`
- **Thème sombre** avec interface responsive

---

## v1.1 — Enrichissement LCSC (scraping)

- **Service `lcsc_scraper.py`** : scraping de l'endpoint interne `wmsc.lcsc.com/ftps/wm/product/detail`
- Récupération automatique de la **catégorie**, **sous-catégorie**, **image** et **datasheet** après import
- **Téléchargement local des images** dans `instance/images/`
- Enrichissement en **thread d'arrière-plan** avec pause ~0.6s entre requêtes
- Bouton **📷** dans le tableau pour relancer l'enrichissement manuellement
- **Table `categories`** en base : arborescence LCSC (id, parent_id, full_path)
- **Miniatures** des composants dans le tableau (clic pour agrandir — lightbox)
- **Badge Datasheet** sur les fiches avec lien PDF

---

## v1.2 — Déduplication et pagination

- **Déduplication à l'import** : détection des doublons par référence LCSC (colonne UNIQUE), message d'avertissement listant les références déjà en stock
- **Pagination** du tableau (25 / 50 / 100 par page) avec navigation numérotée et fenêtre glissante
- Sélecteur de nombre d'éléments par page persisté dans l'URL

---

## v1.3 — Ajout rapide depuis LCSC

- **Bloc "⚡ Import rapide LCSC"** en haut du formulaire d'ajout
- Saisie d'une référence LCSC → prévisualisation instantanée (image, nom, fabricant, catégorie)
- Pré-remplissage automatique de tous les champs du formulaire
- Détection si le composant est **déjà en stock** avant même de continuer
- Déclenchement sur **Entrée** ou clic sur le bouton
- Route `GET /api/lcsc-preview?ref=C149504` (ne crée rien en base)

---

## v1.4 — Projets, historique, alertes et ajustement rapide

### Projets
- **Table `projects`** et **table de liaison `project_components`**
- CRUD complet : créer, éditer, supprimer des projets (nom, description, statut)
- Associer des composants à un projet avec quantité nécessaire
- Vérification de **disponibilité stock** en temps réel (badge ✓ / ✗)
- Boutons **🔧 Débiter** et **↩️ Restituer** pour ajuster le stock depuis la fiche projet (AJAX)
- Sur la fiche composant : liste des projets qui l'utilisent

### Historique des mouvements
- **Table `stock_movements`** : trace tous les mouvements (import, ajout, retrait, ajustement, projet)
- Page **📋 Historique** : 200 derniers mouvements avec stats globales (entrées / sorties)
- Sur la fiche composant : 20 derniers mouvements avec type, delta, avant/après

### Alertes stock bas
- Champ **`min_stock`** par composant (seuil d'alerte)
- Page **🔔 Alertes** : liste des composants sous seuil, triés par urgence
- Bandeau rouge sur l'accueil si des alertes sont actives
- Ajustement +/− directement depuis la page alertes
- Disparition en fondu d'une ligne quand le seuil est repassé

### Ajustement rapide
- Boutons **+** / **−** directement dans le tableau et sur la fiche détail
- Mise à jour **AJAX instantanée** sans rechargement
- Chaque ajustement enregistré automatiquement dans l'historique

---

## v1.5 — Catégories hiérarchiques

- Nouveau filtre avec **`<optgroup>`** HTML : les sous-catégories sont groupées sous leur parent
- Méthode `CategoryModel.get_grouped_for_stock()` : construit l'arbre uniquement depuis les catégories réellement présentes en stock
- **Macro Jinja** `partials/category_select.html` : composant réutilisable importé dans index, add et edit
- Gestion du breadcrumb LCSC `parentCatalogList` : arborescence complète stockée en base
- Formulaires d'ajout et d'édition : le champ catégorie texte libre remplacé par le select hiérarchique
- Compatibilité JS : `setVal()` gère les `<select>` pour le pré-remplissage depuis LCSC

---

## v1.6 — Import BOM KiCad

- **Route `POST /projects/<id>/import-bom`** : upload d'un CSV KiCad
- Détection automatique du séparateur (`,` ou `;`)
- Reconnaissance de multiples noms de colonnes LCSC : `LCSC Part Number`, `LCSC Part #`, `LCSC`, `Supplier Part Number`
- **Rapport de disponibilité** en 4 catégories :
  - ✅ En stock (quantité suffisante) — pré-cochés
  - ⚠️ Stock insuffisant — colonne "Manquant"
  - ❌ Absent du stock — bouton 🛒 LCSC → pour commander
  - — Sans référence LCSC
- Validation sélective : coche les composants à ajouter au projet
- Détection des composants **déjà dans le projet** (badge ✓, pas de doublon)
- Bouton **📋 Importer une BOM KiCad** sur la fiche projet

---

## v1.7 — Images de projets

- Champ **`image_path`** sur la table `projects`
- Upload d'image (JPG, PNG, WEBP, GIF) sur le formulaire de création/édition
- Prévisualisation instantanée avant envoi
- Bouton ✕ pour supprimer l'image courante
- Images stockées dans `instance/project_images/` avec nom UUID
- Suppression automatique du fichier quand le projet est supprimé
- **Cartes projet** redessinées : bannière image (160px), fallback 🔌 si pas d'image
- Route `GET /projects/project-images/<filename>` pour servir les fichiers

---

## v1.8 — Étiquettes imprimables + QR code

- Route `GET /component/<id>/label` : page dédiée à l'impression d'étiquettes
- Format **6×3cm** (paysage), CSS `@media print` avec dimensions en mm
- Contenu : image, description, références (LCSC/MFR/fabricant), badges (package, RoHS, quantité, emplacement, catégorie), prix
- **QR code** généré côté serveur en **Python pur** (`app/services/qr_generator.py`) — zéro dépendance externe, zéro CDN, fonctionne hors ligne
- QR code encodé en SVG + base64 data URL, injecté directement dans le HTML
- Choix du **nombre de copies** (1 à 100) et du **niveau d'information** (complet / minimal)
- Template entièrement **commenté** pour faciliter la personnalisation du CSS
- Bouton **🏷️ Étiquette** sur la fiche détail de chaque composant

---

## v1.9 — Impression d'étiquettes en masse

- **Cases à cocher** sur chaque ligne du tableau principal
- **Case en en-tête** avec état indéterminé (⊟) pour tout sélectionner / tout désélectionner
- **Barre d'actions flottante** animée qui apparaît dès qu'au moins un composant est coché :
  - Affiche le nombre de composants sélectionnés
  - Bouton **🏷️ Imprimer les étiquettes** → ouvre la page multi-étiquettes dans un nouvel onglet
  - Bouton **✕ Désélectionner** pour vider la sélection
- **Page `/labels?ids=1,2,3...`** : impression multi-étiquettes
  - QR code individuel généré côté serveur pour chaque composant
  - Choix du nombre de **copies par étiquette** (1 à 20)
  - Résumé visuel des composants sélectionnés (miniatures + noms) avant impression
  - Même format 6×3cm et mêmes options que l'étiquette unitaire
- Route `/component/<id>/label` redirige désormais vers la page multi (rétrocompatible)
- Workflow typique : *filtrer par catégorie → cocher l'en-tête → 🏷️ Imprimer* = toutes les étiquettes d'une catégorie en 3 clics

---

## Corrections de bugs notables

| Version | Bug | Correction |
|---|---|---|
| v1.1 | Thread d'enrichissement tué par le reloader Flask | `use_reloader=False` dans `run.py` |
| v1.1 | Erreurs silencieuses dans le scraper | Logs `INFO`/`WARNING` sur chaque étape |
| v1.1 | Clé `data` au lieu de `result` dans la réponse LCSC | Correction après inspection de la vraie réponse JSON |
| v1.5 | `setVal()` ne fonctionnait pas sur les `<select>` | Gestion explicite des éléments `SELECT` + ajout dynamique d'option |
| v1.8 | QR code manquant sur les copies 2, 3, 4… | Abandon du CDN + génération serveur en Python pur |
| v1.8 | Page étiquette blanche (CDN bloqué en local) | QR généré côté serveur, aucune dépendance externe |
