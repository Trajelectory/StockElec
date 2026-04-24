# 🔌 API REST

StockEleK expose une API REST JSON utilisée en interne par le frontend et accessible pour des intégrations externes (ESP32, scripts, autres outils).

## Authentification

Les endpoints `/component/<id>/json` et `/component/<id>/image` nécessitent un **token Bearer** :

```
Authorization: Bearer votre-token-secret
```

Configurer le token dans **Paramètres → ESP32 → Token d'authentification**.

Les autres endpoints `/api/*` ne nécessitent pas d'authentification (accès réseau local uniquement).

---

## Composants

### `GET /api/components`

Recherche de composants.

**Paramètres** :
| Param | Type | Description |
|-------|------|-------------|
| `search` | string | Recherche dans description, LCSC, MPN, fabricant, package |
| `limit` | int | Nombre max de résultats (défaut : tous) |

**Réponse** :
```json
[
  {
    "id": 42,
    "description": "Résistance 100Ω 0402 1%",
    "lcsc_part_number": "C25076",
    "mouser_part_number": "",
    "digikey_part_number": "",
    "manufacture_part_number": "RC0402FR-07100RL",
    "manufacturer": "Yageo",
    "package": "0402",
    "quantity": 1000,
    "min_stock": 100,
    "unit_price": 0.0012,
    "location": "A3",
    "category": "Resistors",
    "image_path": "images/42.jpg"
  }
]
```

---

### `GET /component/<id>/json`

Fiche complète d'un composant (pour l'ESP32-P4).

**Auth requise** : ✅

**Réponse** :
```json
{
  "ok": true,
  "id": 42,
  "description": "ESP32-S3-WROOM-1-N8R2",
  "manufacturer": "Espressif",
  "lcsc_part_number": "C2913204",
  "manufacture_part_number": "ESP32-S3-WROOM-1-N8R2",
  "mouser_part_number": "356-ESP32-S3WRM1N8R2",
  "digikey_part_number": "",
  "package": "SMD 25.5×18mm",
  "location": "A7",
  "category": "RF Transceiver Modules",
  "quantity": 12,
  "min_stock": 2,
  "unit_price": 4.8831,
  "rohs": "ROHS",
  "datasheet_url": "https://...",
  "image_url": "/component/42/image",
  "kicad_sym": true,
  "kicad_fp": true,
  "kicad_3d": false
}
```

---

### `GET /component/<id>/image`

Image d'un composant (JPEG ou PNG).

**Auth requise** : ✅

Retourne l'image directement (Content-Type: image/jpeg ou image/png).

---

### `POST /component/<id>/adjust`

Ajuster la quantité en stock.

**Body JSON** :
```json
{
  "delta": -5,
  "note": "Utilisé pour prototype v2",
  "project_id": 3
}
```

**Réponse** :
```json
{"ok": true, "new_quantity": 7}
```

---

## Recherche globale

### `GET /api/search`

Recherche dans composants ET projets simultanément.

**Paramètres** :
| Param | Type | Description |
|-------|------|-------------|
| `q` | string | Terme de recherche (min 2 caractères) |

**Réponse** :
```json
{
  "components": [
    {
      "id": 42,
      "description": "ESP32-S3-WROOM-1-N8R2",
      "ref": "C2913204",
      "package": "SMD 25.5×18mm",
      "quantity": 12,
      "image_path": "images/42.jpg",
      "category": "RF Transceiver Modules"
    }
  ],
  "projects": [
    {
      "id": 3,
      "name": "StockElec Controller",
      "status": "design",
      "image_path": null
    }
  ]
}
```

---

## LEDs ESP32

### `POST /api/led/<cell_id>/on`

Allumer les LEDs d'une case.

**Paramètres URL** : `cell_id` — identifiant de la case (ex: `A7`, `B3`)

**Body JSON** :
```json
{"component_id": 42}
```

**Réponse** :
```json
{"ok": true, "leds": [6, 7, 16, 17], "queued": false, "endpoint": "/leds"}
```

---

### `POST /api/led/off`

Éteindre toutes les LEDs.

**Réponse** :
```json
{"ok": true}
```

---

### `GET /api/led/ping`

Vérifier la connexion avec l'ESP32.

**Réponse** :
```json
{
  "ok": true,
  "device": "S3",
  "leds": 100,
  "display": false,
  "ip": "http://192.168.1.46"
}
```

---

### `POST /api/led/test`

Allumer toutes les LEDs en blanc pendant 2 secondes (test).

---

## Prix

### `GET /api/price-check/<lcsc_ref>`

Vérifie le prix actuel d'un composant LCSC.

**Réponse** :
```json
{
  "ok": true,
  "lcsc_ref": "C2913204",
  "price": 4.8831,
  "currency": "EUR",
  "source": "lcsc"
}
```

---

## Santé

### `GET /api/health`

Health check de l'application.

**Réponse** :
```json
{
  "ok": true,
  "version": "2.0",
  "db": "ok",
  "components": 193,
  "uptime_s": 3600
}
```

---

## KiCad

### `GET /kicad/missing-count`

Nombre de composants LCSC sans fichiers KiCad générés.

**Réponse** :
```json
{
  "total": 150,
  "done": 120,
  "missing": 30,
  "pct": 80
}
```

---

## Codes d'erreur

| Code | Signification |
|------|--------------|
| `200` | Succès |
| `202` | Accepté (traitement en cours, ex: enrichissement) |
| `400` | Paramètre manquant ou invalide |
| `401` | Token manquant ou invalide |
| `404` | Ressource introuvable |
| `502` | ESP32 injoignable ou erreur HTTP |
| `503` | Erreur réseau (ESP32 hors ligne) |
