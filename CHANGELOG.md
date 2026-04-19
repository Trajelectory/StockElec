# Changelog — StockEleK

---

## v3.1 — Audit qualité, KiCad intelligent & robustesse 🔒

> Audit de sécurité complet (3 rounds), génération KiCad unitaire, fusion intelligente des librairies, corrections de performances et de robustesse.

### 🔒 Audit de sécurité & robustesse

**Transactions SQLite — couverture complète**
- 22 commits protégés par `try/except + db.rollback()` dans tous les models et controllers
- `rangement_save()`, `clear_history`, `reset_db` couverts (manquaient au premier audit)
- `database.py` : migrations de boot intentionnellement sans rollback (erreur visible immédiatement au démarrage)

**SQLite — performances et fiabilité**
- Mode **WAL** activé (`PRAGMA journal_mode=WAL`) : lectures concurrentes sans bloquer les écritures sous Waitress multi-thread
- `timeout=10` sur toutes les connexions : plus de crash immédiat si la base est verrouillée
- `PRAGMA foreign_keys=ON` activé systématiquement
- `PRAGMA synchronous=NORMAL` pour des performances optimales en WAL
- **Fix bug critique** `_migrate_v2` : `existing_cols` était un snapshot stale — remplacé par `_col_exists()` qui relit `PRAGMA table_info` à chaque vérification (colonnes `symbol_png` / `footprint_png` correctement migrées)
- **11 index** au total : ajout de `description`, `manufacturer`, `mouser_part_number`, `digikey_part_number`, `(min_stock, quantity)`

**Performances**
- `_get_led_config()` : 5 requêtes `SettingsModel.get()` → 1 seule via `get_all()`
- `settings()` : 7 appels `get_db()` → 1 seul en tête de fonction
- `context_processor` : cache TTL 5s avec `threading.Lock()` — plus de requête SQL à chaque page vue
- Cache P4 thread-safe : `led_on._p4_cache` (non thread-safe) → dict module-level protégé par `threading.Lock()`

**Qualité du code**
- Tous les imports lazy déplacés en haut de fichier (hors `easyeda.fetch_and_save` dans thread worker)
- `except Exception` typés : `RequestException`, `(TypeError, KeyError)`, `sqlite3.OperationalError` selon le contexte
- `import shutil` doublon supprimé dans `routes_settings.py`
- `__import__('datetime')` remplacé par un import normal
- Doublon `"sensor"` dans `LED_COLOR_DEFAULTS` supprimé
- Gestionnaires d'erreur HTTP 404 et 500 enregistrés dans `__init__.py` (JSON pour les routes API, HTML pour les autres)

**Sécurité**
- `require_esp32_token` : le navigateur est maintenant autorisé via `Referer` **ou** `X-Requested-With: XMLHttpRequest` — corrige le bug d'ajustement de stock depuis l'interface web
- `detail.js` : les deux `fetch()` vers `/adjust` envoient `X-Requested-With: XMLHttpRequest`
- `_save_project_image` : vérification des **magic bytes** (12 premiers octets) avant d'accepter un upload — ne se fie plus au `Content-Type` déclaré par le navigateur
- `digikey_scraper` : log d'erreur token masqué — `err_msg` au lieu de `data` brut (évite l'exposition de `client_secret`)
- Suppression des images fichier lors de la suppression d'un composant (`ComponentModel.delete()`)
- `requirements.txt` : versions fixées avec `==` pour garantir la reproductibilité des installations

### ⚡ KiCad — génération unitaire & fusion intelligente

**Bouton "⚙ Générer KiCad" sur la fiche composant**
- Route `POST /kicad/generate-one` : génère 1 seul composant par sa référence LCSC
- Délai minimal (0.5s au lieu de 2s — pas besoin d'attendre pour 1 seul composant)
- Bouton visible uniquement si au moins un fichier manque (sym/fp/3D)
- Rechargement automatique de la fiche après ~12s pour afficher les badges mis à jour
- Fini de relancer le job sur tout le stock pour un nouveau composant !

**Fusion intelligente — `skip_existing` avec merge**
- Checkbox **"Ne pas écraser les libs existantes"** dans les settings KiCad, **cochée par défaut**
- `merge_symbols` avec `skip_existing=True` : lit les noms déjà présents dans le `.kicad_sym`, n'ajoute que les symboles **nouveaux** en fin de fichier — préserve les modifications manuelles
- `merge_footprints` avec `skip_existing=True` : ne copie pas les `.kicad_mod` déjà présents dans le `.pretty/`
- Feedback dans l'interface : `+N symbole(s) ajouté(s)` / `N lib(s) protégée(s)` / `déjà à jour`
- `get_library_stats()` corrigé : ne compte plus les fichiers fusionnés (`.pretty/`, `packages3d/`) — compteurs sym/fp/3D maintenant cohérents

### 🌍 Internationalisation

- 14 nouvelles clés dans `fr.json` et `en.json` : `kicad_gen_btn`, `kicad_gen_running`, `kicad_gen_launched`, `kicad_gen_in_progress`, `kicad_skip_existing`, `kicad_skip_existing_hint`, `kicad_merge_protected`, `kicad_merge_added`, `kicad_merge_uptodate`, `kicad_merge_preserved`, `kicad_reg_sym_added`, `kicad_reg_fp_added`, `kicad_reg_added`, `kicad_reg_uptodate`
- Toutes les nouvelles strings hardcodées dans les templates remplacées par des clés `t.*`

### 🎨 Interface

- **Noms de catégories tronqués** dans la sidebar stock : `white-space: normal` + `word-break: break-word` sur `.sk-cat-btn` — "Signal Switches, Multiplexers, Decoders" s'affiche maintenant en entier

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
- **Sélecteur de statut rapide** dans le hero de la fiche projet
- **Onglets BOM / Notes / Checklist / Liens / Journal** avec barre sticky
- **Notes Markdown** avec parser JS maison complet
- **Checklist** avec 3 templates (PCB, Code, 3D), barre de progression
- **Liens** avec icônes auto par domaine (GitHub, KiCad, JLCPCB, Thingiverse…)
- Import/export BOM, création des composants manquants en un clic
- **Préparer le kit** : débit automatique de tous les composants BOM
- Journal des mouvements de stock par projet
- Tags de discipline : PCB, Code, 3D, Mécanique, Design, Recherche

### ⚙️ Paramètres — enrichissements

- Section **ESP32** : URL, token, couleur LED, durée, offsets par tiroir, éditeur couleurs par catégorie
- Section **Backup** : panneau avec tailles affichées avant téléchargement
- Section **Ressources** : liens vers le Manuel et la Documentation CSS

### 🗄️ Base de données & performance

- **6 index SQLite** ajoutés au démarrage
- Migration `notes` ajoutée pour les nouvelles installations
- Colonnes `notes`, `checklist`, `links`, `image_path` sur la table `projects`

### 📖 Documentation intégrée

- **`/docs`** : documentation CSS interactive (20 namespaces, 750+ classes)
- **`/docs/manuel`** : manuel d'utilisation complet (23 sections)

### 🎨 CSS & Interface

- Nettoyage `legacy.css` : 67 règles mortes supprimées
- 2 clés i18n ajoutées — 751 clés FR/EN synchronisées

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
