# ⚙️ Intégration KiCad

## Présentation

StockEleK génère automatiquement les fichiers KiCad pour tous vos composants LCSC, via la bibliothèque [JLC2KiCadLib](https://github.com/TousstNicolas/JLC2KiCad_lib). Les symboles, footprints et modèles 3D sont téléchargés depuis EasyEDA et convertis au format KiCad.

## Prérequis

```bash
pip install JLC2KiCadLib
```

JLC2KiCadLib doit être accessible dans le PATH Python.

## Configuration

Dans **Paramètres → KiCad Library** :

| Paramètre | Description |
|-----------|-------------|
| Dossier KiCad | Chemin vers votre dossier de librairies KiCad perso (ex: `C:\Users\vous\KiCad\libs`) |
| Préfixe des librairies | Préfixe ajouté aux noms de fichiers (ex: `StockEleK` → `StockEleK_Resistors.kicad_sym`) |

## Génération des fichiers

### Génération globale

**Paramètres → KiCad Library → Générer toutes les librairies**

Lance la génération pour tous les composants LCSC du stock qui ont un `category_id` (composants enrichis depuis LCSC). Les composants sans catégorie (mécaniques, fils...) sont automatiquement exclus car ils n'ont pas de schéma sur EasyEDA.

La progression est affichée en temps réel. La génération tourne en arrière-plan et peut prendre plusieurs minutes selon le nombre de composants.

### Génération unitaire

Depuis la **fiche d'un composant** → bouton **Générer KiCad**

Génère uniquement les fichiers de ce composant. Plus rapide pour tester ou régénérer un composant spécifique.

## Fichiers générés

Pour chaque composant LCSC (ex: `C2040`), les fichiers sont créés dans `instance/kicad/` :

```
instance/kicad/
└── Resistors/
    └── C2040_Res_0402_100ohm/
        ├── C2040.kicad_sym      # Symbole schématique
        ├── C2040.kicad_mod      # Footprint PCB
        └── C2040.step           # Modèle 3D (si disponible)
```

## Fusion par catégorie

**Paramètres → KiCad Library → Fusionner par catégorie**

Fusionne tous les fichiers `.kicad_sym` d'une même catégorie en un seul fichier bibliothèque :

```
StockEleK_Resistors.kicad_sym
StockEleK_Capacitors.kicad_sym
StockEleK_ICs.kicad_sym
...
```

Option **Skip existing** : ne régénère pas les composants déjà présents dans la bibliothèque fusionnée.

## Enregistrement dans KiCad

**Paramètres → KiCad Library → Enregistrer dans KiCad**

Met à jour automatiquement les fichiers `sym-lib-table` et `fp-lib-table` de KiCad pour que les bibliothèques apparaissent dans KiCad sans manipulation manuelle.

> ⚠️ KiCad doit être fermé pendant cette opération.

## Téléchargement des librairies

**Paramètres → KiCad Library → Télécharger (.zip)**

Télécharge toutes les librairies générées dans une archive ZIP — utile pour sauvegarder ou partager.

## Compteur sur le dashboard

Le dashboard home affiche le nombre de composants **sans fichiers KiCad** encore générés. Ce compteur se charge en AJAX et ne bloque pas le rendu de la page. Cliquer dessus redirige vers la section KiCad des paramètres.

## Statut KiCad par composant

Sur chaque fiche composant, des badges indiquent si les fichiers existent :
- 🔷 **SYM** — Symbole généré
- 🔶 **FP** — Footprint généré
- 📦 **3D** — Modèle 3D généré

## Notes importantes

- Seuls les composants avec une **référence LCSC** et un **category_id** (composant enrichi) peuvent être générés
- Les composants mécaniques, visseries, fils sont automatiquement exclus
- La qualité des symboles dépend des données EasyEDA — certains composants rares peuvent avoir des symboles incomplets
