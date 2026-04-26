# Changelog — StockEleK

---

## v4.0 — Refonte UI complète & audit qualité final 🎨

> Refonte totale de l'interface (home, settings, add, rangement), audit de code P1+P2+P3 complet, corrections de bugs, optimisations SQL et architecture.

### 🎨 Refonte de l'interface

**Page d'accueil — minimaliste**
- Logo centré + titre + barre de recherche pleine largeur — plus de dashboard
- Suppression des 5 requêtes SQL au chargement (stats, graphes, fabricants, alertes, mouvements)
- Autocomplete amélioré : navigation clavier ↑↓, badge source coloré (LCSC bleu · Mouser orange · DigiKey rouge), section Projets
- `home.css` : 950L → 212L · `home.html` : 568L → 171L

**Page Settings — sidebar 8 sections**
- Navigation sidebar fixe : Général, Intégrations, EasyEDA, ESP32 & LEDs, KiCad, Statistiques, Maintenance, Zone de danger
- Hash URL (`/settings#esp32`) — onglet actif survit aux rechargements POST
- Toggle debug toolbar instantané (sans recharger)
- Test connexion ESP32 en live (`/api/led/ping`) + chenillard par plateau depuis l'interface
- Color picker natif pour les 18 couleurs LED par catégorie + bouton reset global
- Progression KiCad en temps réel avec log live
- Toasts auto-dismiss (4s)
- Stats en cards avec code couleur automatique (vert = ok · orange = à vérifier)
- Badges de notification sur les onglets sidebar (nb. composants sans EasyEDA, à enrichir)
- `settings.css` : 901L → 438L · `settings.html` : 1416L → 842L

**Page Add — layout 2 colonnes**
- Sidebar droite sticky : Stock & Prix avec stepper +/− et calcul total automatique
- Références fournisseurs en grille colorée (dot LCSC bleu, Mouser orange, DigiKey rouge)
- Zone upload image avec drag & drop natif + aperçu
- Attributs personnalisés en grille propre avec bouton suppression discret
- Titre et lien retour au stock en haut de page (hors sidebar)
- `add.html` : 365L · CSS `nadd-*` dans `legacy.css`

**Page Rangement — réécriture totale**
- Zéro héritage de l'ancien code : `rangement.html`, `rangement.css`, `rangement.js` réécrits de zéro
- Barre de recherche globale avec navigation ↑↓ (F3/Shift+F3), cellule courante en vert distinct
- Points de notification orange sur les onglets si résultats sur d'autres plateaux
- Barre de remplissage animée par plateau dans les onglets
- Filtre catégorie dans le popup d'assignation (pills dynamiques)
- Export PNG via iframe isolée — résout définitivement le bug `color-mix()` avec html2canvas
- Chargement AJAX lazy des composants au premier clic popup (`_comp_loaded = false`)
- Mode lecture / édition avec verrouillage visuel (pointer-events, bouton Save masqué)
- Zoom slider 44→160px via `--cell` CSS variable
- `rangement.js` : JS pur extrait du template (33Ko, zéro Jinja)
- `rangement.html` : 303L · `rangement.css` : 626L · `rangement.js` : 568L

### 🔧 Audit P1 — Corrections immédiates

- Suppression des imports inutilisés (`requests`, `json`, `threading`) dans 5 controllers
- **6 index SQLite** créés au démarrage : `idx_comp_category`, `idx_comp_location`, `idx_comp_manufacturer`, `idx_comp_lcsc`, `idx_movements_comp`, `idx_movements_created`
- Whitelists SQL explicites : `_ALLOWED_ENRICH_COLS` dans `component.py`, `_ALLOWED_COMP_UPDATE_COLS` dans `project_controller.py`
- Silencing des loggers tiers verbeux : `PIL`, `PIL.PngImagePlugin`, `urllib3`, `werkzeug` → niveau WARNING dans `__init__.py`

### 🔧 Audit P2 — Migration JS/CSS et refactoring

- `rangement.js` extrait depuis `rangement.html` (33Ko JS pur, variables Jinja restent dans le template)
- `home.css` créé depuis `home.html` (styles migrés)
- `detail_dc.css` créé depuis `detail.html` (20Ko — classes `dc-*`)
- `stock.css` complété depuis `index.html`
- `bom_analyser.py` extrait de `project_controller.py` (997L → 779L)
- `_settings_get_context(db)` extrait de `settings()` (322L → 230L)
- Route `/rangement` optimisée : `SELECT *` → `SELECT assignés seulement`
- Route API `/api/components/for-rangement` créée pour le popup AJAX

