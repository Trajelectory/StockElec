from .database import get_db


class CategoryModel:
    """Gestion de l'arborescence des catégories LCSC."""

    @staticmethod
    def upsert(category_id: int, name: str, parent_id: int | None,
               parent_name: str | None = None):
        """
        Insère ou met à jour une catégorie.
        Calcule automatiquement full_path depuis le parent.
        """
        if not category_id or not name:
            return

        db = get_db()

        # Calcul du chemin complet
        if parent_name and parent_name != name:
            full_path = f"{parent_name} / {name}"
        else:
            full_path = name

        # Upsert parent d'abord si nécessaire
        if parent_id and parent_name:
            existing_parent = db.execute(
                "SELECT id FROM categories WHERE id = ?", (parent_id,)
            ).fetchone()
            if not existing_parent:
                db.execute(
                    "INSERT OR IGNORE INTO categories (id, parent_id, name, full_path) VALUES (?, NULL, ?, ?)",
                    (parent_id, parent_name, parent_name),
                )

        db.execute(
            """
            INSERT INTO categories (id, parent_id, name, full_path)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name      = excluded.name,
                full_path = excluded.full_path,
                parent_id = excluded.parent_id
            """,
            (category_id, parent_id, name, full_path),
        )
        db.commit()

    @staticmethod
    def get_all() -> list[dict]:
        db = get_db()
        rows = db.execute(
            """
            SELECT c.id, c.name, c.full_path, c.parent_id, p.name AS parent_name
            FROM categories c
            LEFT JOIN categories p ON p.id = c.parent_id
            ORDER BY p.name NULLS LAST, c.name
            """
        ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def get_tree() -> list[dict]:
        """
        Retourne les catégories parentes avec leurs enfants imbriqués.
        Structure: [{ id, name, children: [{id, name, full_path}] }]
        """
        db = get_db()
        # Catégories racines (sans parent)
        roots = db.execute(
            "SELECT * FROM categories WHERE parent_id IS NULL ORDER BY name"
        ).fetchall()

        tree = []
        for root in roots:
            children = db.execute(
                "SELECT * FROM categories WHERE parent_id = ? ORDER BY name",
                (root["id"],),
            ).fetchall()
            tree.append({
                "id":       root["id"],
                "name":     root["name"],
                "children": [dict(c) for c in children],
            })

        # Catégories sans parent trouvé (orphelines)
        orphans = db.execute(
            """
            SELECT c.* FROM categories c
            WHERE c.parent_id IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM categories p WHERE p.id = c.parent_id)
            ORDER BY c.name
            """
        ).fetchall()
        if orphans:
            tree.append({
                "id": None,
                "name": "Autres",
                "children": [dict(o) for o in orphans],
            })

        return tree


    @staticmethod
    def get_grouped_for_stock() -> list[dict]:
        """
        Retourne les catégories réellement utilisées dans le stock,
        groupées hiérarchiquement pour les <optgroup> HTML.

        Résultat : [
          { "group": "Resistors", "options": [
              {"value": "Resistors / Chip Resistor - Surface Mount",
               "label": "Chip Resistor - Surface Mount"},
              ...
          ]},
          { "group": None,   # catégories sans parent détecté
            "options": [...] }
        ]
        """
        db = get_db()

        # Toutes les catégories distinctes présentes dans le stock
        rows = db.execute(
            """
            SELECT DISTINCT c.category
            FROM components c
            WHERE c.category IS NOT NULL AND c.category != ''
            ORDER BY c.category
            """
        ).fetchall()
        all_paths = [r["category"] for r in rows]

        if not all_paths:
            return []

        # Pour chaque full_path, essaie de trouver le groupe parent
        # en cherchant dans la table categories
        groups: dict[str, list] = {}   # group_name -> [option, ...]
        NO_GROUP = "__none__"

        for path in all_paths:
            # Cherche dans la table categories si on a un parent connu
            cat_row = db.execute(
                """
                SELECT c.name, p.name AS parent_name
                FROM categories c
                LEFT JOIN categories p ON p.id = c.parent_id
                WHERE c.full_path = ?
                """,
                (path,),
            ).fetchone()

            if cat_row and cat_row["parent_name"]:
                group = cat_row["parent_name"]
                label = cat_row["name"]
            elif " / " in path:
                # Fallback : split sur " / "
                parts = path.split(" / ", 1)
                group = parts[0]
                label = parts[1]
            else:
                group = NO_GROUP
                label = path

            if group not in groups:
                groups[group] = []
            groups[group].append({"value": path, "label": label})

        # Construit la liste finale, groupes triés, NO_GROUP en dernier
        result = []
        for group in sorted(k for k in groups if k != NO_GROUP):
            result.append({"group": group, "options": groups[group]})
        if NO_GROUP in groups:
            result.append({"group": None, "options": groups[NO_GROUP]})

        return result

    @staticmethod
    def get_full_paths() -> list[str]:
        """Liste des full_path pour les filtres déroulants."""
        db = get_db()
        rows = db.execute(
            "SELECT DISTINCT full_path FROM categories WHERE full_path IS NOT NULL ORDER BY full_path"
        ).fetchall()
        return [r["full_path"] for r in rows]
