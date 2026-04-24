# 📋 Projets

## Vue d'ensemble

La section Projets (`/projects`) permet de gérer vos projets maker et d'associer des composants à chaque projet.

## Kanban des projets

La page principale affiche tous les projets sous forme de **kanban** organisé par statut :

| Statut | Description |
|--------|-------------|
| `idea` | Idée en cours de réflexion |
| `design` | En cours de conception |
| `ordered` | Composants commandés |
| `production` | En production |
| `assembly` | En cours d'assemblage |
| `debug` | Phase de débogage |
| `done` | Terminé |
| `archived` | Archivé |

Chaque carte affiche la **disponibilité des composants** en stock (ex: 8/12 composants disponibles, 67%).

## Créer un projet

1. Cliquer **+ Nouveau projet**
2. Renseigner :
   - **Nom** du projet
   - **Description**
   - **Statut** initial
   - **Image de couverture** (photo ou couleur de bannière)
   - **Tags** : PCB, Code/Firmware, Impression 3D, Mécanique, Design...

### Templates de checklist

En choisissant un tag principal, un template de checklist est proposé :
- **PCB** : Schéma KiCad → PCB routé → Gerber → BOM → Commande JLCPCB → Assemblage → Tests
- **Code** : Architecture → Dev → Tests → Documentation → Tag version
- **3D** : Modélisation → Impression test → Ajustements → Impression finale

## Fiche projet

### Onglet Composants

- **Ajouter un composant** : recherche AJAX instantanée dans tout le stock, sélection par description/ref LCSC
- **Tableau de disponibilité** : pour chaque composant, affiche la quantité requise vs le stock actuel (vert/orange/rouge)
- **Utiliser** / **Rendre** : décrémenter/incrémenter le stock directement depuis le projet
- **Kit** : prélever en une fois tous les composants du projet (débite le stock)
- **Retirer** : supprimer un composant de la liste du projet

### Onglet BOM (Bill of Materials)

#### Import BOM
1. Aller dans **Projets → [votre projet] → Importer BOM**
2. Uploader un fichier CSV (format KiCad, EasyEDA, JLCPCB...)
3. StockEleK analyse la BOM et génère un **rapport de disponibilité** :
   - ✅ Composants disponibles en stock (avec références)
   - ⚠️ Composants en stock insuffisant
   - ❌ Composants manquants (pas en stock du tout)
4. Sélectionner les composants manquants à créer
5. Cliquer **Appliquer** — les composants manquants sont créés et enrichis automatiquement

#### Export BOM
- Export CSV compatible JLCPCB avec toutes les références
- Bouton **Exporter BOM** depuis la fiche projet

### Onglet Notes
Éditeur de notes libre en Markdown — images uploadables directement dans les notes.

### Onglet Checklist
Suivi des étapes du projet avec cases à cocher. Personnalisable.

### Onglet Liens
Ajouter des liens utiles (datasheet, forum, GitHub, boutique...).

## Disponibilité des composants

StockEleK calcule en temps réel si vous avez assez de stock pour réaliser le projet. La barre de progression sur chaque carte du kanban indique le ratio composants disponibles / composants nécessaires.

## Gestion des images projet

- Upload d'une photo (max 3 Mo, formats JPEG/PNG/WebP/GIF)
- Ou sélection d'une **couleur de bannière** (color picker)
- L'image générée est stockée dans `instance/project_images/`
