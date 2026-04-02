# Changelog — StockEleK

---

## v2.2 — i18n, audit de code & rangement interactif 🌍

> Internationalisation complète FR/EN, audit qualité de code, refonte du plan de rangement avec menu contextuel et infobulle.

### 🌍 Internationalisation (i18n) — FR / EN
- Infrastructure complète : fichiers `app/locales/fr.json` + `en.json` (558 clés, 19 sections)
- Context processor Flask injecte `t` et `lang` dans tous les templates
- Helper `_t("section.key", **kwargs)` dans les controllers pour les `flash()` et `jsonify` errors
- Cache locale en mémoire, invalidé automatiquement au changement de langue
- Sélecteur de langue dans **⚙️ Paramètres → Général** (🇫🇷 Français / 🇬🇧 English)
- Tous les templates traduits (22 fichiers HTML), tous les messages Python traduits
- Sections couvertes : nav, home, stock, settings, form, detail, bom, projects, project_form, import_bom, import_csv, import_result, reorder, history, alerts, categories, storage, labels, msg

### 🗃️ Plan de rangement — refonte de l'interaction
- **Clic gauche supprimé** — la grille est maintenant en lecture seule au clic
- **Survol** → infobulle contextuelle (délai 200ms) : image du composant, nom, référence LCSC, fabricant, quantité, package, emplacement
  - Se positionne intelligemment pour ne pas déborder de l'écran
  - Disparaît immédiatement à la sortie de la case
- **Clic droit** → menu contextuel redessiné :
  - 📦 **Assigner un composant** — ouvre la popup de recherche/assignation
  - 💡 **Allumer la LED** — désactivé visuellement (italique + "bientôt"), intégration ESP32 à venir
  - 🗑️ **Vider la case** — fonctionnel, grisé automatiquement si la case est vide
- Correction du bug de timing : `_ctxCell` sauvegardé dans une variable locale avant fermeture du menu, fermeture sur `mousedown` externe pour ne pas interférer avec les `click` des boutons

### 🔧 Audit de code & corrections
- **Imports** : tous les imports locaux remontés en tête de `component_controller.py`, suppression de 20+ imports redondants dans les fonctions
- **Types de mouvements** : `project_use` et `project_return` ajoutés dans `MovementModel.TYPES`
- **Pagination historique** : correction de l'effet de bord Jinja (`qs.update()`) — reconstruction propre de l'URL par macro
- **Macro `sort_th`** : déplacée en tête du `block content` (était invalide dans le `thead`)
- **`TOKEN_URL` DigiKey** : centralisé dans `digikey_scraper.py`, utilisé dans le test de clé
- **Home per_page** : défaut aligné à 5 (correspond au premier bouton), mémorisé en `localStorage`
- **Doublons CSS** supprimés : `col-hide-md` en double dans `responsive.css`, media queries `820px` dupliquées dans `detail.css` et `forms.css`
- **`legacy.css`** nettoyé : 263 lignes supprimées (59 classes mortes)
- **Toolbar sticky** : `border-bottom` en thème clair, ombre désactivée via `[data-theme="light"]`
- **`product_url`** : testé avec filtre `|lower` dans tous les templates pour les badges distributeurs
- **Fallback title** : `'StockElec'` → `'StockEleK'`
- **Debug `qr_generator.py`** : bloc de test en bas du fichier supprimé (polluait le terminal au démarrage)
- **Boutons raccourcis** page d'accueil supprimés (doublons de la navbar)
- **`math.ceil`** remplacé par division entière `//`
- **Backup** : leak de fichier temporaire corrigé (`os.unlink` dans `finally`)

