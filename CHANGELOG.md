# Changelog — StockEleK

---

## v3.0 — LEDs, projets enrichis & documentation 💡

> Intégration complète de l'ESP32 avec LEDs WS2812B et afficheur HT16K33, refonte des projets, système de documentation intégré, firmware v6.1.

### 💡 Intégration ESP32 & LEDs

- **Firmware v4.0 → v6.1** développé de zéro :
  - Ruban 1 (WS2812B) : emplacement exact du composant avec fade in/out
  - Ruban 2 (WS2812B) : tiroir A-Z avec **breathing doux non-bloquant** (v6.1)
  - Afficheur HT16K33 14-segments : affiche la case (`A 16`), veille clignotante après 33s
  - File d'attente de 4 commandes LED
  - OTA (mise à jour firmware sans câble)
  - Reconnexion WiFi automatique (watchdog dans `loop()`)
  - Fix VLA `fadeOut` → buffer statique `MAX_LEDS_PER_CMD`
  - Queue allégée : `MAX_LEDS_PER_CMD=16` au lieu de `NUM_LEDS=500`
  - Headers CORS sur toutes les routes
  - Sweep de boot propre sur le ruban tiroir
  - Config runtime via `POST /config` sauvegardée en Preferences flash
  - **Page web embarquée** sur `GET /` : statut live, contrôle manuel, paramètres
  - **`POST /reboot`** : redémarrer l'ESP32 depuis la page web
  - `/status` retourne `wifi_rssi`, `free_heap`, `display_sleeping`
  - Forward declarations pour compatibilité avec le préprocesseur Arduino IDE

- **Couleurs LED automatiques par catégorie** :
  - 18 familles avec couleurs par défaut (résistances orange, condensateurs bleu, ICs violet…)
  - 49 catégories LCSC réelles couvertes avec matching par mot-clé ordonné
  - Ordre de matching optimisé (sensor avant resistor, connector avant ic, led driver avant led…)
  - **Éditeur dans les Paramètres** : color picker natif + champ hex synchronisé + bouton reset par famille
  - Couleurs sauvegardées dans la DB settings, relues à chaque allumage
  - Couleur du ruban tiroir configurable séparément (`DRAWER_COLOR_STR`)

- **Intégration côté Flask** :
  - `POST /api/led/<cell_id>/on` : accepte `component_id` optionnel → résout la catégorie → couleur adaptée
  - `flashLed(cellId, componentId)` dans `detail.js` et `rangement.html`
  - Test de connexion ESP32 depuis les Paramètres

### 📁 Projets — refonte complète

- **Vue Kanban** avec 8 colonnes de statut, drag & drop AJAX
- **Sélecteur de statut rapide** dans le hero de la fiche projet :
  - Badge de statut cliquable → dropdown avec les 8 options
  - `position: fixed` calculé via `getBoundingClientRect()` (contourne `overflow:hidden` du hero)
  - Sauvegarde AJAX instantanée via `POST /projects/<id>/status`
