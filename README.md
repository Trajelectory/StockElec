# StockElec 📦⚡

Application de gestion de stock pour composants électroniques, pensée pour les makers et hobbyistes.  
Développée avec **Flask + SQLite**, architecture **MVC**.

---

## Installation

```bash
# 1. Créer et activer un environnement virtuel
python -m venv venv
source venv/bin/activate        # Linux / macOS
venv\Scripts\activate           # Windows

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. Lancer l'application
python run.py
```

L'application est accessible sur **http://127.0.0.1:5000**

> **Important** : `run.py` lance Flask avec `use_reloader=False`. C'est intentionnel — le reloader de Flask tuerait les threads d'enrichissement LCSC en arrière-plan avant qu'ils terminent.

---

## Fonctionnalités

### 📦 Gestion du stock

- **Tableau paginé** (25 / 50 / 100 par page) avec miniatures des composants
- **Recherche** par description, référence LCSC, référence fabricant, fabricant, package
- **Filtres** par catégorie (menu hiérarchique avec optgroup) et tri multi-colonnes
- **Fiche détail** complète : image grand format, datasheet, catégorie, historique des mouvements, projets liés
- **Ajout / édition / suppression** de composants
- **Seuil d'alerte** (`min_stock`) par composant — badge orange + page dédiée 🔔

### ⚡ Ajustement rapide

- Boutons **+** / **−** directement dans le tableau et sur la fiche détail
- Mise à jour AJAX instantanée, sans rechargement de page
- Chaque ajustement est automatiquement enregistré dans l'historique

### 📥 Import CSV LCSC

- Glisser-déposer ou sélection de fichier
- **Déduplication automatique** : les composants déjà en stock (même référence LCSC) sont détectés et listés dans un message d'avertissement, sans être dupliqués
- Après l'import, enrichissement automatique en arrière-plan (catégories + images) via le scraper LCSC

### ➕ Ajout rapide depuis LCSC

Sur la page **Ajouter un composant**, un bloc "⚡ Import rapide LCSC" permet de :
1. Saisir une référence LCSC (ex: `C149504`) et appuyer sur Entrée
2. Voir une prévisualisation instantanée (image, nom, fabricant, catégorie)
3. Cliquer **✓ Utiliser ces données** — tous les champs du formulaire se pré-remplissent
4. N'avoir plus qu'à saisir la quantité et valider

Détecte aussi si le composant est **déjà en stock** avant de continuer.

### 🔍 Enrichissement LCSC automatique

L'application scrape l'endpoint interne LCSC (`wmsc.lcsc.com`) pour récupérer :
- **Catégorie** et sous-catégorie (ex: `Resistors / Chip Resistor - Surface Mount`)
- **Image** du composant (téléchargée localement dans `instance/images/`)
- **Datasheet** (lien PDF)

L'enrichissement se fait **en arrière-plan** (thread daemon) après chaque import CSV ou ajout manuel, avec une pause de ~0.6s entre chaque requête pour ne pas surcharger LCSC. Un bouton 📷 dans le tableau permet de relancer l'enrichissement manuellement sur un composant.

> **Note** : le scraping utilise l'endpoint non-officiel de LCSC. Il peut être soumis à des limitations ou des changements de leur côté.

### 🗂️ Projets

- Créer des projets avec **nom, description, statut** et une **image** (photo PCB, boîtier, schéma…)
- Les cartes projet affichent l'image en bannière pour une identification visuelle rapide
- Associer des composants à un projet avec une **quantité nécessaire**
- Vérification de **disponibilité stock** en temps réel (badge ✓ / ✗)
- Boutons **🔧 Débiter** et **↩️ Restituer** pour ajuster le stock depuis la fiche projet
- Sur la fiche d'un composant, liste des projets qui l'utilisent

### 📋 Import BOM KiCad