### 🔧 Audit P3 — Découpage des fonctions longues

- `render_toolbar()` : 315L → **238L** — 4 sous-fonctions créées : `_build_tpl_panel`, `_build_logs_panel`, `_build_req_panel`, `_build_config_panel`
- `settings()` : 322L → **230L** — `_settings_get_context(db)` extrait
- `generate_library()` : 205L → **185L** — `_setup_library_dirs()` extrait
- `_C_ACCENT` défini au niveau module dans `debugtoolbar.py` (fix bug post-refactoring des sous-fonctions)

### 🐛 Corrections de bugs

- **App context dans les threads** : `_fetch_all_easyeda()` dans `routes_settings.py` et `_enrich()` dans `project_controller.py` n'avaient pas de `with app.app_context()` → erreur `Working outside of application context` lors de la génération EasyEDA depuis les Paramètres. Corrigé avec le pattern `_app = current_app._get_current_object()` + `with _app.app_context():`
- **`url_for()` dans les CSS statiques** : lors de la migration P2, `url_for("static", filename="img/Logo.png")` avait été copié dans `home.css` — non interprété par Jinja2 dans un fichier statique → logo invisible. Corrigé en `<img src="{{ url_for(...) }}">` dans le template + script JS swap thème clair/sombre
- **Classes `lcsc-*` perdues** : les styles du Quick Import LCSC étaient dans l'ancien `settings.css` supprimé lors de la refonte → page Add visuellement cassée. Restaurées dans `legacy.css`
- **Radios natifs dans History** : `<input type="radio">` avec apparence navigateur par défaut → `display:none`, seuls les labels colorés restent visibles
- **Double emoji dans les titres** : emoji présent à la fois dans la clé i18n (`t.settings.card_backup = '💾 Sauvegarde'`) et dans le template (`💾 {{ t.settings.card_backup }}`). Corrigé sur 6 titres
- **Double loupe dans Stock** : un `<span>🔍</span>` inline en doublon retiré du champ de filtrage catégorie
- **16 clés i18n manquantes** : `labels.toggle_image`, `labels.toggle_lcsc`, `labels.badge_package`… — Jinja2 retournait silencieusement une chaîne vide → labels invisibles dans Label Settings. Toutes ajoutées dans `fr.json` et `en.json`
- **Endpoint `components.kicad_download`** : blueprint KiCad s'appelle `kicad`, pas `components` → `kicad.download`
- **`/kicad/generate` body JSON** : la route attend `{"delay": 2.0}` en JSON, pas en query string `?delay=2`
- **Toggle debug toolbar** : le track cliquait sur la checkbox via son event `change`, mais comme la checkbox était dans le form `save_general` et `dbg-form` séparé, le submit partait sur le mauvais form. Réécrit avec listener direct sur le track

### 🌍 i18n

- **799 clés** FR/EN synchronisées (était 765 en v3.1)
- 16 nouvelles clés `labels.toggle_*` et `labels.badge_*`
- Tagline raccourci : "Centre de contrôle — Atelier électronique" → "Atelier électronique"
- Nouvelles clés settings : `label_esp32_test_plateau`, `label_esp32_test_delay`, `btn_esp32_test_seq`

---

## v3.1 — Audit qualité, KiCad intelligent & robustesse 🔒

> Audit de sécurité complet (3 rounds), génération KiCad unitaire, fusion intelligente des librairies, corrections de performances et de robustesse.

### 🔒 Audit de sécurité & robustesse

**Transactions SQLite — couverture complète**
- 22 commits protégés par `try/except + db.rollback()` dans tous les models et controllers
- `rangement_save()`, `clear_history`, `reset_db` couverts

**SQLite — performances et fiabilité**
- Mode **WAL** (`PRAGMA journal_mode=WAL`), `timeout=10`, `PRAGMA foreign_keys=ON`, `PRAGMA synchronous=NORMAL`
- Fix bug critique `_migrate_v2` : `_col_exists()` relit `PRAGMA table_info` à chaque vérification
- **11 index** au total : ajout de `description`, `manufacturer`, `mouser_part_number`, `digikey_part_number`, `(min_stock, quantity)`

**Performances**
- `_get_led_config()` : 5 requêtes `SettingsModel.get()` → 1 via `get_all()`
- `settings()` : 7 appels `get_db()` → 1 seul en tête de fonction
- Context processor cache TTL 5s avec `threading.Lock()`
- Cache P4 thread-safe : dict module-level protégé par `threading.Lock()`

