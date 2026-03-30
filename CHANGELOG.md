# Changelog — StockElectory

---

## v2.1 — Support multi-distributeurs 🌐

> Intégration complète Mouser et DigiKey, corrections de fond, nettoyage de code.

### 🛒 Multi-distributeurs (Mouser + DigiKey)
- Support **Mouser** via API officielle v1 (`/search/partnumber`) — clé configurable dans les Paramètres
- Support **DigiKey** via API officielle v4 — OAuth2 Client Credentials (2-legged), token mis en cache
- Prévisualisation unifiée à l'ajout : saisie d'une ref LCSC, Mouser ou DigiKey → détection automatique de la source → pré-remplissage du formulaire
- Import BOM KiCad avec colonnes multi-sources : `LCSC`, `Mouser`, `DigiKey` détectées automatiquement
- Enrichissement async après import pour chaque source (threads avec `app_context`)
- Badges colorés avec logo distributeur dans toutes les vues (stock, accueil, projets, détail)
- Badges **cliquables** — lien direct vers la fiche produit du distributeur
- Colonne `product_url` en base — URL exacte retournée par l'API, convertie en locale `.fr`

### 🔁 Double enrichissement Mouser → LCSC
- Si l'API Mouser retourne peu d'attributs techniques, recherche automatique sur LCSC par MPN
- Complète `attributes`, `package`, `datasheet_url`, `description_long` et l'image depuis LCSC
- Délai de 0.4s entre les appels pour respecter les serveurs LCSC

### 🖼️ Gestion des images améliorée
- Téléchargement immédiat de l'image au moment de la création (plus d'attente async pour la preview)
- Encodage URL automatique pour les URLs avec espaces (ex: `PTA SERIES 45MM.JPG`)
- Vérification du `Content-Type` de la réponse — rejette les pages HTML servies à la place des images
- Détection des fichiers corrompus dans le cache — retéléchargement automatique
- `Referer` adapté selon le domaine de l'image (mouser.com / digikey.com)
- `Accept: image/*` ajouté aux headers pour signaler explicitement qu'on veut une image

### 🔑 Enrichissement via route `/enrich/<id>`
- Route multi-source : DigiKey → Mouser → LCSC selon la ref disponible
- Nouveau paramètre `force_attributes=True` pour écraser les attributs existants (ré-enrichissement)
- Bouton "Récupérer" visible pour toutes les sources (plus LCSC uniquement)

### 📊 Export CSV enrichi
- 19 colonnes au lieu de 15 : ajout `mouser_part_number`, `digikey_part_number`, `description_long`, `product_url`
- Encodage `utf-8-sig` pour compatibilité Excel (caractères spéciaux : Ω, µ, °...)
- Export accessible depuis la page Stock (bouton "⬇️ Export CSV") et depuis les Paramètres

### 🐛 Bugs corrigés
| Composant | Bug | Correction |
|---|---|---|
| DigiKey API | Préfixe `118-` dans les refs rejeté par `/productdetails` | Essai avec et sans préfixe numérique |
| DigiKey API | Fallback `/keyword` ne récupérait pas les `Parameters` | 2e appel `/productdetails` avec la ref exacte trouvée |
| DigiKey API | Token expiré entre preview et enrich async → 401 silencieux | Refresh automatique du token sur 401 |
| DigiKey URL | URLs construites manuellement → 404 | Utilisation de `ProductUrl` retourné par l'API |
| Mouser prix | `"1,92 €"` → crash float (€ non retiré) | Nettoyage complet avant `float()` |
| Mouser attrs | Attributs dupliqués (ex: `Conditionnement`) écrasés | Concaténation `"Reel / Cut Tape"` |
| Mouser RoHS | Champ `ROHSStatus` non lu | Détection `"compliant"` dans la valeur |
| Mouser requête | `IncludeExtendedAttributes` inexistant dans l'API v1 | Remplacé par `partSearchOptions: "Exact"` |
| BOM projets | Threads enrich sans `app_context` → SQLite inaccessible | `with app.app_context()` sur tous les threads |
| BOM description | Valeur KiCad (`0R 0402`) écrasait la description API | `description` et `description_long` toujours écrasés par l'enrich |
| `apply_enrichment` | `_maybe` bloquait si description déjà remplie | `description`/`description_long` sortis de `_maybe` |
| Page accueil | Colonnes `mouser_part_number`/`digikey_part_number` absentes du SELECT | Ajoutées avec `product_url` |
| Page projet | `ProjectComponent` ne mappait pas les refs Mouser/DigiKey | Attributs ajoutés dans `__init__` |
| Page projet | Bouton 🛒 LCSC-only dans les fiches projet | Redirige vers le bon distributeur |
| Import CSV | `min_stock`, `category`, `location`, `notes` absents de l'INSERT | Détection colonnes + insertion |

### 🧹 Nettoyage & qualité
- Suppression de `lcsc_api.py` — 8 Ko de code mort jamais importé
- Suppression des templates orphelins : `dashboard.html`, `gridfinity.html`, `label.html`
- Suppression de la route `label` (redirect inutile) et `digikey_debug` (debug temporaire)
- Suppression de `symbol_svg`/`footprint_svg` de la migration (colonnes jamais utilisées)
- `SECRET_KEY` lue depuis variable d'environnement `SECRET_KEY` avec fallback
- `Pillow` ajouté dans `requirements.txt`
- Import inutilisé `secure_filename` retiré de `project_controller.py`
- Reset BDD complet dans les Paramètres (phase de test) — confirmation par saisie de `RESET`

