# StockElec 📦⚡

Application de gestion de stock de composants électroniques pour makers et hobbyistes.
Développée avec **Flask + SQLite**, architecture **MVC**, thème sombre.

<p align="center">
    <a href="#"> <img src="https://placehold.co/300x200" width="300" height="200"> </a>
    <a href="#"> <img src="https://placehold.co/300x200" width="300" height="200"> </a>
    <a href="#"> <img src="https://placehold.co/300x200" width="300" height="200"> </a>
    <a href="#"> <img src="https://placehold.co/300x200" width="300" height="200"> </a>
    <a href="#"> <img src="https://placehold.co/300x200" width="300" height="200"> </a>
    <a href="#"> <img src="https://placehold.co/300x200" width="300" height="200"> </a>
    <a href="#"> <img src="https://placehold.co/300x200" width="300" height="200"> </a>
    <a href="#"> <img src="https://placehold.co/300x200" width="300" height="200"> </a>
    <a href="#"> <img src="https://placehold.co/300x200" width="300" height="200"> </a>
</p>
Installation
bash# 1. Environnement virtuel
python -m venv venv
source venv/bin/activate        # Linux / macOS
venv\Scripts\activate           # Windows

# 2. Dépendances
pip install -r requirements.txt

# 3. Lancer
python run.py
Accessible sur http://127.0.0.1:5000

use_reloader=False est intentionnel — le reloader de Flask tuerait les threads d'enrichissement LCSC en arrière-plan.


Fonctionnalités
📦 Stock

Tableau paginé (5/25/50/100) avec miniatures, recherche, filtres catégorie, tri
Barre de stats compacte (références, pièces, valeur totale, fabricants)
Badges RoHS/DS inline, seuil d'alerte discret ⚡
Cases à cocher multi-sélection + barre flottante (étiquettes)
Ajustement rapide +/− AJAX

➕ Ajout en série

Layout deux colonnes : Import rapide LCSC + Identification + Organisation à gauche, stock/prix sticky à droite
Import rapide LCSC : ref → prévisualisation → pré-remplissage en un clic
Upload d'image manuelle : JPG, PNG, WEBP avec prévisualisation instantanée — utile pour les composants hors LCSC
Calcul automatique prix total (quantité × unitaire)
Mode série : après validation, reste sur la page avec bandeau vert de confirmation

✏️ Édition

Même layout que l'ajout, données pré-remplies
Upload image manuelle avec prévisualisation de l'image existante
Calcul automatique prix total

📥 Import CSV LCSC
Deux formats détectés automatiquement :
FormatColonnes clésExport commandeLCSC Part Number, Manufacture Part Number, Ext.Price(€)Export panier (export_cart_*.csv)LCSC#, MPN, Extended Price(€)

Drag & drop ou sélection fichier
Déduplication automatique par référence LCSC
Enrichissement en arrière-plan après import

🔍 Enrichissement LCSC automatique
Scrape wmsc.lcsc.com pour récupérer catégorie, image et datasheet.
Thread daemon, ~0.6s entre requêtes. Bouton 📷 pour relancer manuellement.
🖼️ Symbole & Footprint EasyEDA
Sur la fiche composant : grande photo (180×180) + 2 vignettes (symbole / footprint) côte à côte.
Chargement à la demande, cache dans instance/easyeda_pngs/, lightbox au clic.
🗂️ Catégories

Catégories LCSC créées automatiquement à l'enrichissement
Catégories personnalisées : création/suppression via ⚙️ Paramètres → 🗂️ Gérer les catégories
Groupes et sous-catégories libres (ex: Hardware / Vis M3, Modules / Arduino…)
Apparaissent immédiatement dans les selects Ajouter/Éditer

🗂️ Projets

CRUD avec image bannière, grille auto-fill responsive
Tableau composants groupés par catégorie, barre de progression disponibilité
Formulaire d'ajout rétractable, boutons −/+ AJAX pour débiter/restituer
Import BOM KiCad avec rapport ✅/⚠️/❌/—

🏷️ Étiquettes imprimables

Impression multi-étiquettes depuis la sélection ou la fiche
QR code généré en Python pur (zéro dépendance externe)
Copies multiples par étiquette, grille auto-fill dans l'aperçu

⚙️ Configuration des étiquettes (/label-settings)