**Qualité du code**
- Imports lazy déplacés en haut de fichier
- `except Exception` typés selon le contexte
- `__import__('datetime')` remplacé par import normal
- Gestionnaires d'erreur HTTP 404 et 500 (JSON pour API, HTML pour les autres)

**Sécurité**
- `require_esp32_token` : navigateur autorisé via `Referer` ou `X-Requested-With: XMLHttpRequest`
- Vérification des **magic bytes** (12 premiers octets) avant d'accepter un upload image
- Log token DigiKey masqué (`err_msg` au lieu de `data` brut)
- Suppression des images fichier lors de la suppression d'un composant
- `requirements.txt` : versions fixées avec `==`

### ⚡ KiCad — génération unitaire & fusion intelligente

- Route `POST /kicad/generate-one` : génère 1 seul composant par sa référence LCSC (délai 0.5s au lieu de 2s)
- Bouton visible uniquement si au moins un fichier manque (sym/fp/3D)
- Rechargement automatique de la fiche après ~12s
- Fusion intelligente avec `skip_existing=True` : lit les noms présents dans `.kicad_sym`, n'ajoute que les nouveaux
- `merge_footprints` : ne copie pas les `.kicad_mod` déjà présents
- Feedback : `+N symbole(s) ajouté(s)` / `N lib(s) protégée(s)` / `déjà à jour`

### 🌍 i18n — 14 nouvelles clés KiCad

`kicad_gen_btn`, `kicad_gen_running`, `kicad_gen_launched`, `kicad_skip_existing`, `kicad_merge_protected`, `kicad_merge_added`, `kicad_merge_uptodate`, `kicad_reg_sym_added`, `kicad_reg_fp_added`, `kicad_reg_added`, `kicad_reg_uptodate`

---

## v3.0 — LEDs, projets enrichis & documentation 💡

> Intégration complète de l'ESP32 avec LEDs WS2812B et afficheur HT16K33, refonte des projets, système de documentation intégré, firmware v6.1.

### 💡 Intégration ESP32 & LEDs

- Firmware v4.0 → **v6.1** :
  - Ruban WS2812B : fade in/out position + breathing doux tiroir (non-bloquant)
  - Afficheur HT16K33 14-segments : veille clignotante après 33s
  - File d'attente 4 commandes, OTA, reconnexion WiFi watchdog
  - Headers CORS, sweep de boot, config runtime via `POST /config`
  - **Page web embarquée** `GET /` : statut live, contrôle, `POST /reboot`
  - `/status` retourne `wifi_rssi`, `free_heap`, `display_sleeping`
- **18 familles de couleurs LED** avec matching par mot-clé ordonné
- Éditeur dans les Paramètres : color picker natif + champ hex synchronisé + reset
- `POST /api/led/<cell_id>/on` accepte `component_id` → couleur adaptée à la catégorie

### 📁 Projets — refonte complète

- Vue Kanban 8 colonnes, drag & drop AJAX
- Notes Markdown (parser JS maison complet), Checklist (3 templates, barre progression)
- Liens avec icônes auto par domaine, import/export BOM, kit automatique
- Journal des mouvements par projet

### 📖 Documentation intégrée

- `/docs` : documentation CSS interactive (25 namespaces)
- `/docs/manuel` : manuel d'utilisation complet (23 sections)

### 🗄️ Base de données

- Mode WAL activé, 6 index ajoutés, migration `notes` sur la table `projects`

---

## v2.2 — i18n, audit & rangement interactif 🌍

> Internationalisation complète FR/EN, audit qualité, refonte du plan de rangement.

- Infrastructure i18n complète : `locales/fr.json` + `en.json` (558 clés, 19 sections)
- 22 templates HTML traduits, tous les messages Python traduits
- Rangement : infobulle survol, menu contextuel clic droit (Assigner / LED / Vider)
- Imports centralisés, pagination historique, doublons CSS supprimés, `legacy.css` nettoyé

---

## v2.1 — Support multi-distributeurs 🌐

- **Mouser** via API officielle v1, **DigiKey** via API v4 + OAuth2 automatique
- Prévisualisation unifiée à l'ajout, badges cliquables
- Double enrichissement Mouser → LCSC si attributs incomplets
- Export CSV 19 colonnes, encodage `utf-8-sig`

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