Depuis la fiche d'un projet, le bouton **📋 Importer une BOM KiCad** permet de :
1. Déposer un fichier CSV exporté depuis KiCad
2. Obtenir un **rapport de disponibilité** en 4 catégories :
   - ✅ **En stock** — quantité suffisante (cochés par défaut)
   - ⚠️ **Stock insuffisant** — présent mais pas assez, la colonne "Manquant" indique le delta
   - ❌ **Absent du stock** — avec un bouton 🛒 LCSC → pour commander directement
   - **—** Sans référence LCSC (connecteurs, DNP…)
3. Cocher les composants à ajouter et valider en un clic

Formats KiCad reconnus automatiquement :
- KiCad 7/8 natif (`Tools → Edit Symbol Fields → Export`)
- Plugin JLCPCB (`Comment, Designator, Footprint, LCSC Part Number`)
- bom2csv avec séparateur `;`
- Noms de colonnes LCSC reconnus : `LCSC Part Number`, `LCSC Part #`, `LCSC`, `Supplier Part Number`

### 📋 Historique des mouvements

Toutes les opérations sont tracées automatiquement :

| Type | Déclencheur |
|---|---|
| 📥 Import CSV | Import d'un fichier CSV |
| ➕ Ajout manuel | Création d'un composant avec quantité > 0 |
| ➖ Retrait manuel | Bouton − dans le tableau |
| ✏️ Ajustement | Modification de quantité via le formulaire d'édition |
| 🔧 Utilisé (projet) | Bouton "Débiter" sur un projet |
| ↩️ Retour (projet) | Bouton "Restituer" sur un projet |

Consultable par composant (fiche détail, 20 derniers) ou globalement (page Historique, 200 derniers).

### 🔔 Alertes stock bas

- Page dédiée listant tous les composants sous leur seuil `min_stock`
- Bandeau rouge sur l'accueil si des alertes sont actives
- Ajustement +/− disponible directement sur la page alertes
- La ligne disparaît en fondu une fois le seuil repassé

---

## Format CSV supporté (LCSC)