Format (mm), couleurs, tailles de police, 11 toggles on/off
Aperçu en temps réel, config sauvegardée en base

🔔 Alertes stock bas

Seuil min_stock par composant
Page dédiée + bandeau rouge sur l'accueil


Paramètres (/settings)
SectionContenu🏠 GénéralNom de l'app, adresse de base QR codes, seuil d'alerte par défaut🗂️ CatégoriesLien vers /categories — gestion des catégories personnalisées🏷️ ÉtiquettesLien vers /label-settings💾 SauvegardeZIP complet (base + images)📊 StatsComposants, projets, tailles, alertes de complétude🔍 EnrichissementRelance sur tous les composants incomplets🖼️ EasyEDAListe des composants sans symbole/footprint, téléchargement en masse, réconciliation🧹 NettoyageSupprime les images orphelines

Structure du projet
stock_composants/
├── run.py
├── requirements.txt
├── README.md
├── CHANGELOG.md
└── app/
    ├── __init__.py
    ├── models/
    │   ├── database.py          # SQLite, schéma, migrations à chaud
    │   ├── component.py         # CRUD composants, pagination, déduplication
    │   ├── category.py          # Catégories LCSC + custom (ID < 0)
    │   ├── project.py           # CRUD projets
    │   └── settings.py          # Config clé/valeur
    ├── views/component_view.py
    ├── controllers/
    │   ├── component_controller.py   # Stock, import, enrichissement, étiquettes, catégories, paramètres
    │   └── project_controller.py    # Projets, BOM KiCad
    ├── services/
    │   ├── lcsc_scraper.py      # Scraping wmsc.lcsc.com
    │   ├── easyeda.py           # PNGs symbole/footprint
    │   └── qr_generator.py      # QR code SVG Python pur
    ├── templates/
    │   ├── base.html
    │   ├── partials/category_select.html
    │   ├── components/
    │   │   ├── index.html       # Tableau stock
    │   │   ├── add.html         # Ajout (import LCSC + image manuelle + mode série)
    │   │   ├── edit.html        # Édition
    │   │   ├── detail.html      # Fiche composant
    │   │   ├── import.html      # Import CSV
    │   │   ├── alerts.html      # Alertes stock bas
    │   │   ├── categories.html  # Gestion catégories custom
    │   │   ├── labels_print.html
    │   │   ├── label_settings.html
    │   │   └── settings.html
    │   └── projects/
    │       ├── index.html
    │       ├── form.html
    │       ├── detail.html
    │       ├── import_bom.html
    │       └── bom_report.html
    └── static/
        ├── css/style.css        # ~42Ko, thème sombre
        └── js/app.js

Base de données
SQLite dans instance/stock.db (créée automatiquement au démarrage).
TableRôlecomponentsStock (ref LCSC unique, prix, image, symbol/footprint PNG)categoriesCatégories LCSC (ID > 0) + custom (ID < 0)projectsProjets avec image optionnelleproject_componentsLiaison composants ↔ projetssettingsConfiguration clé/valeur
Les migrations sont appliquées à chaud — pas de perte de données sur une base existante.

API JSON
EndpointDescriptionGET /api/componentsListe composants (?search=)GET /api/lcsc-preview?ref=C149504Prévisualisation LCSCPOST /component/<id>/adjust{"delta": ±N}POST /enrich/<id>Relance enrichissement LCSCGET /labels?ids=1,2,3Page impression étiquettesGET /api/easyeda-pngs/<ref>PNG EasyEDA

Dépannage
Images et catégories vides après import
Flask doit tourner avec use_reloader=False (déjà configuré).
QR code ne fonctionne pas sur mobile
Configurer l'adresse de base dans ⚙️ Paramètres → Général.
Ex : http://192.168.1.50:5000. Lancer Flask avec host='0.0.0.0' dans run.py.
Symboles/footprints présents mais compteur indique des manquants
Utiliser 🔗 Réconcilier avec les fichiers dans les paramètres.
BOM KiCad non reconnue
Les composants KiCad doivent avoir un champ LCSC Part Number renseigné.
Catégories personnalisées n'apparaissent pas dans le select
Elles sont créées via ⚙️ Paramètres → 🗂️ Gérer les catégories et apparaissent immédiatement.
Réinitialiser la base
Supprimer instance/stock.db et relancer. Les images sont conservées.
