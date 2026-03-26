from .database import get_db

STATUS_OPTIONS = ["en cours", "terminé", "en pause", "archivé"]


class Project:
    def __init__(self, row):
        keys = row.keys()
        self.id           = row["id"]
        self.name         = row["name"]
        self.description  = row["description"]
        self.status       = row["status"]
        self.created_at   = row["created_at"]
        self.updated_at   = row["updated_at"]
        # Colonnes jointes
        self.component_count = row["component_count"] if "component_count" in keys else None
        self.total_value     = row["total_value"]     if "total_value"     in keys else None
        self.image_path      = row["image_path"]      if "image_path"      in keys else None


class ProjectComponent:
    def __init__(self, row):
        keys = row.keys()
        self.id           = row["id"]
        self.project_id   = row["project_id"]
        self.component_id = row["component_id"]
        self.quantity     = row["quantity"]
        self.notes        = row["notes"]
        # Colonnes jointes depuis components
        self.description             = row["description"]             if "description"             in keys else None
        self.lcsc_part_number        = row["lcsc_part_number"]        if "lcsc_part_number"        in keys else None
        self.manufacture_part_number = row["manufacture_part_number"] if "manufacture_part_number" in keys else None
        self.manufacturer            = row["manufacturer"]            if "manufacturer"            in keys else None
        self.package                 = row["package"]                 if "package"                 in keys else None
        self.category                = row["category"]                if "category"                in keys else None
        self.stock_quantity          = row["stock_quantity"]          if "stock_quantity"          in keys else None
        self.unit_price              = row["unit_price"]              if "unit_price"              in keys else None
        self.image_path              = row["image_path"]              if "image_path"              in keys else None


class ProjectModel:

    # ---- READ --------------------------------------------------------

    @staticmethod
    def get_all() -> list:
        db = get_db()
        rows = db.execute(
            """
            SELECT p.*,
                   COUNT(pc.id)                         AS component_count,
                   COALESCE(SUM(c.unit_price * pc.quantity), 0) AS total_value
            FROM projects p
            LEFT JOIN project_components pc ON pc.project_id = p.id
            LEFT JOIN components         c  ON c.id = pc.component_id
            GROUP BY p.id
            ORDER BY p.updated_at DESC
            """
        ).fetchall()
        return [Project(r) for r in rows]

    @staticmethod
    def get_by_id(project_id: int):
        db = get_db()
        row = db.execute(
            """
            SELECT p.*,
                   COUNT(pc.id) AS component_count,
                   COALESCE(SUM(c.unit_price * pc.quantity), 0) AS total_value
            FROM projects p
            LEFT JOIN project_components pc ON pc.project_id = p.id
            LEFT JOIN components         c  ON c.id = pc.component_id
            WHERE p.id = ?
            GROUP BY p.id
            """,
            (project_id,),
        ).fetchone()
        return Project(row) if row else None

    @staticmethod
    def get_components(project_id: int) -> list:
        db = get_db()
        rows = db.execute(
            """
            SELECT pc.*,
                   c.description, c.lcsc_part_number, c.manufacture_part_number,
                   c.manufacturer, c.package, c.category,
                   c.quantity AS stock_quantity,
                   c.unit_price, c.image_path
            FROM project_components pc
            JOIN components c ON c.id = pc.component_id
            WHERE pc.project_id = ?
            ORDER BY c.description
            """,
            (project_id,),
        ).fetchall()
        return [ProjectComponent(r) for r in rows]

    # ---- WRITE -------------------------------------------------------

    @staticmethod
    def create(data: dict) -> int:
        db = get_db()
        cur = db.execute(
            "INSERT INTO projects (name, description, status, image_path) VALUES (?, ?, ?, ?)",
            (data["name"], data.get("description"), data.get("status", "en cours"), data.get("image_path")),
        )
        db.commit()
        return cur.lastrowid

    @staticmethod
    def update(project_id: int, data: dict):
        db = get_db()
        db.execute(
            "UPDATE projects SET name=?, description=?, status=?, image_path=? WHERE id=?",
            (data["name"], data.get("description"), data.get("status", "en cours"),
             data.get("image_path"), project_id),
        )
        db.commit()

    @staticmethod
    def delete(project_id: int):
        db = get_db()
        db.execute("DELETE FROM projects WHERE id=?", (project_id,))
        db.commit()

    # ---- Composants du projet ----------------------------------------

    @staticmethod
    def add_component(project_id: int, component_id: int, quantity: int, notes: str = None):
        db = get_db()
        db.execute(
            """
            INSERT INTO project_components (project_id, component_id, quantity, notes)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(project_id, component_id) DO UPDATE SET
                quantity = excluded.quantity,
                notes    = excluded.notes
            """,
            (project_id, component_id, quantity, notes),
        )
        db.commit()

    @staticmethod
    def remove_component(project_id: int, component_id: int):
        db = get_db()
        db.execute(
            "DELETE FROM project_components WHERE project_id=? AND component_id=?",
            (project_id, component_id),
        )
        db.commit()

    @staticmethod
    def get_projects_for_component(component_id: int) -> list:
        """Retourne les projets qui utilisent ce composant."""
        db = get_db()
        rows = db.execute(
            """
            SELECT p.id, p.name, p.status, pc.quantity
            FROM projects p
            JOIN project_components pc ON pc.project_id = p.id
            WHERE pc.component_id = ?
            ORDER BY p.name
            """,
            (component_id,),
        ).fetchall()
        return [dict(r) for r in rows]