Le fichier CSV exporté depuis [lcsc.com](https://lcsc.com) → *Orders* → *Export* est importé directement.

| Colonne CSV | Champ en base |
|---|---|
| `LCSC Part Number` | `lcsc_part_number` (clé unique) |
| `Manufacture Part Number` | `manufacture_part_number` |
| `Manufacturer` | `manufacturer` |
| `Customer NO.` | `customer_no` |
| `Package` | `package` |
| `Description` | `description` |
| `RoHS` | `rohs` |
| `Quantity` | `quantity` |
| `Unit Price(€)` | `unit_price` |
| `Ext.Price(€)` | `ext_price` |

---

## Structure du projet

```
stock_composants/
├── run.py                              # Point d'entrée (debug=True, use_reloader=False)
├── requirements.txt                    # flask, requests
├── debug_lcsc.py                       # Script de diagnostic endpoint LCSC
└── app/
    ├── __init__.py                     # Factory Flask (create_app), chargement config
    │
    ├── models/
    │   ├── database.py                 # Connexion SQLite, schéma, migrations à chaud
    │   ├── component.py                # CRUD composants, pagination, déduplication
    │   ├── category.py                 # Arborescence catégories LCSC, optgroups
    │   ├── project.py                  # CRUD projets, liaison composants
    │   ├── movement.py                 # Historique des mouvements de stock
    │   └── settings.py                 # Configuration clé/valeur (persistée en DB)
    │
    ├── views/
    │   └── component_view.py           # Couche Vue — appels render_template
    │
    ├── controllers/
    │   ├── component_controller.py     # Routes stock, import, enrichissement, alertes
    │   └── project_controller.py       # Routes projets, BOM KiCad, débit/restitution
    │
    ├── services/
    │   └── lcsc_scraper.py             # Scraping wmsc.lcsc.com, téléchargement images
    │
    ├── templates/
    │   ├── base.html                   # Layout commun (navbar, flash messages)
    │   ├── partials/
    │   │   └── category_select.html    # Macro Jinja : <select> hiérarchique réutilisable
    │   ├── components/
    │   │   ├── index.html              # Tableau stock paginé
    │   │   ├── add.html                # Ajout manuel + import rapide LCSC
    │   │   ├── edit.html               # Formulaire édition
    │   │   ├── detail.html             # Fiche composant complète
    │   │   ├── import.html             # Import CSV drag & drop
    │   │   ├── alerts.html             # Page alertes stock bas
    │   │   ├── history.html            # Historique global des mouvements
    │   │   └── settings.html           # Page paramètres
    │   └── projects/
    │       ├── index.html              # Liste des projets (cartes avec image)
    │       ├── form.html               # Création / édition projet (avec upload image)
    │       ├── detail.html             # Fiche projet + gestion composants
    │       ├── import_bom.html         # Upload BOM KiCad
    │       └── bom_report.html         # Rapport de disponibilité BOM
    │
    └── static/
        ├── css/style.css               # Thème sombre, tous les composants UI
        └── js/app.js                   # Auto-dismiss alertes
```

---

## Base de données

SQLite stockée dans `instance/stock.db` (créée automatiquement au premier lancement).

| Fichier/Dossier | Contenu |
|---|---|
| `instance/stock.db` | Base de données SQLite |
| `instance/images/` | Images des composants (téléchargées depuis LCSC) |
| `instance/project_images/` | Images uploadées pour les projets |

### Schéma

| Table | Rôle |
|---|---|
| `components` | Stock de composants (référence LCSC unique) |
| `categories` | Arborescence des catégories LCSC (id, parent_id, full_path) |
| `projects` | Projets électroniques (avec image optionnelle) |
| `project_components` | Liaison composants ↔ projets avec quantité |
| `stock_movements` | Historique de tous les mouvements de stock |
| `settings` | Configuration clé/valeur (persistée entre redémarrages) |

Les migrations sont appliquées **à chaud** au démarrage : si tu as une ancienne base, les nouvelles colonnes sont ajoutées automatiquement sans perte de données.

---

## API JSON

| Endpoint | Description |
|---|---|
| `GET /api/components` | Liste tous les composants (param `?search=`) |
| `GET /api/lcsc-preview?ref=C149504` | Prévisualisation LCSC sans enregistrement |
| `POST /component/<id>/adjust` | Ajustement rapide de stock (`{"delta": +/-N}`) |
| `POST /enrich/<id>` | Relance l'enrichissement LCSC pour un composant |
| `POST /projects/<id>/components/<id>/use` | Débite le stock pour un projet |
| `POST /projects/<id>/components/<id>/return` | Restitue au stock depuis un projet |

---

## Dépannage

**Les catégories et images ne se remplissent pas après l'import**  
Vérifie que Flask tourne bien avec `use_reloader=False` (déjà configuré dans `run.py`). Les logs dans le terminal doivent afficher des lignes `[LCSC] C149504 — enrichi : [...]`. Si tu vois des erreurs réseau, c'est que LCSC est inaccessible ou a changé son endpoint.

**Tester l'endpoint LCSC manuellement**  
```bash
python debug_lcsc.py
```
Affiche la réponse JSON brute pour `C149504` et vérifie quels champs sont disponibles.

**La BOM KiCad n'est pas reconnue**  
L'analyse échoue si aucune colonne LCSC n'est trouvée. Dans ce cas, un message d'erreur liste les colonnes détectées. Il faut que tes composants KiCad aient un champ `LCSC Part Number` (ou variante) renseigné. Dans KiCad, édite les propriétés de tes symboles et ajoute ce champ.

**Réinitialiser la base de données**  
Supprime simplement `instance/stock.db` et relance l'app. Les images dans `instance/images/` et `instance/project_images/` peuvent être conservées.