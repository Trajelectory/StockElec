# ⚡ StockEleK — Wiki

> Gestionnaire de stock de composants électroniques avec intégration KiCad, étiquettes, rangement Gridfinity et afficheur LED ESP32.

## Navigation

| Section | Description |
|---------|-------------|
| [🚀 Installation & démarrage](Installation) | Prérequis, configuration initiale, lancement |
| [📦 Gestion du stock](Gestion-du-stock) | Ajouter, rechercher, modifier, importer des composants |
| [📋 Projets](Projets) | Créer des projets maker, gérer la BOM, suivre la disponibilité |
| [🏷️ Étiquettes](Etiquettes) | Génération et impression d'étiquettes avec QR codes |
| [📐 Rangement Gridfinity](Rangement) | Plan de rangement visuel + LEDs ESP32 |
| [⚙️ Intégrations KiCad](KiCad) | Génération automatique de symboles et footprints |
| [🔌 Intégrations fournisseurs](Fournisseurs) | LCSC, EasyEDA, Mouser, DigiKey |
| [🖥️ Hardware ESP32](Hardware-ESP32) | Firmware S3 (LEDs + afficheur) et P4 (écran tactile) |
| [⚙️ Paramètres](Parametres) | Configuration complète de l'application |
| [🛠️ Debug Toolbar](Debug-Toolbar) | Outil de débogage intégré |
| [🔌 API REST](API-REST) | Endpoints JSON pour intégration externe |

---

## Présentation rapide

StockEleK est une application web locale (Flask + SQLite) conçue pour les makers et ingénieurs électroniciens qui souhaitent gérer leur stock de composants sans dépendre d'un service cloud.

### Ce que StockEleK sait faire

- **Stock** — gérer des centaines de composants avec photos, références multi-fournisseurs, caractéristiques techniques, historique des mouvements
- **Enrichissement automatique** — récupération des données depuis LCSC/EasyEDA, Mouser et DigiKey (description, package, image, prix, datasheet)
- **Projets** — créer des projets avec BOM, suivre la disponibilité des composants en stock, gérer checklist et statut
- **KiCad** — générer automatiquement les symboles (.kicad_sym) et footprints (.kicad_mod) pour tous les composants LCSC via JLC2KiCadLib, et les enregistrer dans KiCad
- **Rangement Gridfinity** — plan visuel de vos tiroirs avec assignation case→composant
- **LEDs WS2812B** — allumer la LED de la bonne case quand on cherche un composant, via un ESP32-S3
- **Étiquettes** — imprimer des étiquettes avec QR code pour chaque composant
- **Import/Export** — CSV avec prévisualisation avant import, export BOM pour JLCPCB

### Stack technique

- **Backend** : Python 3.11+ / Flask / SQLite (WAL mode)
- **Frontend** : HTML/CSS/JS vanilla, pas de framework JS
- **Hardware** : ESP32-S3 + LEDs WS2812B + afficheur HT16K33 (optionnel)
- **Firmware** : Arduino C++ (ESP32-S3) / LVGL v9 (ESP32-P4, à venir)
