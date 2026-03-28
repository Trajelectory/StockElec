# ⚡ StockElectory
<img width="1329" height="714" alt="image" src="https://github.com/user-attachments/assets/bd336ca8-5f8f-4ad2-98cb-fd43eb58fcdb" />

**Gestionnaire de stock de composants électroniques pour hobbyistes et makers.**

Conçu pour l'atelier : import depuis LCSC, plan visuel Gridfinity, étiquettes QR, gestion de projets et BOM KiCad. Tourne entièrement en local sur ta machine.

![Python](https://img.shields.io/badge/Python-3.10+-blue?style=flat-square&logo=python)
![Flask](https://img.shields.io/badge/Flask-3.0+-lightgrey?style=flat-square&logo=flask)
![SQLite](https://img.shields.io/badge/SQLite-local-green?style=flat-square&logo=sqlite)
![License](https://img.shields.io/badge/License-MIT-purple?style=flat-square)

---

## ✨ Fonctionnalités

### Stock
- Tableau paginé avec recherche, tri et filtres par catégorie
- Ajustement de quantité **+/−** en un clic (AJAX, sans rechargement)
- Seuil d'alerte par composant — page dédiée 🔔
- Export CSV complet en un clic
- Import CSV LCSC (format commande **et** panier)
- Enrichissement automatique depuis LCSC : image, catégorie, datasheet, fabricant

### Atelier
- **Plan Gridfinity** 📦 — grille visuelle interactive pour organiser ses tiroirs physiques, assignation composant → case, sauvegarde automatique
- **Étiquettes imprimables** 🏷️ — QR code généré en Python pur, format configurable (taille, couleurs, éléments affichés)
- **Emplacements** — champ `location` mis à jour automatiquement depuis le plan Gridfinity

### Projets
- CRUD projets avec image bannière et statut (en cours / terminé / en pause)
- Import BOM KiCad (CSV) avec rapport de disponibilité ✅/⚠️/❌
- Débiter / restituer des composants au stock depuis la fiche projet

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
git clone https://github.com/ton-user/stockelectory.git
cd stockelectory

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
```

> **Note :** `cairosvg` est utilisé pour la génération d'images EasyEDA. Sur Windows, une installation de [GTK](https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer) peut être nécessaire. Si tu n'utilises pas EasyEDA, tu peux retirer cette dépendance.

---

## 📁 Structure du projet

```
stockelectory/
├── run.py                  # Point d'entrée (Waitress)
├── requirements.txt
├── app/
│   ├── __init__.py         # Factory Flask
│   ├── controllers/
│   │   ├── component_controller.py   # Routes composants
│   │   └── project_controller.py    # Routes projets
│   ├── models/
│   │   ├── database.py     # SQLite, migrations
│   │   ├── component.py    # CRUD composants
│   │   ├── project.py      # CRUD projets
│   │   ├── category.py     # Catégories LCSC + custom
│   │   ├── movement.py     # Historique mouvements
│   │   └── settings.py     # Paramètres clé/valeur
│   ├── services/
│   │   ├── lcsc_scraper.py # Enrichissement LCSC
│   │   ├── easyeda.py      # Symboles/footprints EasyEDA
│   │   └── qr_generator.py # Génération QR code (Python pur)
│   ├── templates/
│   │   ├── base.html
│   │   ├── components/     # Stock, ajout, détail, étiquettes...
│   │   └── projects/       # Projets, BOM, rapport
│   └── static/
│       ├── css/
│       │   ├── style.css           # Imports uniquement
│       │   └── modules/            # 15 fichiers CSS modulaires
│       └── js/app.js
└── instance/               # Créé automatiquement
    ├── stock.db            # Base SQLite
    ├── images/             # Images composants (LCSC + upload)
    └── easyeda_pngs/       # Symboles et footprints EasyEDA
```

---

## 🗄️ Base de données

SQLite locale dans `instance/stock.db`. Migrations automatiques au démarrage — pas besoin de setup manuel.

### Tables principales
| Table | Description |
|---|---|
| `components` | Composants (description, LCSC, quantité, prix, emplacement…) |
| `projects` | Projets avec image et statut |
| `project_components` | Liaison projet ↔ composant avec quantité nécessaire |
| `categories` | Catégories LCSC importées + catégories personnalisées |
| `stock_movements` | Historique de tous les +/− |
| `settings` | Paramètres clé/valeur (config app, Gridfinity, étiquettes…) |

---

## 📦 Plan Gridfinity

[Gridfinity](https://www.printables.com/model/274917) est un système de rangement modulaire open-source pour l'impression 3D, très populaire dans la communauté maker.

StockElectory intègre un **plan visuel interactif** :

1. Configure tes plateaux (ID, nom, colonnes × rangées)
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
- Nom de l'application
- Adresse de base pour les QR codes
- Seuil d'alerte stock global
- Sauvegarde ZIP de la base et des images
- Vider l'historique des mouvements
- Téléchargement en masse des symboles EasyEDA

---

## 🤝 Contribution

Les PR sont les bienvenues ! Pour les bugs, ouvre une issue avec :
- Version Python et OS
- Message d'erreur complet
- Étapes pour reproduire

---

## 📄 Licence

MIT — fais-en ce que tu veux, un crédit sympa toujours apprécié ⚡
