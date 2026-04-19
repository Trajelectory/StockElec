from .database import get_db

STATUS_OPTIONS = ["idée", "conception", "commandé", "en production", "assemblage", "debug", "terminé", "archivé"]

# Tags disponibles — (slug, label, emoji, couleur)
TAG_OPTIONS = [
    ("pcb",        "Électronique / PCB",  "🔌", "#7c6cff"),
    ("code",       "Code / Firmware",     "💻", "#06b6d4"),
    ("3d",         "Impression 3D",       "🖨️", "#f97316"),
    ("mecanique",  "Mécanique",           "⚙️", "#8b5cf6"),
    ("design",     "Design / UI",         "🎨", "#ec4899"),
    ("recherche",  "Recherche",           "🔬", "#f59e0b"),
    ("autre",      "Autre",               "📌", "#6b7280"),
]

# Templates de checklist par type de projet
CHECKLIST_TEMPLATES = {
    "pcb": [
        "Schéma KiCad complété",
        "PCB routé et vérifié (DRC)",
        "Fichiers Gerber exportés",
        "BOM exportée",
        "Commande JLCPCB passée",
        "Composants commandés (LCSC/Mouser)",
        "PCB reçu",
        "Composants reçus",
        "Assemblage et soudure",
        "Tests et debug",
        "Firmware flashé",
    ],
    "code": [
        "Architecture définie",
        "Environnement de dev configuré",
        "Code de base fonctionnel",
        "Tests écrits",
        "Documentation",
        "Version finale taggée",
    ],
    "3d": [
        "Modélisation CAO",
        "Vérification des cotes",
        "Fichier STL exporté",
        "Impression test",
        "Ajustements si besoin",
        "Impression finale",
        "Post-traitement",
    ],
}


class Project:
    def __init__(self, row):
        import json as _json
        keys = row.keys()
        self.id           = row["id"]
        self.name         = row["name"]
        self.description  = row["description"]
        self.status       = row["status"]
        self.created_at   = row["created_at"]
        self.updated_at   = row["updated_at"]
        # Tags, checklist, liens
        try: self.tags      = _json.loads(row["tags"]      if "tags"      in keys and row["tags"]      else "[]")
        except: self.tags   = []
        try: self.checklist = _json.loads(row["checklist"] if "checklist" in keys and row["checklist"] else "[]")
        except: self.checklist = []
        try: self.links     = _json.loads(row["links"]     if "links"     in keys and row["links"]     else "[]")
        except: self.links  = []
        # Colonnes jointes
        self.component_count = row["component_count"] if "component_count" in keys else None
        self.total_value     = row["total_value"]     if "total_value"     in keys else None
        self.image_path      = row["image_path"]      if "image_path"      in keys else None
        self.notes           = row["notes"]           if "notes"           in keys else None


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
        self.mouser_part_number      = row["mouser_part_number"]      if "mouser_part_number"      in keys else None
        self.digikey_part_number     = row["digikey_part_number"]     if "digikey_part_number"     in keys else None
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
                   c.description, c.lcsc_part_number, c.mouser_part_number, c.digikey_part_number,
                   c.manufacture_part_number,
                   c.manufacturer, c.package, c.category,
                   c.quantity AS stock_quantity,
                   c.unit_price, c.image_path
            FROM project_components pc
            JOIN components c ON c.id = pc.component_id
            WHERE pc.project_id = ?
            ORDER BY
                CASE WHEN c.category IS NULL OR c.category = '' THEN 1 ELSE 0 END,
                c.category,
                c.description
            """,
            (project_id,),
        ).fetchall()
        return [ProjectComponent(r) for r in rows]

    # ---- WRITE -------------------------------------------------------

    @staticmethod
    def create(data: dict) -> int:
        try:
            db = get_db()
            import json as _json
            cur = db.execute(
                """INSERT INTO projects
                   (name, description, status, image_path, tags, checklist, links)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    data["name"],
                    data.get("description"),
                    data.get("status", "idée"),
                    data.get("image_path"),
                    _json.dumps(data.get("tags",      []), ensure_ascii=False),
                    _json.dumps(data.get("checklist", []), ensure_ascii=False),
                    _json.dumps(data.get("links",     []), ensure_ascii=False),
                ),
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        return cur.lastrowid

    @staticmethod
    def update(project_id: int, data: dict):
        try:
            import json as _json
            db = get_db()
            db.execute(
                """UPDATE projects SET name=?, description=?, status=?, image_path=?,
                   tags=?, checklist=?, links=?, notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (
                    data["name"],
                    data.get("description"),
                    data.get("status", "idée"),
                    data.get("image_path"),
                    _json.dumps(data.get("tags", []),      ensure_ascii=False),
                    _json.dumps(data.get("checklist", []), ensure_ascii=False),
                    _json.dumps(data.get("links", []),     ensure_ascii=False),
                    data.get("notes", None),
                    project_id,
                ),
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def delete(project_id: int):
        db = get_db()
        try:
            db.execute("DELETE FROM projects WHERE id=?", (project_id,))
            db.commit()
        except Exception:
            db.rollback()
            raise

    # ---- Composants du projet ----------------------------------------

    @staticmethod
    def add_component(project_id: int, component_id: int, quantity: int, notes: str = None):
        try:
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
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def remove_component(project_id: int, component_id: int):
        try:
            db = get_db()
            db.execute(
                "DELETE FROM project_components WHERE project_id=? AND component_id=?",
                (project_id, component_id),
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

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
