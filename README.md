# ⚡ StockEleK

**Gestionnaire de stock de composants électroniques pour hobbyistes et makers.**

Conçu pour l'atelier : import depuis LCSC, Mouser et DigiKey, plan visuel de rangement interactif, étiquettes QR, gestion de projets et BOM KiCad. Interface bilingue FR/EN. Tourne entièrement en local sur ta machine.

![Python](https://img.shields.io/badge/Python-3.10+-blue?style=flat-square&logo=python)
![Flask](https://img.shields.io/badge/Flask-3.0+-lightgrey?style=flat-square&logo=flask)
![SQLite](https://img.shields.io/badge/SQLite-local-green?style=flat-square&logo=sqlite)
![License](https://img.shields.io/badge/License-MIT-purple?style=flat-square)
![Version](https://img.shields.io/badge/version-2.2-violet?style=flat-square)

---

## ✨ Fonctionnalités

### 📦 Stock
- Tableau paginé avec recherche full-text, tri multi-colonnes et filtres par catégorie
- Ajustement de quantité **+/−** en un clic (AJAX, sans rechargement)
- Seuil d'alerte par composant — page dédiée 🔔
- Export CSV complet (19 colonnes, encodage Excel UTF-8)
- Import CSV : LCSC (commande + panier), BOM KiCad, Mouser, DigiKey

### 🌐 Multi-distributeurs
- **LCSC** — enrichissement automatique : image, catégorie, datasheet, fabricant, attributs, symbole/footprint EasyEDA
- **Mouser** — enrichissement via API officielle v1 (clé API dans les Paramètres)
- **DigiKey** — enrichissement via API officielle v4, OAuth2 Client Credentials automatique
- Prévisualisation unifiée à l'ajout : détection automatique de la source selon la référence
- Double enrichissement Mouser → LCSC si peu d'attributs retournés
- Badges distributeurs cliquables dans toutes les vues

### 🗃️ Plan de rangement
- Grille visuelle interactive par plateaux (colonnes × rangées configurables)
- **Survol** → infobulle avec image, référence, quantité, package, fabricant
- **Clic droit** → menu contextuel :
  - Assigner un composant (popup de recherche + sélection taille de boîte)
  - Allumer la LED *(à venir — intégration ESP32)*
  - Vider la case
- Champ `Emplacement` mis à jour automatiquement (ex : `A3`, `B12`)
- Slider zoom, stats d'occupation par plateau, bouton "Vider le plateau"
- Navigation par onglets, sauvegarde automatique

### 🏷️ Étiquettes imprimables
- QR code généré en Python pur, zéro dépendance externe
- Format, couleurs, tailles de police, 11 éléments toggles configurables
- Multi-sélection dans le tableau → impression en lot
- Aperçu temps réel dans les paramètres

### 🗂️ Projets
- CRUD projets avec image bannière et statut (en cours / terminé / en pause)
- Import BOM KiCad (CSV) avec rapport de disponibilité ✅ / ⚠️ / ❌
- Débiter / restituer des composants au stock depuis la fiche projet
- Bouton 🛒 par composant → redirige vers le bon distributeur

### 📋 Historique & Réapprovisionnement
- Chaque mouvement +/− enregistré automatiquement
- Page `/history` filtrable par type et par composant
- Page `/reorder` : composants en rupture ou sous le seuil, quantité suggérée, liens distributeurs

### 🌍 Interface bilingue FR / EN
- Traduction complète : templates, messages flash, erreurs API
- Sélecteur de langue dans les Paramètres → Général
- Fichiers `locales/fr.json` et `locales/en.json` (558 clés) — facilement extensible

### 🎨 Interface
- Thème sombre **et clair** avec toggle (logo adaptatif par thème)
- Design violet/indigo, typographie Inter
- CSS modulaire (16 fichiers dans `modules/`)
- Responsive mobile — navbar hamburger
- Page d'accueil type "Google" avec barre de recherche

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

### Dépendances

```
flask>=3.0.0
requests>=2.31.0
waitress>=3.0.0
Pillow>=10.0.0
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
├── run.py                  # Point d'entrée (Waitress)
├── requirements.txt
├── app/
│   ├── __init__.py         # Factory Flask + système i18n
│   ├── locales/
│   │   ├── fr.json         # 558 clés — Français
│   │   └── en.json         # 558 clés — English
│   ├── controllers/
│   │   ├── component_controller.py
│   │   └── project_controller.py
│   ├── models/
│   │   ├── database.py     # SQLite, migrations automatiques
│   │   ├── component.py
│   │   ├── project.py
│   │   ├── category.py
│   │   ├── movement.py
│   │   └── settings.py
│   ├── services/
│   │   ├── lcsc_scraper.py
│   │   ├── mouser_scraper.py
│   │   ├── digikey_scraper.py
│   │   ├── easyeda.py
│   │   └── qr_generator.py
│   ├── templates/
│   │   ├── base.html
│   │   ├── components/
│   │   ├── projects/
│   │   └── partials/
│   └── static/
│       ├── css/modules/    # 16 fichiers CSS modulaires
│       ├── js/app.js
│       └── img/            # Logo.png (sombre) + Logo_c.png (clair)
└── instance/               # Créé automatiquement
    ├── stock.db
    ├── images/
    └── easyeda_pngs/
```

---

## 🗄️ Base de données

SQLite locale dans `instance/stock.db`. Migrations automatiques au démarrage — pas de setup manuel.

| Table | Description |
|---|---|
| `components` | Composants (description, refs distributeurs, quantité, prix, emplacement…) |
| `projects` | Projets avec image et statut |
| `project_components` | Liaison projet ↔ composant |
| `categories` | Catégories LCSC + personnalisées |
| `stock_movements` | Historique de tous les mouvements |
| `settings` | Paramètres clé/valeur (config, étiquettes, clés API, langue…) |

---

## 🔌 Configuration des APIs

### Mouser
1. Demande une clé sur [mouser.com/api-hub](https://www.mouser.com/api-hub/)
2. **⚙️ Paramètres** → Intégrations → colle ta clé Mouser

### DigiKey
1. Crée une application sur [developer.digikey.com](https://developer.digikey.com/)
2. Récupère `Client ID` et `Client Secret`
3. **⚙️ Paramètres** → Intégrations → renseigne les deux champs

Le token OAuth2 DigiKey est obtenu et renouvelé automatiquement.

---

## 🗃️ Plan de rangement — utilisation

1. **⚙️ Gérer les plateaux** — configure ID, nom et dimensions de chaque plateau
2. **Clic droit sur une case** → *Assigner un composant* → recherche dans le stock
3. Choisis la taille de boîte (1×1, 2×1, 2×2…) pour les systèmes modulaires (Gridfinity…)
4. Le champ `Emplacement` du composant est mis à jour automatiquement
5. Imprime les étiquettes QR et colle-les sur tes tiroirs

---

## 🌍 Ajouter une langue

1. Copie `app/locales/fr.json` en `app/locales/xx.json`
2. Traduis les valeurs (ne modifie pas les clés)
3. Ajoute `<option value="xx">🏳️ Langue</option>` dans `settings.html`
4. C'est tout

---

## ⚙️ Paramètres

| Onglet | Options |
|---|---|
| Général | Nom de l'app, URL de base QR, seuil alerte global, **langue** |
| Sauvegarde | ZIP complet (base + images), export CSV du stock |
| Intégrations | Clé Mouser, Client ID/Secret DigiKey, test de connexion |
| Enrichissement LCSC | Enrichissement en masse, EasyEDA, réconciliation, nettoyage images |
| Étiquettes | Format, couleurs, tailles de police, 11 toggles, aperçu temps réel |
| Base de données | Stats, historique, nettoyage, reset complet |

---

## 🤝 Contribution

Les PR sont les bienvenues ! Pour les bugs, ouvre une issue avec :
- Version Python et OS
- Message d'erreur complet (log Waitress)
- Étapes pour reproduire

---

## 📄 Licence

MIT — fais-en ce que tu veux, un crédit sympa toujours apprécié ⚡
