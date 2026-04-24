# 🖥️ Hardware ESP32

## Architecture

Le système hardware se compose de deux appareils distincts :

| Appareil | Rôle |
|----------|------|
| **ESP32-S3** | WiFi + LEDs WS2812B + afficheur HT16K33 (en production) |
| **ESP32-P4 GUITION JC4880P443** | Écran tactile 4.3" 800×480 (à venir) |

---

## ESP32-S3 — En production ✅

Voir la page [Rangement Gridfinity](Rangement) pour le détail du firmware S3 et du câblage.

### Résumé

- Reçoit les commandes de StockEleK via HTTP
- Allume les LEDs WS2812B de la case correspondante
- Affiche des messages sur l'afficheur HT16K33 (7 segments ou matrice)
- Répond à `/ping` avec `{"display": false}` pour être détecté comme S3

---

## ESP32-P4 GUITION JC4880P443 — En cours 🚧

### Matériel

Le **GUITION JC4880P443** est un module tout-en-un comprenant :
- **ESP32-P4** (RISC-V, processeur principal, gère l'écran)
- **ESP32-C6** (gère le WiFi 6, Bluetooth 5, les GPIO)
- Écran tactile **4.3" IPS 800×480** (ST7701 + GT911)
- Caméra 2MP
- Boîtier avec coque

Les deux puces communiquent via **UART** (RS232 sur le connecteur JP1).

### Interface prévue

L'écran affichera la fiche complète d'un composant quand StockEleK allume une LED :

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ ⚡ StockEleK                                    ESP32-S3-WROOM-1-N8R2       │
├────────────────┬─────────────────────────────────────┬──────────────────────┤
│  [Photo]       │ 2.4GHz Wi-Fi 802.11b/g/n + BT5 LE  │   Emplacement        │
│                │ Flash: 8MB  PSRAM: 2MB               │  ┌─────────────┐    │
│  [Symbole][FP] │ Package: SMD 25.5×18mm               │  │     A7      │    │
│                │─────────────────────────────────────  │  └─────────────┘    │
│  Fournisseurs  │ Fréquence    2.4 GHz                 │   Tiroir A · Case 7 │
│  LCSC: C2913   │ Alimentation 3 ~ 3.6V                │  ● LED active       │
│                │ Bluetooth    5.0 LE                   │──────────────────── │
│                │─────────────────────────────────────  │   Stock             │
│                │ Prix: 4.88 €    Valeur: 58.60 €      │  [−] [12] [+]       │
│                │                                       │  [Confirmer]        │
├────────────────┴─────────────────────────────────────┴──────────────────────┤
│ IoT › RF Transceiver Modules                                    StockEleK   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Endpoints StockEleK pour le P4

StockEleK expose déjà les endpoints nécessaires :

| Endpoint | Description |
|----------|-------------|
| `GET /component/<id>/json` | Fiche complète en JSON (description, refs, stock, KiCad...) |
| `GET /component/<id>/image` | Image du composant (JPEG/PNG) |
| `POST /api/led/<cell>/on` | Allumer les LEDs (retourne aussi les infos composant) |

Ces endpoints sont protégés par le **token d'authentification** ESP32.

### Firmware P4 (LVGL v9)

Le firmware est en cours de développement avec :
- **LVGL v9** pour l'interface graphique
- Drivers **ST7701** (écran MIPI DSI) et **GT911** (tactile I²C)
- Communication UART P4↔C6 pour les commandes LEDs

> ⏳ En attente de réception du hardware pour les tests finaux.

### Détection automatique dans StockEleK

Quand le P4 sera connecté, son firmware répondra à `/ping` avec `"display": true`. StockEleK basculera automatiquement sur l'endpoint `/led` (au lieu de `/leds` pour le S3).

---

## Sécurité

Tous les endpoints ESP32 sont protégés par un **token Bearer** :

```
Authorization: Bearer votre-token-secret
```

Le token est configuré dans **Paramètres → ESP32** et doit être identique dans le firmware.

## Dépannage

### L'ESP32 ne répond pas
1. Vérifier que l'ESP32 est sur le même réseau WiFi
2. Pinguer l'IP depuis votre machine : `ping 192.168.1.46`
3. Vérifier l'URL dans les paramètres (sans slash final, avec le port si non-standard)

### Les LEDs ne s'allument pas
1. Depuis **Paramètres → ESP32**, cliquer **Test LED**
2. Vérifier le câblage DATA → GPIO 5 (ou le GPIO configuré dans le firmware)
3. Vérifier l'alimentation 5V (les LEDs consomment beaucoup)

### 404 sur l'endpoint
StockEleK gère automatiquement le fallback : si `/led` répond 404, il essaie `/leds` et vice-versa. Le log affiche `🔄 Endpoint réel ≠ hint ping — cache mis à jour`.
