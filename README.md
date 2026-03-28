# StockElec 📦⚡

Application de gestion de stock de composants électroniques pour makers et hobbyistes.
Développée avec **Flask + SQLite**, architecture **MVC**, thème sombre.

![C2326](https://github.com/user-attachments/assets/4b2f03ce-ccde-4ce1-a423-be80b11c394d)


---

## Installation

```bash
# 1. Environnement virtuel
python -m venv venv
source venv/bin/activate        # Linux / macOS
venv\Scripts\activate           # Windows

# 2. Dépendances
pip install -r requirements.txt

# 3. Lancer
python run.py
```

Accessible sur **http://127.0.0.1:5000**

> `use_reloader=False` est intentionnel — le reloader de Flask tuerait les threads d'enrichissement LCSC en arrière-plan.

---

## Fonctionnalités

### 📦 Stock
- Tableau paginé (25/50/100) avec miniatures, recherche, filtres catégorie, tri
- Barre de stats compacte (références, pièces, valeur totale, fabricants)
- Badges RoHS/DS inline, seuil d'alerte discret ⚡
- Cases à cocher multi-sélection + barre flottante (étiquettes)
- Ajustement rapide +/− AJAX

### ➕ Ajout en série
- Layout deux colonnes : infos + Import rapide LCSC à gauche, stock/prix sticky à droite
- Import rapide LCSC : ref → prévisualisation → pré-remplissage en un clic
- Calcul automatique prix total (quantité × unitaire)
- **Mode série** : après validation, reste sur la page avec un bandeau vert de confirmation — pas besoin de naviguer pour ajouter le composant suivant

### ✏️ Édition
- Même layout que l'ajout, données pré-remplies
- Calcul automatique prix total mis à jour en temps réel

### 📥 Import CSV LCSC
Deux formats détectés automatiquement :

| Format | Colonnes clés |
|---|---|
| Export commande | `LCSC Part Number`, `Manufacture Part Number`, `Ext.Price(€)` |
| Export panier (`export_cart_*.csv`) | `LCSC#`, `MPN`, `Extended Price(€)` |

- Drag & drop ou sélection fichier, bouton désactivé sans fichier sélectionné
- Déduplication automatique par référence LCSC
- Enrichissement en arrière-plan après import

### 🔍 Enrichissement LCSC automatique
Scrape `wmsc.lcsc.com` pour récupérer catégorie, image et datasheet.
Thread daemon, ~0.6s entre requêtes. Bouton 📷 pour relancer manuellement.

### 🖼️ Symbole & Footprint EasyEDA
Sur la fiche composant : grande photo (180×180) + 2 vignettes (symbole / footprint) côte à côte.
Chargement à la demande, cache dans `instance/easyeda_pngs/`, lightbox au clic.

### 🗂️ Projets
- CRUD avec image bannière, grille auto-fill responsive
- Tableau composants groupés par catégorie, colonnes alignées
- Barre de progression disponibilité (n/n %)
- Formulaire d'ajout rétractable
- Boutons −/+ AJAX pour débiter/restituer le stock
- Import BOM KiCad avec rapport ✅/⚠️/❌/—

### 🏷️ Étiquettes imprimables
- Impression multi-étiquettes depuis la sélection ou la fiche
- QR code généré en Python pur (zéro dépendance externe)
- Copies multiples par étiquette, grille auto-fill dans l'aperçu

### ⚙️ Configuration des étiquettes (`/label-settings`)
- Format (largeur × hauteur mm), couleurs fond/texte/badges
- Tailles de police, 11 toggles on/off
- Aperçu en temps réel avec un vrai composant du stock
- Config sauvegardée en base, appliquée automatiquement à l'impression

### 🔔 Alertes stock bas
- Seuil `min_stock` par composant
- Page dédiée + bandeau rouge sur l'accueil

---

## Paramètres (`/settings`)

| Section | Contenu |
|---|---|
| 🏠 Général | Nom de l'app (navbar), adresse de base QR codes, seuil d'alerte par défaut |
| 🏷️ Étiquettes | Lien vers `/label-settings` |
| 💾 Sauvegarde | ZIP complet (base + images) |
| 📊 Stats | Composants, projets, tailles, alertes de complétude |
| 🔍 Enrichissement | Relance sur tous les composants incomplets |
| 🖼️ EasyEDA | Télécharge les symboles/footprints manquants + réconciliation avec les fichiers existants |
| 🧹 Nettoyage | Supprime les images orphelines |

---

## Structure du projet

```
stock_composants/
├── run.py                              # Point d'entrée (debug=True, use_reloader=False)
├── requirements.txt
├── README.md
├── CHANGELOG.md
└── app/
    ├── __init__.py                     # Factory Flask, context_processor app_name
    ├── models/
    │   ├── database.py                 # SQLite, schéma, migrations à chaud
    │   ├── component.py                # CRUD composants, pagination, déduplication
    │   ├── category.py                 # Arborescence catégories LCSC
    │   ├── project.py                  # CRUD projets, liaison composants
    │   └── settings.py                 # Config clé/valeur persistée
    ├── views/
    │   └── component_view.py
    ├── controllers/
    │   ├── component_controller.py     # Routes stock, import, enrichissement, étiquettes, paramètres
    │   └── project_controller.py       # Routes projets, BOM KiCad, débit/restitution
    ├── services/
    │   ├── lcsc_scraper.py             # Scraping wmsc.lcsc.com
    │   ├── easyeda.py                  # PNGs symbole/footprint EasyEDA
    │   └── qr_generator.py             # QR code SVG Python pur
    ├── templates/
    │   ├── base.html                   # Layout commun (navbar, nom dynamique)
    │   ├── partials/category_select.html
    │   ├── components/
    │   │   ├── index.html              # Tableau stock
    │   │   ├── add.html                # Ajout + import rapide LCSC + mode série
    │   │   ├── edit.html               # Édition (même layout que add)
    │   │   ├── detail.html             # Fiche composant
    │   │   ├── import.html             # Import CSV drag & drop
    │   │   ├── alerts.html             # Alertes stock bas
    │   │   ├── labels_print.html       # Impression étiquettes
    │   │   ├── label_settings.html     # Config étiquettes (aperçu live)
    │   │   └── settings.html           # Paramètres
    │   └── projects/
    │       ├── index.html              # Grille projets
    │       ├── form.html               # Création/édition projet
    │       ├── detail.html             # Tableau composants + stats
    │       ├── import_bom.html         # Import BOM KiCad
    │       └── bom_report.html         # Rapport ✅/⚠️/❌/—
    └── static/
        ├── css/style.css               # ~40Ko, thème sombre complet
        └── js/app.js
```

---

## Base de données

SQLite dans `instance/stock.db` (créée automatiquement au démarrage).

| Table | Rôle |
|---|---|
| `components` | Stock (ref LCSC unique, prix, image, symbol/footprint PNG) |
| `categories` | Arborescence LCSC |
| `projects` | Projets avec image optionnelle |
| `project_components` | Liaison composants ↔ projets |
| `settings` | Configuration clé/valeur |

Les migrations sont appliquées **à chaud** — pas de perte de données sur une base existante.

---

## API JSON

| Endpoint | Description |
|---|---|
| `GET /api/components` | Liste composants (`?search=`) |
| `GET /api/lcsc-preview?ref=C149504` | Prévisualisation LCSC |
| `POST /component/<id>/adjust` | `{"delta": ±N}` |
| `POST /enrich/<id>` | Relance enrichissement LCSC |
| `GET /labels?ids=1,2,3` | Page impression étiquettes |
| `GET /api/easyeda-pngs/<ref>` | PNG EasyEDA |
| `GET /label-settings` | Config étiquettes |

---

## Dépannage

**Images et catégories vides après import**
Flask doit tourner avec `use_reloader=False` (déjà configuré). Les logs affichent `[LCSC] C149504 — enrichi`.

**QR code ne fonctionne pas sur mobile**
Configurer l'adresse de base dans ⚙️ Paramètres → Général → "Adresse de base".
Ex : `http://192.168.1.50:5000`. Lancer aussi Flask avec `host='0.0.0.0'` dans `run.py`.

**Symboles/footprints affichés dans les fiches mais compteur ⚙️ indique des manquants**
Utiliser le bouton **🔗 Réconcilier avec les fichiers** dans les paramètres — les fichiers PNG existent mais leurs chemins ne sont pas enregistrés en base.

**BOM KiCad non reconnue**
Les composants KiCad doivent avoir un champ `LCSC Part Number` (ou variante) renseigné.

**Réinitialiser la base**
Supprimer `instance/stock.db` et relancer. Les images peuvent être conservées.
