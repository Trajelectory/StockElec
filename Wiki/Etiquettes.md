# 🏷️ Étiquettes

## Présentation

StockEleK génère des étiquettes imprimables pour vos composants, avec QR code pointant vers la fiche web du composant.

## Accéder aux étiquettes (`/labels`)

Depuis la page Stock, cocher les composants souhaités et cliquer **Imprimer les étiquettes**, ou aller directement sur `/labels`.

## Configuration des étiquettes (`/label-settings`)

### Mise en page

| Paramètre | Description |
|-----------|-------------|
| Largeur / Hauteur | Dimensions de l'étiquette en mm |
| Colonnes / Lignes | Nombre d'étiquettes par feuille |
| Marges | Marges de la feuille (haut, bas, gauche, droite) |
| Espacement | Espace entre étiquettes |

### Contenu affiché

Choisir quels champs afficher sur l'étiquette :
- ✅ **Description** (recommandé)
- ✅ **Référence LCSC** (recommandé)
- ☐ Référence Mouser
- ☐ Référence DigiKey
- ✅ **Package**
- ☐ Fabricant / MPN
- ✅ **QR Code** (lien vers la fiche)
- ☐ Image du composant
- ☐ Symbole EasyEDA
- ☐ Footprint EasyEDA
- ☐ Quantité en stock
- ☐ Prix unitaire
- ☐ Emplacement (case Gridfinity)

### Aperçu en temps réel

La page de configuration affiche un aperçu visuel de l'étiquette mis à jour en temps réel.

## Impression

1. Configurer la mise en page
2. Sélectionner les composants à étiqueter
3. Cliquer **Aperçu / Imprimer**
4. Dans la boîte de dialogue d'impression du navigateur, désactiver les marges et l'en-tête/pied de page

> 💡 Pour les étiquettes Dymo ou Brother, ajuster les dimensions aux dimensions de votre rouleau d'étiquettes.

## QR Code

Chaque étiquette contient un QR code encodant l'URL complète de la fiche composant (ex: `http://192.168.1.50:5000/component/42`). Scanner ce QR code depuis un téléphone ouvre directement la fiche.

> ⚠️ Pour que les QR codes fonctionnent depuis votre téléphone, renseigner l'**Adresse de base** dans Paramètres → Application avec l'IP de votre machine sur le réseau local.
