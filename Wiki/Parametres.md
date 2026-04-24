# ⚙️ Paramètres

Accès : icône engrenage dans la navbar, ou `/settings`.

## Application (Général)

| Paramètre | Description | Défaut |
|-----------|-------------|--------|
| Nom de l'application | Affiché dans la navbar et l'onglet du navigateur | `StockEleK` |
| Adresse de base | URL complète pour les QR codes (ex: `http://192.168.1.50:5000`) | Auto-détectée |
| Langue | Français / English | `fr` |
| Seuil d'alerte par défaut | Quantité minimum appliquée aux nouveaux composants importés | `4` |

## Sauvegarde & Export

### Sauvegarder la base de données
Télécharge une copie de `instance/stock.db`. À faire régulièrement !

### Exporter le stock en CSV
Export de tous les composants au format CSV UTF-8.

### Restaurer
Upload d'un fichier `.db` de sauvegarde. ⚠️ **Remplace toutes les données actuelles**.

### Reset complet
Efface toutes les données (composants, projets, settings, mouvements). Nécessite de taper `RESET` pour confirmer. À n'utiliser qu'en phase de test.

## LCSC & EasyEDA

Aucune clé API requise. L'enrichissement LCSC/EasyEDA est gratuit.

Section informative uniquement.

## Mouser

| Paramètre | Description |
|-----------|-------------|
| Clé API Mouser | Obtenue sur mouser.fr dans les paramètres du compte |

Bouton **Tester la connexion** pour valider la clé.

## DigiKey

| Paramètre | Description |
|-----------|-------------|
| Client ID | Obtenu sur developer.digikey.com |
| Client Secret | Obtenu sur developer.digikey.com |

Bouton **Tester la connexion** pour valider les credentials.

## ESP32 — LEDs adressables

| Paramètre | Description | Exemple |
|-----------|-------------|---------|
| URL de l'ESP32 | Adresse IP complète | `http://192.168.1.46` |
| Token d'authentification | Clé secrète partagée avec le firmware | `mon-token-secret` |
| Couleur par défaut | Couleur LED si la catégorie n'est pas reconnue | `#38bdf8` |
| Durée d'allumage | Secondes avant extinction automatique | `5` |
| Décalages plateaux | Offset LED pour chaque plateau (séparés par virgules) | `0,30,60` |

### Couleurs par catégorie de composant

Personnaliser la couleur LED pour chaque famille :
- Résistances, Condensateurs, Inductances
- Transistors, Diodes, LEDs, Optique
- Amplificateurs, ICs, Connecteurs
- Switches, Cristaux, Fusibles
- Capteurs, Alimentation, Relais, RF, Moteurs

### Test de connexion
Bouton **Ping ESP32** → vérifie la connexion et affiche le type de device détecté (S3 ou P4).
Bouton **Test LED** → allume toutes les LEDs pendant 2 secondes.

## Base de données — Statistiques

Affiche :
- Nombre de composants, projets, mouvements, catégories
- Valeur totale du stock
- Taille de la base de données

## Base de données — Maintenance

### Optimiser la base
Lance `VACUUM` et `ANALYZE` sur SQLite — compacte la base et met à jour les statistiques d'index. Recommandé après une suppression massive.

### Ré-enrichir tous les composants
Lance l'enrichissement LCSC en arrière-plan pour tous les composants avec référence LCSC et données manquantes (image ou catégorie absente).

## KiCad Library

Voir la page [Intégration KiCad](KiCad) pour le détail complet.

| Paramètre | Description |
|-----------|-------------|
| Dossier KiCad | Chemin vers vos librairies KiCad personnelles |
| Préfixe | Préfixe des fichiers générés (ex: `StockEleK`) |

Statistiques affichées :
- Nombre de symboles, footprints, modèles 3D générés
- Nombre de composants LCSC sans fichiers KiCad (avec lien pour générer)

## Étiquettes — Configuration

Voir la page [Étiquettes](Etiquettes) pour le détail complet.

## Développement — Debug Toolbar

| Paramètre | Description |
|-----------|-------------|
| Activer la debug toolbar | Affiche la toolbar de débogage en bas de chaque page HTML |

> ⚠️ La toolbar expose les requêtes SQL et les variables de session. Ne jamais activer sur un serveur accessible publiquement.

Voir la page [Debug Toolbar](Debug-Toolbar) pour le détail.
