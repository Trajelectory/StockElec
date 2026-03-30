# ⚡ StockElectory

**Gestionnaire de stock de composants électroniques pour hobbyistes et makers.**

Conçu pour l'atelier : import depuis LCSC, Mouser et DigiKey, plan visuel de rangement, étiquettes QR, gestion de projets et BOM KiCad. Tourne entièrement en local sur ta machine.

![Python](https://img.shields.io/badge/Python-3.10+-blue?style=flat-square&logo=python)
![Flask](https://img.shields.io/badge/Flask-3.0+-lightgrey?style=flat-square&logo=flask)
![SQLite](https://img.shields.io/badge/SQLite-local-green?style=flat-square&logo=sqlite)
![License](https://img.shields.io/badge/License-MIT-purple?style=flat-square)
![Version](https://img.shields.io/badge/version-2.1-violet?style=flat-square)

---

## ✨ Fonctionnalités

### Stock
- Tableau paginé avec recherche, tri et filtres par catégorie
- Ajustement de quantité **+/−** en un clic (AJAX, sans rechargement)
- Seuil d'alerte par composant — page dédiée 🔔
- Export CSV complet (19 colonnes, encodage Excel UTF-8)
- Import CSV LCSC (format commande **et** panier)

### Multi-distributeurs
- **LCSC** — enrichissement automatique via scraping : image, catégorie, datasheet, fabricant, attributs, symbole/footprint EasyEDA
- **Mouser** — enrichissement via API officielle v1 (clé API dans les Paramètres)
- **DigiKey** — enrichissement via API officielle v4, OAuth2 Client Credentials automatique
- Prévisualisation unifiée à l'ajout : détection automatique de la source selon la référence saisie
- Import BOM KiCad multi-sources : colonnes LCSC, Mouser et DigiKey détectées automatiquement
- Double enrichissement Mouser→LCSC : si Mouser retourne peu d'attributs, complétion automatique depuis LCSC par MPN
- Badges distributeurs cliquables dans toutes les vues — lien direct vers la fiche produit

### Atelier
- **Plan de rangement** 📦 — grille visuelle interactive pour organiser ses tiroirs physiques, assignation composant → case, sauvegarde automatique
- **Étiquettes imprimables** 🏷️ — QR code généré en Python pur, format configurable (taille, couleurs, éléments affichés)
- **Emplacements** — champ `location` mis à jour automatiquement depuis le plan de rangement

### Projets
- CRUD projets avec image bannière et statut (en cours / terminé / en pause)
- Import BOM KiCad (CSV) avec rapport de disponibilité ✅/⚠️/❌
- Débiter / restituer des composants au stock depuis la fiche projet
- Bouton 🛒 par composant → redirige vers le bon distributeur

### Historique
- Chaque +/− enregistré automatiquement en base
- Page `/history` filtrable par type et par composant
- Page `/reorder` : liste des composants à commander avec quantité suggérée

### Interface
- Thème sombre violet/indigo, typographie Inter
- CSS modulaire (15 fichiers dans `modules/`)
- Page d'accueil type "Google" avec barre de recherche géante
- Serveur **Waitress** — démarrage propre sans warnings Flask

---

## 🚀 Installation

### Prérequis
- Python 3.10 ou supérieur
- pip

### Installation

```bash
# Clone le repo
git clone https://github.com/Trajelectory/StockElec.git
cd StockElec

# Installe les dépendances
pip install -r requirements.txt

# Lance l'application
python run.py
```

Ouvre ensuite [http://127.0.0.1:5000](http://127.0.0.1:5000) dans ton navigateur.

### Dépendances

```
flask>=3.0.0
requests>=2.31.0
cairosvg
waitress>=3.0.0
Pillow>=10.0.0
```

> **Note :** `cairosvg` est utilisé pour la génération d'images EasyEDA. Sur Windows, une installation de [GTK](https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer) peut être nécessaire. Si tu n'utilises pas EasyEDA, tu peux retirer cette dépendance.

### Variable d'environnement (optionnel)

```bash
# Clé secrète Flask (recommandé si exposé sur un réseau)
set SECRET_KEY=une-cle-secrete-solide   # Windows
export SECRET_KEY=une-cle-secrete-solide  # Linux/Mac
```

---

## 📁 Structure du projet

```
stockelectory/
├── run.py                  # Point d'entrée (Waitress)
├── requirements.txt
├── app/
│   ├── __init__.py         # Factory Flask
│   ├── controllers/
│   │   ├── component_controller.py   # Routes composants (~1360 lignes)
│   │   └── project_controller.py    # Routes projets
│   ├── models/
│   │   ├── database.py     # SQLite, migrations automatiques
│   │   ├── component.py    # CRUD composants
│   │   ├── project.py      # CRUD projets
│   │   ├── category.py     # Catégories LCSC + custom
│   │   ├── movement.py     # Historique mouvements
│   │   └── settings.py     # Paramètres clé/valeur
│   ├── services/
│   │   ├── lcsc_scraper.py   # Enrichissement LCSC + recherche par MPN
│   │   ├── mouser_scraper.py # Enrichissement Mouser (API v1)
│   │   ├── digikey_scraper.py # Enrichissement DigiKey (API v4 OAuth2)
│   │   ├── easyeda.py        # Symboles/footprints EasyEDA
│   │   └── qr_generator.py   # Génération QR code (Python pur)
│   ├── views/
│   │   └── component_view.py # Rendu templates composants
│   ├── templates/
│   │   ├── base.html
│   │   ├── components/     # Stock, ajout, détail, étiquettes...
│   │   └── projects/       # Projets, BOM, rapport
│   └── static/
│       ├── css/
│       │   ├── style.css           # Imports uniquement
│       │   └── modules/            # 15 fichiers CSS modulaires
│       ├── js/app.js
│       └── img/                    # Logos distributeurs (lcsc, mouser, digikey)
└── instance/               # Créé automatiquement
    ├── stock.db            # Base SQLite
    ├── images/             # Images composants
    └── easyeda_pngs/       # Symboles et footprints EasyEDA
```

---

## 🗄️ Base de données

SQLite locale dans `instance/stock.db`. Migrations automatiques au démarrage — pas besoin de setup manuel.

### Tables principales
| Table | Description |
|---|---|
| `components` | Composants (description, LCSC/Mouser/DigiKey, quantité, prix, emplacement…) |
| `projects` | Projets avec image et statut |
| `project_components` | Liaison projet ↔ composant avec quantité nécessaire |
| `categories` | Catégories LCSC importées + catégories personnalisées |
| `stock_movements` | Historique de tous les +/− |
| `settings` | Paramètres clé/valeur (config app, Rangement, étiquettes, clés API…) |

### Colonnes `components` notables
| Colonne | Description |
|---|---|
| `lcsc_part_number` | Référence LCSC (ex: `C149504`) |
| `mouser_part_number` | Référence Mouser (ex: `637-2N2222A`) |
| `digikey_part_number` | Référence DigiKey (ex: `1514-2N2222A-ND`) |
| `product_url` | URL exacte de la fiche produit distributeur |
| `attributes` | Attributs techniques en JSON (résistance, tension, package…) |
| `symbol_png` / `footprint_png` | Chemins vers les PNGs EasyEDA |

---

## 🔌 Configuration des APIs

### Mouser
1. Demande une clé sur [mouser.com/api-hub](https://www.mouser.com/api-hub/)
2. Dans les **⚙️ Paramètres** → onglet Intégrations → colle ta clé Mouser

### DigiKey
1. Crée une application sur [developer.digikey.com](https://developer.digikey.com/)
2. Récupère le `Client ID` et le `Client Secret`
3. Dans les **⚙️ Paramètres** → onglet Intégrations → renseigne les deux champs

Les credentials sont stockés dans la base SQLite locale (`settings`). Le token DigiKey est obtenu automatiquement et renouvelé avant expiration.

---

## 📦 Plan de rangement

StockElectory intègre un **plan visuel interactif** compatible avec les systèmes de rangement modulaires open-source (Gridfinity et similaires) :

1. Configure tes plateaux (ID, nom, colonnes × rangées) dans les Paramètres
2. Clique sur une case → assigne un composant
3. Le champ `Emplacement` du composant est automatiquement mis à jour (ex: `A3`, `B12`)
4. Imprime les étiquettes QR et colle-les sur tes tiroirs

---

## 🏷️ Étiquettes

Génère et imprime des étiquettes pour tes tiroirs depuis la page Stock :
- Sélectionne des composants (cases à cocher)
- Clique sur **🏷️ Étiquettes**
- Configure format, couleurs, éléments affichés dans `/label-settings`
- Imprime depuis le navigateur (Ctrl+P)

Chaque étiquette contient : image, description, références LCSC/fabricant, badges (package, RoHS, quantité, emplacement), QR code.

---

## ⚙️ Configuration

Depuis la page **⚙️ Paramètres** :

| Onglet | Options |
|---|---|
| Général | Nom de l'application, URL de base QR, seuil alerte global |
| Sauvegarde | ZIP complet (base + images), export CSV du stock |
| Intégrations | Clé Mouser, Client ID/Secret DigiKey |
| Enrichissement | Enrichissement LCSC en masse, nettoyage images orphelines, réconciliation EasyEDA |
| Étiquettes | Format, couleurs, tailles de police, éléments affichés |
| Danger | Vider l'historique, reset complet de la base (confirmation requise) |

---

## 🤝 Contribution

Les PR sont les bienvenues ! Pour les bugs, ouvre une issue avec :
- Version Python et OS
- Message d'erreur complet (log Waitress)
- Étapes pour reproduire

---

## 📄 Licence

MIT — fais-en ce que tu veux, un crédit sympa toujours apprécié ⚡
