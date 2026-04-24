# 📐 Rangement Gridfinity

## Présentation

La page Rangement (`/rangement`) affiche un plan visuel de vos tiroirs de stockage Gridfinity et permet d'assigner chaque case à un composant. Couplé à l'ESP32-S3, la LED de la bonne case s'allume quand vous cherchez un composant.

## Configuration des plateaux

### Ajouter un plateau

Un **plateau** représente un tiroir ou une étagère physique. Configuration :
- **Identifiant** : lettre unique (A, B, C...)
- **Label** : nom affiché (ex: "Résistances", "Plateau du haut")
- **Colonnes** : nombre de cases en largeur
- **Lignes** : nombre de cases en hauteur

### Taille des cases

Chaque case peut avoir une taille différente (pour les grands composants qui occupent 2 ou 4 unités Gridfinity). Cliquer sur une case pour modifier sa taille :
- 1×1 (standard)
- 1×2, 2×1 (rectangle)
- 2×2 (carré double)

## Assigner un composant à une case

1. Cliquer sur une case du plan
2. Rechercher un composant (recherche par description, LCSC, MPN)
3. Valider — la case affiche le nom et la miniature du composant

L'assignation est automatiquement synchronisée avec le champ **Emplacement** de la fiche composant (ex: `A7` = plateau A, case 7).

## Allumer les LEDs depuis le plan

Depuis la page Rangement, cliquer sur une case assignée → les LEDs WS2812B de cette case s'allument (si l'ESP32 est configuré et connecté).

## Depuis une fiche composant

Sur chaque fiche composant, le bouton **🔦 Trouver** (ou l'icône LED) allume automatiquement la case correspondante dans le rangement.

## Depuis la page Stock

Dans la liste du stock, cliquer sur l'emplacement d'un composant allume sa LED.

---

# 🔌 Hardware ESP32-S3

## Matériel nécessaire

- **ESP32-S3** (recommandé : ESP32-S3-DevKitC)
- **LEDs WS2812B** — rubans ou matrices NeoPixel
- **Afficheur HT16K33** (optionnel) — afficheur 7 segments ou matrice LED I²C
- Alimentation 5V adaptée (compter ~60mA par LED en blanc pleine puissance)

## Firmware

Le firmware Arduino est dans le dossier `firmware/ESP32-S3/` du dépôt.

### Dépendances Arduino

```
Adafruit NeoPixel
Adafruit GFX Library
Adafruit HT16K33
WiFi (inclus ESP32)
ArduinoJson
```

### Configuration du firmware (`config.h`)

```cpp
// WiFi
#define WIFI_SSID     "VotreSSID"
#define WIFI_PASSWORD "VotreMotDePasse"

// Sécurité — doit correspondre au token dans StockEleK Paramètres > ESP32
#define API_TOKEN     "votre-token-secret"

// LEDs WS2812B
#define LED_PIN       5       // GPIO connecté au DATA des LEDs
#define LED_COUNT     100     // Nombre total de LEDs

// HT16K33 (optionnel)
#define HT16K33_SDA   8       // GPIO SDA
#define HT16K33_SCL   9       // GPIO SCL

// Disposition des plateaux
// Chaque plateau = { id, premiere_led, derniere_led, cols, rows }
```

### Endpoints HTTP exposés par le firmware

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/ping` | GET | Health check, retourne `{"ok": true, "display": false, "leds": 100, "uptime": 42}` |
| `/leds` | POST | Allumer des LEDs spécifiques |
| `/off` | POST | Éteindre toutes les LEDs |
| `/test` | POST | Afficher "TEST" sur l'afficheur HT16K33 |

### Format du payload `/leds`

```json
{
  "leds": [6, 7, 16, 17],
  "color": "#38bdf8",
  "duration": 5,
  "cell": "A7",
  "drawer": 0
}
```

### Connexion matérielle

```
ESP32-S3         WS2812B
GPIO 5    ──►   DATA IN
GND       ──►   GND
5V        ──►   5V (alimentation externe recommandée)

ESP32-S3         HT16K33
GPIO 8    ──►   SDA
GPIO 9    ──►   SCL
3.3V      ──►   VCC
GND       ──►   GND
```

## Configuration dans StockEleK

Aller dans **Paramètres → ESP32 — LEDs adressables** :

| Paramètre | Description | Exemple |
|-----------|-------------|---------|
| URL de l'ESP32 | Adresse IP de l'ESP32 sur le réseau | `http://192.168.1.46` |
| Token d'authentification | Doit correspondre à `API_TOKEN` dans le firmware | `mon-token-secret` |
| Couleur par défaut | Couleur des LEDs si pas de catégorie | `#38bdf8` |
| Durée | Temps d'allumage en secondes | `5` |
| Décalages | Offset LED par plateau (si plusieurs plateaux sur le même ruban) | `0,30,60` |

### Couleurs par catégorie

Chaque famille de composants peut avoir sa propre couleur LED :
- Résistances : rouge
- Condensateurs : bleu
- LEDs/Optique : jaune
- ICs : violet
- Connecteurs : vert
- etc.

## Détection automatique S3 / P4

StockEleK détecte automatiquement si l'ESP32 connecté est un S3 ou un P4 en interrogeant `/ping` :
- `"display": false` → **S3** → utilise l'endpoint `/leds`
- `"display": true` → **P4** → utilise l'endpoint `/led`

Si le premier endpoint répond 404, StockEleK bascule automatiquement sur l'autre et met à jour le cache pour les requêtes suivantes.

## LED de test

Depuis **Paramètres → ESP32**, le bouton **Test LED** allume toutes les LEDs pendant 2 secondes pour vérifier la connexion.
