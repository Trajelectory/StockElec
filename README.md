# ⚡ StockEleK

**Gestionnaire de stock de composants électroniques pour makers et hobbyistes.**

Conçu pour l'atelier : catalogue tes composants, suis tes projets, localise physiquement chaque pièce avec des LEDs WS2812B pilotées par un ESP32, génère tes bibliothèques KiCad. Tourne entièrement en local, sans cloud, sans abonnement.

![Python](https://img.shields.io/badge/Python-3.10+-blue?style=flat-square&logo=python)
![Flask](https://img.shields.io/badge/Flask-3.1.3-lightgrey?style=flat-square&logo=flask)
![SQLite](https://img.shields.io/badge/SQLite-WAL-green?style=flat-square&logo=sqlite)
![ESP32](https://img.shields.io/badge/ESP32-firmware_v6.1-orange?style=flat-square&logo=espressif)
![License](https://img.shields.io/badge/License-MIT-purple?style=flat-square)
![Version](https://img.shields.io/badge/version-3.1-violet?style=flat-square)

---

## ✨ Fonctionnalités

### 📦 Gestion du stock
- Tableau paginé avec recherche full-text, tri multi-colonnes et filtres par catégorie
- Ajustement de quantité **+/−** en un clic (AJAX, sans rechargement)
- Seuil d'alerte configurable par composant — page dédiée 🔔
- Page `/reorder` : composants en rupture avec liens directs LCSC/Mouser/DigiKey
- Export CSV complet (19 colonnes, encodage UTF-8 Excel)
- Import CSV : LCSC (commande + panier), BOM KiCad, Mouser, DigiKey
- **11 index SQLite** pour des performances fluides sur gros catalogues
- Mode WAL SQLite : lectures concurrentes sans blocage sous Waitress multi-thread

### 🌐 Enrichissement multi-distributeurs
- **LCSC** — automatique sans clé : image, catégorie, datasheet, symbole/footprint EasyEDA, attributs techniques
- **Mouser** — via API officielle v1 (clé API dans les Paramètres)
- **DigiKey** — via API officielle v4, OAuth2 Client Credentials automatique
- Enrichissement en masse depuis les Paramètres
- Double enrichissement Mouser → LCSC si les attributs sont incomplets
- Badges distributeurs cliquables dans toutes les vues

### 📁 Projets maker
- Vue **Kanban** avec 8 statuts : Idée → Conception → Commandé → En production → Assemblage → Debug → Terminé → Archivé
- Drag & drop entre colonnes, sauvegarde AJAX instantanée
- **BOM complète** : import KiCad CSV, vérification de disponibilité en temps réel, préparation de kit en un clic
- **Notes Markdown** avec parser JS maison : H1-H4, gras/italique/barré/souligné/surligné, listes, checkboxes, tableaux, blocs de code, citations, couleurs custom `{red}texte{/red}`, images (upload / drag & drop / coller)
- **Checklist** avec templates par discipline (PCB, Code, Impression 3D)
- **Liens** avec icônes auto selon le domaine (GitHub, KiCad, JLCPCB, Thingiverse…)
- Journal des mouvements de stock par projet

### 💡 Localisation physique par LEDs (ESP32)
- Firmware **v6.1** pour ESP32-S3 avec deux rubans WS2812B
- **Ruban 1** : emplacement exact du composant (LED de position)
- **Ruban 2** : tiroir (A-Z) avec **breathing doux** pendant l'allumage
- **Afficheur HT16K33** 14-segments : affiche la case (ex: `A 16`), veille après 33s
- **Couleurs automatiques par catégorie** : résistances orange, condensateurs bleu, ICs violet, diodes rouge… (18 familles, 100% personnalisables)
- File d'attente de 4 commandes
- **Page web embarquée** sur `http://[IP_ESP32]/` : statut live, contrôle manuel, paramètres
- Reconnexion WiFi automatique, OTA

### ⬡ Intégration KiCad
- Génération de bibliothèques `.kicad_sym` / `.kicad_mod` / `.step` depuis les données LCSC (via JLC2KiCadLib)
- **Bouton "⚙ Générer KiCad"** directement sur la fiche composant — génère 1 seul composant sans relancer le job entier
- **Fusion intelligente** par catégorie avec option `skip_existing` (cochée par défaut) : ajoute uniquement les nouveaux symboles sans écraser les modifications manuelles KiCad
- Enregistrement automatique dans `sym-lib-table` et `fp-lib-table` de KiCad
- Téléchargement ZIP complet de toutes les librairies

### 🗃️ Rangement GridFinity
- Carte visuelle interactive par plateaux (colonnes × rangées configurables)
- Survol → infobulle avec image, référence, quantité, package
- Clic droit → menu contextuel : assigner, allumer LED, vider la case

### 🏷️ Étiquettes imprimables
- QR code généré en Python pur (zéro dépendance externe)
- Format, couleurs, taille de police, 11 éléments configurables
- Multi-sélection → impression en lot
- Aperçu temps réel dans les Paramètres

### 🌍 Interface bilingue FR / EN
- 765 clés de traduction dans `locales/fr.json` et `locales/en.json`
- Sélecteur de langue dans les Paramètres
- Tous les templates et messages Flask traduits

### 🎨 Design & UX
- Thème sombre **et clair** avec toggle
- Violet/indigo `#7c6cff`, typographie Inter
- CSS modulaire (20 fichiers dans `modules/`)
- Documentation CSS interactive sur `/docs`
- Manuel d'utilisation complet sur `/docs/manuel`
- Responsive mobile — navbar hamburger

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

La base de données SQLite et le dossier `images/` sont créés automatiquement dans `instance/` au premier démarrage.

### Dépendances Python

```
flask==3.1.3
waitress==3.0.1
requests==2.33.0
Pillow==12.1.1
```

### Variable d'environnement (optionnel)

```bash
# Clé secrète Flask (générée et persistée automatiquement dans instance/secret_key)
# Peut être surchargée via variable d'environnement :
set SECRET_KEY=une-cle-secrete-solide   # Windows
export SECRET_KEY=une-cle-secrete-solide  # Linux/Mac
```

---

## 📁 Structure du projet

```
StockElec/
├── run.py                          # Point d'entrée (Waitress)
├── requirements.txt                # Versions fixées avec ==
├── .gitignore
├── app/
│   ├── __init__.py                 # Factory Flask + i18n + cache TTL
│   ├── locales/
│   │   ├── fr.json                 # 765 clés — Français
│   │   └── en.json                 # 765 clés — English
│   ├── controllers/
│   │   ├── routes_stock.py
│   │   ├── routes_settings.py
│   │   ├── routes_led.py           # API LED + couleurs par catégorie
│   │   ├── routes_enrichment.py
│   │   ├── routes_import_export.py
│   │   ├── routes_labels.py
│   │   ├── routes_rangement.py
│   │   ├── routes_kicad.py         # /generate, /generate-one, /merge (skip_existing)
│   │   ├── routes_misc.py
│   │   └── utils.py                # require_esp32_token (navigateur + ESP32)
│   ├── models/
│   │   ├── database.py             # SQLite WAL, 11 index, migrations _col_exists()
│   │   ├── component.py            # Rollbacks complets, delete() nettoie les images
│   │   ├── project.py
│   │   ├── settings.py
│   │   ├── movement.py
│   │   └── category.py
│   ├── services/
│   │   ├── lcsc_scraper.py
│   │   ├── mouser_scraper.py
│   │   ├── digikey_scraper.py
│   │   ├── kicad_jlc.py            # Fusion intelligente skip_existing
│   │   ├── easyeda.py
│   │   └── qr_generator.py
│   ├── views/
│   │   └── component_view.py
│   ├── templates/
│   │   ├── base.html
│   │   ├── components/             # detail.html avec bouton Générer KiCad
│   │   ├── projects/
│   │   ├── errors/                 # 404.html, 500.html
│   │   └── docs/
│   └── static/
│       ├── css/modules/            # 20 fichiers CSS modulaires
│       ├── js/                     # JS par page
│       └── img/
└── instance/                       # Créé automatiquement — non versionné
    ├── stock.db                    # ← Sauvegarde ce fichier !
    ├── secret_key                  # ← Clé Flask persistée
    ├── images/
    ├── project_images/
    ├── easyeda_pngs/
    └── kicad/                      # Fichiers KiCad générés
```

---

## 💾 Sauvegarde

Toutes tes données se trouvent dans `instance/` (ignoré par Git) :

```
instance/stock.db        ← base de données complète
instance/images/         ← images des composants
instance/project_images/ ← images des projets
```

Un bouton **Télécharger la sauvegarde** dans **Paramètres → Backup** génère un ZIP horodaté. Copie-le régulièrement sur un disque externe ou un cloud.

---

## 🗄️ Base de données

SQLite locale dans `instance/stock.db`. Mode WAL activé, migrations et index créés automatiquement au démarrage.

| Table | Description |
|---|---|
| `components` | Composants (description, refs, quantité, prix, emplacement, catégorie…) |
| `projects` | Projets avec image, statut, notes, checklist, liens |
| `project_components` | Liaison projet ↔ composant avec quantité |
| `stock_movements` | Historique complet de tous les mouvements |
| `settings` | Paramètres clé/valeur (config, étiquettes, clés API, couleurs LED…) |
| `categories` | Arborescence des catégories LCSC et personnalisées |

---

## 🔌 Configuration des APIs

### Mouser
1. Demande une clé gratuite sur [mouser.com/api-hub](https://www.mouser.com/api-hub/)
2. **⚙️ Paramètres** → Integrations → Mouser

### DigiKey
1. Crée une application sur [developer.digikey.com](https://developer.digikey.com/)
2. Récupère `Client ID` et `Client Secret`
3. **⚙️ Paramètres** → Integrations → DigiKey

Le token OAuth2 DigiKey est obtenu et renouvelé automatiquement.

---

## 💡 Firmware ESP32

Le firmware se trouve dans `StockEleK_P4/` (ESP32-P4 GUITION) ou `StockEleK_S3/` (ESP32-S3).

### API REST ESP32

| Méthode | Route | Description |
|---|---|---|
| `POST` | `/leds` | Allumer des LEDs (indices, couleur, durée, tiroir, case) |
| `POST` | `/led` | Variante P4 avec affichage écran |
| `POST` | `/off` | Tout éteindre |
| `GET` | `/status` | État complet (LEDs, afficheur, RSSI, heap, uptime) |
| `GET` | `/ping` | Ping sans token — retourne `{"display": true/false}` pour détecter P4 vs S3 |
| `POST` | `/test` | Chenillard de test |
| `POST` | `/reboot` | Redémarrer l'ESP32 |

Toutes les routes (sauf `/ping`) nécessitent le header `X-Token: [AUTH_TOKEN]`.

---

## 🤝 Contribution

Les PR sont les bienvenues ! Pour les bugs, ouvre une issue avec :
- Version Python et OS
- Message d'erreur complet (log Waitress ou Serial Monitor Arduino)
- Étapes pour reproduire

---

## 📄 Licence

MIT — fais-en ce que tu veux, un crédit sympa toujours apprécié ⚡
