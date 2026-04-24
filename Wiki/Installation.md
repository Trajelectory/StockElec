# 🚀 Installation & Démarrage

## Prérequis

- **Python 3.11+**
- **pip**
- Windows, Linux ou macOS

## Installation

```bash
# 1. Cloner le dépôt
git clone https://github.com/TON_USER/StockEleK.git
cd StockEleK

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. Lancer l'application
python run.py
```

L'application démarre sur **http://localhost:5000**.

## Premier démarrage

Au premier lancement, StockEleK :
- Crée automatiquement la base de données SQLite dans `instance/stock.db`
- Génère une `SECRET_KEY` aléatoire dans `instance/secret_key`
- Applique toutes les migrations de schéma

Aucune configuration manuelle n'est nécessaire pour commencer.

## Structure des fichiers

```
StockEleK/
├── run.py                  # Point d'entrée
├── requirements.txt
├── app/
│   ├── __init__.py         # Création de l'app Flask
│   ├── controllers/        # Routes Flask
│   ├── models/             # Accès base de données
│   ├── services/           # Logique métier (scrapers, KiCad...)
│   ├── templates/          # Templates Jinja2
│   └── static/             # CSS, JS, images statiques
└── instance/               # Données (créé automatiquement)
    ├── stock.db            # Base de données SQLite
    ├── images/             # Photos des composants
    ├── project_images/     # Images des projets
    ├── kicad/              # Fichiers KiCad générés
    └── secret_key          # Clé de session Flask
```

## Accès depuis le réseau local

Pour accéder depuis un téléphone ou une autre machine sur le réseau (utile avec l'ESP32) :

1. Aller dans **Paramètres → Application**
2. Renseigner l'**Adresse de base** : `http://192.168.1.XX:5000` (l'IP de votre machine)

Cette adresse est utilisée pour générer les QR codes des étiquettes.

## Mise à jour

```bash
git pull
pip install -r requirements.txt --upgrade
python run.py
```

Les migrations de schéma sont appliquées automatiquement au démarrage.

## Variables d'environnement

| Variable | Description | Défaut |
|----------|-------------|--------|
| `SECRET_KEY` | Clé secrète Flask | Générée automatiquement dans `instance/` |
| `PORT` | Port d'écoute | `5000` |

## Mode production

Pour un déploiement plus robuste (Tailscale, réseau local permanent) :

```bash
# Avec waitress (déjà inclus)
python run.py

# Ou avec gunicorn (Linux)
gunicorn -w 2 -b 0.0.0.0:5000 "app:create_app()"
```

> ⚠️ StockEleK est conçu pour un usage local/personnel. Ne pas exposer directement sur Internet sans reverse proxy et authentification.
