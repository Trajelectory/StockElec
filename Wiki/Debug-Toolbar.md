# 🛠️ Debug Toolbar

## Présentation

La debug toolbar est un outil de débogage intégré à StockEleK, inspiré de CakePHP DebugKit. Elle s'affiche sous forme d'une barre fixe en bas de chaque page HTML quand elle est activée.

## Activation

1. **Paramètres → Développement → Debug Toolbar**
2. Cocher **Activer la debug toolbar**
3. Cliquer **Enregistrer**

La toolbar apparaît immédiatement sur toutes les pages HTML. Pour la désactiver, décocher et enregistrer.

## Interface

### Barre principale

Toujours visible en bas de page (hauteur 32px) :

```
⚡ Debug  |  🗃 SQL (12)  |  📋 Logs (3)  |  🌐 Requête  |  ... 245ms  12 SQL / 18.3ms  GET /stock  ×
```

| Élément | Description |
|---------|-------------|
| **⚡ Debug** | Logo de la toolbar |
| **🗃 SQL (N)** | Nombre de requêtes SQL — orange si requête lente détectée |
| **📋 Logs (N)** | Nombre de messages de log — rouge si warning/error |
| **🌐 Requête** | Informations sur la requête HTTP courante |
| **Temps** | Durée totale de la page (vert < 200ms, orange < 500ms, rouge > 500ms) |
| **SQL total** | Nombre et durée cumulée des requêtes SQL |
| **Méthode + route** | Ex: `GET /stock` |
| **×** | Fermer la toolbar (jusqu'au prochain rechargement) |

Cliquer sur un onglet l'ouvre/ferme (toggle).

### Onglet SQL

Tableau de toutes les requêtes SQLite exécutées pendant la requête HTTP :

| Colonne | Description |
|---------|-------------|
| Durée | Temps d'exécution en ms |
| Requête | SQL complet + paramètres |

Le badge **SLOW** (fond rouge) apparaît sur les requêtes > 50ms.

### Onglet Logs

Tous les messages de log Python (`logger.info`, `logger.warning`, `logger.error`...) émis pendant la requête :

- 🔵 **DEBUG** — messages de débogage
- 🔵 **INFO** — informations normales
- 🟡 **WARNING** — avertissements
- 🔴 **ERROR** — erreurs
- 🔴 **CRITICAL** — erreurs critiques

### Onglet Requête

4 colonnes d'informations sur la requête HTTP courante :

| Colonne | Contenu |
|---------|---------|
| **Méthode / Route** | Méthode HTTP, chemin, IP client |
| **Query Params** | Paramètres GET (ex: `?search=ESP32&page=2`) |
| **Form Data** | Données POST soumises par un formulaire |
| **Headers** | Headers HTTP utiles (Content-Type, User-Agent, Referer...) |

La session Flask (si elle contient des données) est affichée sous les 4 colonnes.

## Ce que la toolbar ne capture pas

- Les requêtes AJAX/fetch faites par le navigateur (utiliser F12 → Réseau pour ça)
- Les requêtes WebSocket
- Les requêtes vers des services externes (LCSC, Mouser...) qui tournent dans des threads séparés

Pour ces cas, utiliser la **DevTools du navigateur** (F12 → Réseau / Console).

## Performances

La toolbar a un impact minimal sur les performances :
- Le wrapper SQLite ajoute ~0.1ms par requête
- Le handler de log est thread-safe
- La toolbar n'est **jamais** injectée sur les routes `/api/*`, `/kicad/*`, `/static/*` ou les images

## Sécurité

⚠️ La toolbar expose des informations sensibles :
- Structure complète des requêtes SQL (révèle le schéma de la base)
- Contenu des formulaires POST (peut inclure des mots de passe ou tokens)
- Variables de session

**Ne jamais activer la debug toolbar sur un serveur accessible publiquement.**