---

## v2.0 — Refonte majeure 🎉

> Release publique. Réécriture complète du design, nouvelles fonctionnalités atelier, plan de rangement.

### 🎨 Design system v2
- Nouveau design sombre violet/indigo (`#7c6cff`) — fini le bleu
- Typographie **Inter** (Google Fonts) avec poids 800 pour les titres
- Navbar avec backdrop blur, liens actifs avec bordure subtile
- Boutons, badges et alertes redessinés de zéro
- CSS modulaire : `style.css` de 40 lignes avec `@import` vers 15 modules dans `modules/`

### 🏠 Page d'accueil repensée
- Grande barre de recherche centrée (style Google) avec soumission automatique au bout de 400ms
- Compteurs discrets : références, pièces totales, alertes
- 5 raccourcis rapides (Stock, Ajouter, Projets, Alertes, Commander)
- Tableau des 5 derniers composants ajoutés, pleine largeur
- Route `/` → page d'accueil, `/stock` → tableau complet

### 📋 Historique des mouvements
- Table `stock_movements` en base — chaque +/− enregistré automatiquement
- Page `/history` filtrable par type (entrée / sortie / ajustement) et par limite
- Types : 📥 Entrée, 📤 Sortie, 🔧 Ajustement, 🌱 Initialisation

### 🛒 Réapprovisionnement
- Page `/reorder` : liste automatique des composants en rupture ou sous le seuil
- Quantité suggérée (3× le seuil), prix estimé de la commande, liens directs LCSC

### ⬇️ Export CSV
- Un clic pour télécharger tout le stock en `.csv` (`/export/csv`)

### 📦 Plan de rangement ⭐
- Page visuelle pour planifier l'organisation physique de son atelier
- Grille de cases cliquables représentant les plateaux imprimés en 3D
- Plusieurs plateaux configurables (ID, nom, colonnes × rangées)
- Navigation par **tabs** — un onglet par plateau, affichage instantané sans rechargement
- Barre de progression : taux d'occupation de chaque plateau
- Popup de recherche et d'assignation
- Sauvegarde automatique en BDD dès l'assignation

### ⚙️ Paramètres
- Bouton **🗑️ Vider l'historique** avec confirmation
- Vider l'historique ne touche pas au stock

### 🔧 Serveur de production
- Remplacement du serveur de développement Flask par **Waitress**
- Démarrage propre, sans warning, avec fallback automatique si Waitress absent

---

## v1.x — Historique complet

<details>
<summary>Voir l'historique des versions 1.x</summary>

## v1.0 — Base de l'application
- Architecture **Flask + SQLite + MVC**
- Tableau paginé, recherche, tri multi-colonnes
- Import CSV LCSC (format export commande)
- Ajout / édition / suppression de composants
- Fiche détail complète — thème sombre

## v1.1 — Enrichissement LCSC
- Service `lcsc_scraper.py` : scraping `wmsc.lcsc.com`
- Récupération automatique catégorie, image, datasheet
- Thread daemon avec pause ~0.6s entre requêtes

## v1.2 — Déduplication et pagination
- Déduplication à l'import par référence LCSC (UNIQUE en base)
- Pagination (25 / 50 / 100 par page)

## v1.3 — Ajout rapide depuis LCSC
- Bloc "⚡ Import rapide LCSC" : saisie ref → prévisualisation → pré-remplissage

## v1.4 — Projets et alertes stock
- CRUD projets avec image bannière
- Vérification disponibilité en temps réel, boutons Débiter / Restituer (AJAX)
- Champ `min_stock`, page 🔔 Alertes + bandeau rouge

## v1.5 — Catégories hiérarchiques
- Filtre avec `<optgroup>` par sous-catégorie, macro Jinja réutilisable

## v1.6 — Import BOM KiCad
- Upload CSV KiCad → rapport ✅/⚠️/❌
- Formats : KiCad 7/8, plugin JLCPCB, bom2csv

## v1.7 — Images de projets
- Upload + prévisualisation, cartes projet avec bannière

## v1.8 — Étiquettes imprimables + QR code
- Route `/labels?ids=1,2,3` : impression multi-étiquettes
- QR code généré en Python pur (`qr_generator.py`), zéro CDN externe
- Multi-sélection dans le tableau + barre flottante

## v1.9 — Symbole & Footprint EasyEDA
- Téléchargement PNG symbole + footprint, cache dans `instance/easyeda_pngs/`
- Galerie sur la fiche détail, lightbox unifiée

## v1.10 — Support export panier LCSC
- Import CSV format `export_cart_*.csv` détecté automatiquement

## v1.11 — Refonte page projet
- Tableau unique, barre de stats compacte, formulaire rétractable

## v1.12 — Configuration des étiquettes
- Page `/label-settings` avec aperçu en temps réel
- Format, couleurs, tailles de police, 11 toggles on/off

## v1.13 — Paramètres enrichis
- Nom de l'application, sauvegarde ZIP, stats base, enrichissement en masse

## v1.14 à v1.21 — Corrections et ajouts divers
- Mode ajout en série, catégories personnalisées, upload d'image manuelle
- Téléchargement EasyEDA en masse + réconciliation, nettoyages CSS

</details>
