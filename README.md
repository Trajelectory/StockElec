# ⚡ StockEleK

**Gestionnaire de stock de composants électroniques pour makers et hobbyistes.**

Conçu pour l'atelier : catalogue tes composants, suis tes projets, localise physiquement chaque pièce avec des LEDs WS2812B pilotées par un ESP32, génère tes bibliothèques KiCad. Tourne entièrement en local, sans cloud, sans abonnement.

![Python](https://img.shields.io/badge/Python-3.10+-blue?style=flat-square&logo=python)
![Flask](https://img.shields.io/badge/Flask-3.0+-lightgrey?style=flat-square&logo=flask)
![SQLite](https://img.shields.io/badge/SQLite-local-green?style=flat-square&logo=sqlite)
![ESP32](https://img.shields.io/badge/ESP32-firmware_v6.1-orange?style=flat-square&logo=espressif)
![License](https://img.shields.io/badge/License-MIT-purple?style=flat-square)
![Version](https://img.shields.io/badge/version-3.0-violet?style=flat-square)

---

## ✨ Fonctionnalités

### 📦 Gestion du stock
- Tableau paginé avec recherche full-text, tri multi-colonnes et filtres par catégorie
- Ajustement de quantité **+/−** en un clic (AJAX, sans rechargement)
- Seuil d'alerte configurable par composant — page dédiée 🔔
- Page `/reorder` : composants en rupture avec liens directs LCSC/Mouser/DigiKey
- Export CSV complet (19 colonnes, encodage UTF-8 Excel)
- Import CSV : LCSC (commande + panier), BOM KiCad, Mouser, DigiKey
- **6 index SQLite** pour des performances fluides sur gros catalogues

### 🌐 Enrichissement multi-distributeurs
- **LCSC** — automatique sans clé : image, catégorie, datasheet, symbole/footprint EasyEDA, attributs techniques
- **Mouser** — via API officielle v1 (clé API dans les Paramètres)
- **DigiKey** — via API officielle v4, OAuth2 Client Credentials automatique
- Enrichissement en masse depuis les Paramètres (tous les composants sans image/catégorie en un clic)
- Double enrichissement Mouser → LCSC si les attributs sont incomplets
- Badges distributeurs cliquables dans toutes les vues

### 📁 Projets maker
- Vue **Kanban** avec 8 statuts : Idée → Conception → Commandé → En production → Assemblage → Debug → Terminé → Archivé
- Drag & drop entre colonnes, sauvegarde AJAX instantanée
- **Sélecteur de statut rapide** depuis la fiche projet (dropdown dans le hero)
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
- **Couleurs automatiques par catégorie** : résistances orange, condensateurs bleu, ICs violet, diodes rouge… (18 familles, 100% personnalisables dans les Paramètres)
- File d'attente de 4 commandes
- **Page web embarquée** sur `http://[IP_ESP32]/` : statut live, contrôle manuel, paramètres runtime (luminosité, durée, couleurs) sauvegardés en flash
- Reconnexion WiFi automatique, OTA (mise à jour sans câble)
- **`POST /reboot`** : redémarrer l'ESP32 depuis la page web

### 🗃️ Rangement GridFinity
- Carte visuelle interactive par plateaux (colonnes × rangées configurables)
- Survol → infobulle avec image, référence, quantité, package
- Clic droit → menu contextuel : assigner, allumer LED, vider la case
- Drag & drop pour déplacer les composants entre cases

### 🏷️ Étiquettes imprimables
- QR code généré en Python pur (zéro dépendance externe)
- Format, couleurs, taille de police, 11 éléments configurables
- Multi-sélection → impression en lot
- Aperçu temps réel dans les Paramètres
- URL encodée dans le QR = accès direct à la fiche depuis un smartphone

### ⬡ Intégration KiCad
- Génération de bibliothèques `.kicad_sym` depuis les données LCSC (via easyeda2kicad)
- Une bibliothèque par catégorie, téléchargeable en ZIP
- Symbole, empreinte et modèle 3D par composant

### 🌍 Interface bilingue FR / EN
- 751 clés de traduction dans `locales/fr.json` et `locales/en.json`
- Sélecteur de langue dans les Paramètres
- Tous les templates et messages Flask traduits

### 🎨 Design & UX
- Thème sombre **et clair** avec toggle (logo adaptatif)
- Violet/indigo `#7c6cff`, typographie Inter
- CSS modulaire (20 fichiers dans `modules/`)
- Documentation CSS interactive sur `/docs` (extraite dynamiquement des fichiers CSS)
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
git clone https://github.com/ton-user/stockelek.git
cd stockelek

# Installe les dépendances
pip install -r requirements.txt

# Lance l'application
python run.py
```

Ouvre ensuite [http://127.0.0.1:5000](http://127.0.0.1:5000) dans ton navigateur.

La base de données SQLite et le dossier `images/` sont créés automatiquement dans `instance/` au premier démarrage.

### Dépendances Python

```
flask>=3.0.0
requests>=2.31.0
waitress>=3.0.0
Pillow>=10.0.0
qrcode>=7.4.0
```

### Variable d'environnement (optionnel)

```bash
# Clé secrète Flask (recommandé si exposé sur un réseau)
set SECRET_KEY=une-cle-secrete-solide   # Windows
export SECRET_KEY=une-cle-secrete-solide  # Linux/Mac
```

---

## 📁 Structure du projet

```
stockelek/
├── run.py                          # Point d'entrée (Waitress)
├── requirements.txt
├── gridfinity_leds_Arduino/
│   └── gridfinity_leds_Arduino.ino # Firmware ESP32 v6.1
├── app/
│   ├── __init__.py                 # Factory Flask + i18n
│   ├── locales/
│   │   ├── fr.json                 # 751 clés — Français
│   │   └── en.json                 # 751 clés — English
│   ├── controllers/
│   │   ├── routes_stock.py
│   │   ├── routes_settings.py
│   │   ├── routes_led.py           # API LED + couleurs par catégorie
│   │   ├── routes_enrichment.py
│   │   ├── routes_import_export.py
│   │   ├── routes_labels.py
│   │   ├── routes_rangement.py
│   │   ├── routes_kicad.py
│   │   └── routes_misc.py          # API REST, /docs
│   ├── models/
│   │   ├── database.py             # SQLite, migrations + index auto
│   │   ├── component.py
│   │   ├── project.py
│   │   ├── settings.py
│   │   └── ...
│   ├── services/
│   │   ├── lcsc_scraper.py
│   │   ├── mouser_scraper.py
│   │   ├── digikey_scraper.py
│   │   ├── kicad_export.py
│   │   ├── easyeda.py
│   │   └── qr_generator.py
│   ├── views/
│   │   └── component_view.py
│   ├── templates/
│   │   ├── base.html
│   │   ├── components/
│   │   ├── projects/
│   │   └── docs/                   # /docs et /docs/manuel
│   └── static/
│       ├── css/modules/            # 20 fichiers CSS modulaires
│       ├── js/                     # JS par page
│       └── img/
└── instance/                       # Créé automatiquement
    ├── stock.db                    # ← Sauvegarde ce fichier !
    ├── images/                     # ← Et ce dossier !
    ├── project_images/
    └── easyeda_pngs/
```

---

## 💾 Sauvegarde

Toutes tes données se trouvent dans **deux emplacements** :

```
instance/stock.db        ← base de données complète
instance/images/         ← images des composants
instance/project_images/ ← images des projets
```

Un bouton **Télécharger la sauvegarde** dans **Paramètres → Backup** génère un ZIP horodaté contenant les trois. Copie-le régulièrement sur un disque externe ou un cloud.

---

## 🗄️ Base de données

SQLite locale dans `instance/stock.db`. Migrations et index créés automatiquement au démarrage.

| Table | Description |
|---|---|
| `components` | Composants (description, refs, quantité, prix, emplacement, catégorie…) |
| `projects` | Projets avec image, statut, notes, checklist, liens |
| `project_components` | Liaison projet ↔ composant avec quantité |
| `stock_movements` | Historique complet de tous les mouvements |
| `settings` | Paramètres clé/valeur (config, étiquettes, clés API, couleurs LED…) |

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

Le firmware se trouve dans `gridfinity_leds_Arduino/`.

### Bibliothèques Arduino requises
- FastLED
- ArduinoJson
- WebSockets (Markus Sattler)
- Adafruit LED Backpack Library
- Adafruit GFX Library
- Preferences (incluse dans ESP32 Arduino core)

### Câblage HT16K33 (ESP32-S3 Wroom-1)
| HT16K33 | ESP32-S3 |
|---|---|
| SDA | GPIO 8 |
| SCL | GPIO 9 |
| VCC | 3.3V |
| GND | GND |

### API REST ESP32

| Méthode | Route | Description |
|---|---|---|
| `POST` | `/leds` | Allumer des LEDs (indices, couleur, durée, tiroir, case) |
| `POST` | `/off` | Tout éteindre |
| `GET` | `/status` | État complet (LEDs, afficheur, RSSI, heap, uptime) |
| `GET` | `/ping` | Ping sans token |
| `POST` | `/test` | Chenillard de test |
| `GET/POST` | `/config` | Lire/modifier la config runtime (luminosité, durée, couleurs) |
| `POST` | `/reboot` | Redémarrer l'ESP32 |

Toutes les routes (sauf `/ping`) nécessitent le header `X-Token: [AUTH_TOKEN]`.

La page web embarquée est accessible directement sur `http://[IP_ESP32]/`.

---

## 🤝 Contribution

Les PR sont les bienvenues ! Pour les bugs, ouvre une issue avec :
- Version Python et OS
- Message d'erreur complet (log Waitress ou Serial Monitor Arduino)
- Étapes pour reproduire

---

## 📄 Licence

MIT — fais-en ce que tu veux, un crédit sympa toujours apprécié ⚡