- **Onglets BOM / Notes / Checklist / Liens / Journal** avec barre sticky
- **Sidebar BOM** : filtres par catégorie, actions, activité récente
- **Notes Markdown** avec parser JS maison complet :
  - H1-H4, gras/italique/***bold-italic***, ~~barré~~, ++souligné++, ==surligné==
  - Listes UL/OL/checkboxes imbriquées, blockquotes, tableaux, séparateurs, exposants
  - Code inline et blocs avec langue
  - Liens et images `![alt](url)`
  - Couleurs custom : `{red}`, `{orange}`, `{green}`, `{blue}`, `{purple}`, `{pink}`, `{gray}`, `{white}`
  - Upload image par bouton / drag-drop / coller (`Ctrl+V`)
  - Sauvegarde auto AJAX 1,2s après frappe
- **Checklist** avec 3 templates (PCB, Code, 3D), barre de progression
- **Liens** avec icônes auto par domaine (GitHub, KiCad, JLCPCB, Thingiverse…)
- Import/export BOM, création des composants manquants en un clic
- **Préparer le kit** : débit automatique de tous les composants BOM
- Journal des mouvements de stock par projet
- Tags de discipline : PCB, Code, 3D, Mécanique, Design, Recherche
- Mémorisation du dernier onglet ouvert par projet (localStorage)

### ⚙️ Paramètres — enrichissements

- Section **ESP32** : URL, token, couleur LED, durée, offsets par tiroir, éditeur couleurs par catégorie
- Section **Backup** : panneau avec tailles affichées (`stock.db`, `images/`, `project-images/`) avant téléchargement
- Section **Ressources** : liens vers le Manuel et la Documentation CSS
- Sauvegarde des couleurs LED (18 clés) dans les settings

### 🗄️ Base de données & performance

- **6 index SQLite** ajoutés au démarrage : `components.category`, `components.location`, `components.lcsc_part_number`, `stock_movements.component_id`, `stock_movements.project_id`, `project_components.project_id`
- Migration `notes` ajoutée pour les nouvelles installations
- Colonnes `notes`, `checklist`, `links`, `image_path` sur la table `projects`

### 📖 Documentation intégrée

- **`/docs`** : documentation CSS interactive extraite dynamiquement des fichiers CSS
  - 20 namespaces documentés (750+ classes)
  - Exemples de rendu inline : alertes, badges, boutons, quantités, Markdown, BOM, Kanban, dashboard…
  - Recherche live, surlignage nav au scroll, copier-au-clic
  - Auto-mise à jour quand les CSS changent
- **`/docs/manuel`** : manuel d'utilisation complet (23 sections)
  - Couvre tout : démarrage, composants, enrichissement, stock, projets, BOM, notes, hardware, KiCad, API, tips

### 🎨 CSS & Interface

- Nettoyage `legacy.css` : 67 règles mortes supprimées (513 → 332 lignes)
- 2 clés i18n ajoutées (`detail.click_to_edit`, `detail.col_reference`) — 751 clés FR/EN synchronisées
- Namespace `pd-status-*` : sélecteur de statut animé
- Namespace `stg-led-*` : éditeur de couleurs LED (color picker + hex + reset)
- Namespace `stg-backup-*` : panneau de sauvegarde avec tailles

---

## v2.2 — i18n, audit de code & rangement interactif 🌍

> Internationalisation complète FR/EN, audit qualité de code, refonte du plan de rangement avec menu contextuel et infobulle.

### 🌍 Internationalisation (i18n) — FR / EN
- Infrastructure complète : `locales/fr.json` + `en.json` (558 clés, 19 sections)
- Context processor Flask, helper `_t()`, cache locale en mémoire
- Sélecteur de langue dans **⚙️ Paramètres → Général**
- 22 templates HTML traduits, tous les messages Python traduits

### 🗃️ Plan de rangement — refonte
- Survol → infobulle contextuelle (image, référence, quantité, package)
- Clic droit → menu contextuel : Assigner, Allumer LED, Vider
- Correction du bug de timing `_ctxCell`

### 🔧 Audit de code & corrections
- Imports centralisés, types de mouvements `project_use` / `project_return`
- Pagination historique, macro `sort_th`, `TOKEN_URL` DigiKey centralisé
- Doublons CSS supprimés, `legacy.css` nettoyé (263 lignes)
- Logo adaptatif sombre/clair, bouton thème dans le menu mobile

---

## v2.1 — Support multi-distributeurs 🌐

> Intégration complète Mouser et DigiKey, corrections de fond.

- **Mouser** via API officielle v1, **DigiKey** via API v4 + OAuth2 automatique
- Prévisualisation unifiée à l'ajout, badges cliquables
- Double enrichissement Mouser → LCSC si attributs incomplets
- Export CSV 19 colonnes, encodage `utf-8-sig`
- Reset BDD complet dans les Paramètres

---

## v2.0 — Refonte majeure 🎉

> Release publique. Réécriture complète du design, plan de rangement, historique.

- Nouveau design system violet/indigo, CSS modulaire
- Vue Kanban projets, BOM KiCad, historique, réapprovisionnement
- Plan de rangement interactif multi-plateaux
- Remplacement serveur dev → **Waitress**

---

## v1.x — Historique

<details>
<summary>Voir l'historique des versions 1.x</summary>

**v1.0** — Architecture Flask + SQLite + MVC, tableau paginé, import CSV LCSC, CRUD composants

**v1.1** — Enrichissement LCSC automatique

**v1.2** — Déduplication à l'import, pagination 25/50/100

**v1.3** — Import rapide LCSC avec prévisualisation

**v1.4** — CRUD projets, alertes stock, champ `min_stock`

**v1.5** — Catégories hiérarchiques

**v1.6** — Import BOM KiCad, rapport ✅/⚠️/❌

**v1.7** — Images de projets

**v1.8** — Étiquettes imprimables + QR code Python pur

**v1.9** — Symbole & Footprint EasyEDA, lightbox

**v1.10** — Support export panier LCSC

**v1.11** — Refonte page projet

**v1.12** — Configuration étiquettes avec aperçu temps réel

**v1.13** — Paramètres enrichis : sauvegarde ZIP, stats, enrichissement en masse

**v1.14–v1.21** — Mode ajout en série, catégories personnalisées, upload image manuelle, EasyEDA en masse, nettoyages CSS

</details>