### 🎨 Interface & thème
- **Logo adaptatif** : `Logo.png` en thème sombre, `Logo_c.png` en thème clair (navbar + page d'accueil)
- **Bouton thème** ajouté dans le menu mobile, icône synchronisée (🌙/☀️)
- **Bouton "Vider le plateau"** par plateau dans la barre de stats du rangement

---

## v2.1 — Support multi-distributeurs 🌐

> Intégration complète Mouser et DigiKey, corrections de fond, nettoyage de code.

### 🛒 Multi-distributeurs (Mouser + DigiKey)
- Support **Mouser** via API officielle v1 — clé configurable dans les Paramètres
- Support **DigiKey** via API officielle v4 — OAuth2 Client Credentials, token mis en cache thread-safe
- Prévisualisation unifiée à l'ajout : détection automatique de la source
- Import BOM KiCad multi-sources : colonnes LCSC, Mouser et DigiKey détectées automatiquement
- Enrichissement async après import pour chaque source
- Badges colorés avec logo distributeur dans toutes les vues, **cliquables** vers la fiche produit
- Colonne `product_url` en base — URL exacte retournée par l'API

### 🔁 Double enrichissement Mouser → LCSC
- Si Mouser retourne peu d'attributs, recherche automatique sur LCSC par MPN
- Complète `attributes`, `package`, `datasheet_url`, `description_long` et l'image depuis LCSC

### 📊 Export CSV enrichi
- 19 colonnes : ajout `mouser_part_number`, `digikey_part_number`, `description_long`, `product_url`
- Encodage `utf-8-sig` pour compatibilité Excel

### 🐛 Bugs corrigés
- DigiKey : préfixe numérique dans les refs, fallback `/keyword`, refresh token sur 401
- Mouser : parsing prix `"1,92 €"`, attributs dupliqués, champ RoHS
- BOM projets : threads sans `app_context`
- Import CSV : colonnes `min_stock`, `category`, `location`, `notes` absentes de l'INSERT

### 🧹 Nettoyage
- Suppression de `lcsc_api.py` (code mort), templates orphelins (`dashboard.html`, `gridfinity.html`)
- Reset BDD complet dans les Paramètres avec confirmation par saisie de `RESET`

---

## v2.0 — Refonte majeure 🎉

> Release publique. Réécriture complète du design, plan de rangement, historique.

### 🎨 Design system v2
- Nouveau thème sombre violet/indigo (`#7c6cff`), typographie Inter
- CSS modulaire : 15 fichiers dans `modules/`
- Navbar avec backdrop blur, boutons et badges redessinés

### 🏠 Page d'accueil
- Barre de recherche centrée, compteurs discrets, tableau des derniers ajouts

### 📋 Historique & Réapprovisionnement
- Table `stock_movements`, page `/history` filtrable, page `/reorder`

### 📦 Plan de rangement ⭐
- Grille interactive, plusieurs plateaux configurables, popup d'assignation, sauvegarde automatique

### 🔧 Serveur
- Remplacement du serveur Flask dev par **Waitress**

---

## v1.x — Historique

<details>
<summary>Voir l'historique des versions 1.x</summary>

**v1.0** — Architecture Flask + SQLite + MVC, tableau paginé, import CSV LCSC, CRUD composants

**v1.1** — Enrichissement LCSC automatique (scraping `wmsc.lcsc.com`)

**v1.2** — Déduplication à l'import, pagination 25/50/100

**v1.3** — Import rapide LCSC avec prévisualisation

**v1.4** — CRUD projets, alertes stock, champ `min_stock`

**v1.5** — Catégories hiérarchiques avec `<optgroup>`

**v1.6** — Import BOM KiCad, rapport ✅/⚠️/❌

**v1.7** — Images de projets

**v1.8** — Étiquettes imprimables + QR code Python pur, multi-sélection

**v1.9** — Symbole & Footprint EasyEDA, lightbox

**v1.10** — Support export panier LCSC (`export_cart_*.csv`)

**v1.11** — Refonte page projet

**v1.12** — Configuration des étiquettes avec aperçu temps réel

**v1.13** — Paramètres enrichis : sauvegarde ZIP, stats, enrichissement en masse

**v1.14–v1.21** — Mode ajout en série, catégories personnalisées, upload image manuelle, EasyEDA en masse, nettoyages CSS

</details>
