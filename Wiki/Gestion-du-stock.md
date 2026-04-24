# 📦 Gestion du Stock

## Vue d'ensemble

La page stock (`/stock`) est le cœur de l'application. Elle affiche tous vos composants avec filtres, recherche et actions rapides.

## Recherche et filtres

La barre de recherche en haut filtre en temps réel sur :
- Description / valeur
- Référence LCSC / Mouser / DigiKey
- Référence fabricant (MPN)
- Fabricant
- Package

### Filtres disponibles
- **Catégorie** — filtre par famille LCSC (résistances, condensateurs, ICs...)
- **Stock bas** — affiche uniquement les composants sous leur seuil d'alerte
- **Sans image** — composants non encore enrichis

## Ajouter un composant

### Via l'interface (`/add`)

Remplir le formulaire avec :
- **Références fournisseurs** : LCSC, Mouser, DigiKey (au moins une)
- **Référence fabricant (MPN)** et fabricant
- **Package** (ex: 0402, SOT-23, DIP-8...)
- **Quantité** et **seuil d'alerte minimum**
- **Description** courte et longue
- **Prix unitaire**
- **Emplacement** (ex: A7, B3...) — case dans le rangement Gridfinity
- **Catégorie**
- **Notes**
- **Caractéristiques techniques** — tableau nom/valeur (ex: Voltage Rating: 12V, Package: SOT-23...)
- **Image** — photo du composant (upload manuel ou récupérée automatiquement)

> 💡 Si vous renseignez une référence LCSC, cliquez **Aperçu LCSC** pour prévisualiser les données avant d'enregistrer.

### Via import CSV (`/import`)

1. Aller dans **Stock → Importer**
2. Choisir un fichier CSV
3. **Prévisualisation** — StockEleK analyse le CSV et affiche :
   - Les composants **nouveaux** (avec checkbox pour sélectionner lesquels importer)
   - Les composants **déjà en stock** (doublons détectés par ref LCSC/Mouser/DigiKey)
   - Les lignes **ignorées** (sans référence fournisseur)
4. Cocher/décocher les lignes souhaitées
5. Cliquer **Importer X composants**

#### Format CSV supporté

StockEleK détecte automatiquement les colonnes suivantes (insensible à la casse) :

| Colonne | Noms reconnus |
|---------|--------------|
| LCSC | `LCSC Part Number`, `LCSC#`, `LCSC` |
| Mouser | `Mouser`, `Mouser Part Number` |
| DigiKey | `DigiKey`, `Digi-Key`, `DigiKey Part Number` |
| Quantité | `Quantity`, `Qty`, `Quantité` |
| Description | `Description`, `Value`, `Comment` |
| Package | `Package` |
| Prix | `Unit Price(€)`, `Unit Price` |
| Fabricant | `Manufacturer` |
| MPN | `Manufacture Part Number`, `MPN` |
| Emplacement | `Location`, `Emplacement` |
| Min stock | `Min_Stock`, `Min Stock`, `Seuil alerte` |

> 💡 Compatible avec les exports CSV de LCSC, Mouser, DigiKey et JLCPCB.

## Modifier un composant (`/component/<id>/edit`)

Toutes les données sont modifiables. L'emplacement et les caractéristiques techniques sont également éditables.

## Ajuster le stock

Depuis la fiche d'un composant, utiliser les boutons **+** et **−** pour ajuster la quantité. Chaque mouvement est enregistré dans l'historique avec date, type (entrée/sortie) et note optionnelle.

## Historique des mouvements (`/history`)

L'historique global affiche tous les mouvements de stock :
- **Entrées** (réceptions de commandes, ajouts manuels)
- **Sorties** (utilisation en projet, pertes)
- **Ajustements** (corrections d'inventaire)

Filtrable par composant et par date.

## Alertes stock (`/alerts`)

Les composants dont la quantité est inférieure ou égale au seuil minimum apparaissent dans les alertes. Accessible depuis :
- Le dashboard home (badge rouge)
- La navbar (cloche)
- `/alerts`

## Réapprovisionnement (`/reorder`)

Page dédiée listant tous les composants sous leur seuil, avec :
- Quantité actuelle vs seuil minimum
- Référence LCSC/Mouser/DigiKey pour commander rapidement
- Export CSV de la liste de réapprovisionnement

## Enrichissement automatique

Quand un composant est ajouté avec une référence LCSC, StockEleK lance automatiquement en arrière-plan :
1. **Scraping LCSC/EasyEDA** — description, package, image, datasheet, prix, catégorie, symbole/footprint PNG
2. **Mouser** (si clé API configurée) — données complémentaires
3. **DigiKey** (si clé API configurée) — données complémentaires

L'enrichissement peut aussi être déclenché manuellement depuis la fiche composant.

## Export CSV (`/export/csv`)

Exporte tous les composants du stock au format CSV UTF-8 avec BOM (compatible Excel).
