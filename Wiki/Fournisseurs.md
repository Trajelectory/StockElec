# 🔌 Intégrations Fournisseurs

## LCSC & EasyEDA

LCSC est le fournisseur principal supporté. L'enrichissement est **gratuit et sans clé API**.

### Ce qui est récupéré

- Description, description longue
- Package / boîtier
- Fabricant et référence fabricant (MPN)
- Prix unitaire
- Statut RoHS
- Image du composant
- URL datasheet
- Catégorie et sous-catégorie LCSC
- Symbole schématique (PNG depuis EasyEDA)
- Footprint PCB (PNG depuis EasyEDA)

### Configuration

Aucune configuration nécessaire. L'enrichissement LCSC fonctionne par défaut.

### Prévisualisation

Avant d'ajouter un composant, entrer une référence LCSC et cliquer **Aperçu LCSC** pour voir les données sans enregistrer.

---

## Mouser

### Obtenir une clé API

1. Créer un compte sur [mouser.fr](https://www.mouser.fr)
2. Aller dans **Mon compte → Clés API**
3. Créer une clé avec les droits de recherche

### Configuration dans StockEleK

**Paramètres → Mouser** → renseigner la **clé API Mouser**

### Ce qui est récupéré

- Description
- Fabricant / MPN
- Prix (pricing échelonné)
- Stock disponible chez Mouser
- URL produit

---

## DigiKey

### Obtenir les credentials OAuth2

1. Aller sur [developer.digikey.com](https://developer.digikey.com)
2. Créer une application avec l'API **Product Information**
3. Récupérer le **Client ID** et le **Client Secret**

### Configuration dans StockEleK

**Paramètres → DigiKey** → renseigner le **Client ID** et le **Client Secret**

### Ce qui est récupéré

- Description
- Fabricant / MPN
- Prix
- Stock disponible chez DigiKey
- URL produit

---

## Vérification des clés API

Depuis **Paramètres → Mouser / DigiKey**, le bouton **Tester la connexion** vérifie que les identifiants fonctionnent correctement.

---

## Flux d'enrichissement

Quand un composant est créé ou mis à jour :

```
1. LCSC scraper          → description, image, catégorie, prix
2. EasyEDA scraper       → symbole PNG, footprint PNG
3. Mouser scraper        → données complémentaires (si clé configurée)
4. DigiKey scraper       → données complémentaires (si clé configurée)
```

Chaque scraper tourne dans un **thread séparé** pour ne pas bloquer l'interface. Les données sont appliquées au fur et à mesure qu'elles arrivent.

### Politique de mise à jour

L'enrichissement **ne remplace jamais** les champs déjà renseignés manuellement, sauf si l'option "forcer la mise à jour" est activée (ré-enrichissement explicite depuis la fiche).

## Vérification de prix en temps réel

Sur la fiche d'un composant LCSC, le bouton **Vérifier le prix** interroge LCSC en temps réel pour obtenir le prix actuel (utile si le prix a changé depuis l'enrichissement initial).
