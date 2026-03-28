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
        Retourne les catégories utilisées dans le stock + toutes les catégories
        custom (ID < 0), groupées pour les <optgroup> HTML.
        """
        db = get_db()

        groups: dict[str, list] = {}
        NO_GROUP = "__none__"

        # 1. Catégories déjà utilisées dans le stock
        rows = db.execute(
            """
            SELECT DISTINCT c.category
            FROM components c
            WHERE c.category IS NOT NULL AND c.category != ''
            ORDER BY c.category
            """
        ).fetchall()

        for row in rows:
            path = row["category"]
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
                parts = path.split(" / ", 1)
                group = parts[0]
                label = parts[1]
            else:
                group = NO_GROUP
                label = path

            groups.setdefault(group, [])
            if not any(o["value"] == path for o in groups[group]):
                groups[group].append({"value": path, "label": label})

        # 2. Ajoute toutes les catégories custom (ID < 0) même si pas encore utilisées
        custom_rows = db.execute(
            """
            SELECT c.id, c.name, c.full_path, c.parent_id, p.name AS parent_name
            FROM categories c
            LEFT JOIN categories p ON p.id = c.parent_id
            WHERE c.id < 0
            ORDER BY p.name NULLS LAST, c.name
            """
        ).fetchall()

        # Collecte les IDs parents qui ont des enfants custom
        parent_ids_with_children = {
            c["parent_id"] for c in custom_rows if c["parent_id"] is not None
        }

        for c in custom_rows:
            if c["parent_id"] is None:
                # Groupe racine : ne l'ajoute que s'il n'a aucun enfant custom
                if c["id"] not in parent_ids_with_children:
                    path  = c["full_path"] or c["name"]
                    label = c["name"]
                    group = NO_GROUP
                    groups.setdefault(group, [])
                    if not any(o["value"] == path for o in groups[group]):
                        groups[group].append({"value": path, "label": label})
            else:
                # Sous-catégorie : toujours affichée
                path  = c["full_path"]
                label = c["name"]
                group = c["parent_name"] or NO_GROUP
                groups.setdefault(group, [])
                if not any(o["value"] == path for o in groups[group]):
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

    @staticmethod
    def create_custom(parent_name: str, child_name: str | None = None) -> int:
        """
        Crée une catégorie personnalisée (ID négatif pour éviter les collisions LCSC).
        Retourne l'ID créé.
        """
        db = get_db()
        # Trouve le plus petit ID (négatif) disponible
        row = db.execute("SELECT MIN(id) FROM categories").fetchone()
        min_id = row[0] or 0
        new_id = min(min_id - 1, -1)

        parent_name = parent_name.strip()
        if child_name:
            child_name = child_name.strip()

        # Cherche ou crée le parent
        parent_row = db.execute(
            "SELECT id FROM categories WHERE name = ? AND parent_id IS NULL",
            (parent_name,)
        ).fetchone()

        if parent_row:
            parent_id = parent_row["id"]
        else:
            parent_id = new_id
            db.execute(
                "INSERT INTO categories (id, parent_id, name, full_path) VALUES (?, NULL, ?, ?)",
                (parent_id, parent_name, parent_name)
            )
            new_id -= 1

        if child_name:
            full_path = f"{parent_name} / {child_name}"
            db.execute(
                "INSERT INTO categories (id, parent_id, name, full_path) VALUES (?, ?, ?, ?)",
                (new_id, parent_id, child_name, full_path)
            )
            db.commit()
            return new_id
        else:
            db.commit()
            return parent_id

    @staticmethod
    def delete_custom(category_id: int):
        """Supprime une catégorie custom (ID négatif uniquement). Met à jour les composants."""
        db = get_db()
        cat = db.execute("SELECT * FROM categories WHERE id = ?", (category_id,)).fetchone()
        if not cat or cat["id"] >= 0:
            return  # Ne supprime jamais les catégories LCSC

        full_path = cat["full_path"]
        # Réinitialise la catégorie des composants qui l'utilisent
        db.execute(
            "UPDATE components SET category = NULL, category_id = NULL WHERE category = ?",
            (full_path,)
        )
        # Supprime les enfants si c'est un parent
        children = db.execute(
            "SELECT id FROM categories WHERE parent_id = ?", (category_id,)
        ).fetchall()
        for child in children:
            if child["id"] < 0:
                db.execute("DELETE FROM categories WHERE id = ?", (child["id"],))
        db.execute("DELETE FROM categories WHERE id = ?", (category_id,))
        db.commit()

    @staticmethod
    def get_custom() -> list[dict]:
        """Retourne toutes les catégories personnalisées (ID < 0)."""
        db = get_db()
        rows = db.execute(
            """
            SELECT c.id, c.name, c.full_path, c.parent_id, p.name AS parent_name
            FROM categories c
            LEFT JOIN categories p ON p.id = c.parent_id
            WHERE c.id < 0
            ORDER BY p.name NULLS LAST, c.name
            """
        ).fetchall()
        return [dict(r) for r in rows]
