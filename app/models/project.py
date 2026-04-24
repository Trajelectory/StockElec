import json
from .database import get_db

STATUS_OPTIONS = ["idea", "design", "ordered", "production", "assembly", "debug", "done", "archived"]

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
        d = dict(row)
        self.id           = d["id"]
        self.name         = d["name"]
        self.description  = d["description"]
        self.status       = d["status"]
        self.created_at   = d["created_at"]
        self.updated_at   = d["updated_at"]
        # Tags, checklist, liens — JSON stocké en base
        try:
            self.tags      = json.loads(d.get("tags")      or "[]")
        except (json.JSONDecodeError, ValueError) as e:
            logger.debug("Ignored: %s", e); self.tags = []
        try:
            self.checklist = json.loads(d.get("checklist") or "[]")
        except (json.JSONDecodeError, ValueError) as e:
            logger.debug("Ignored: %s", e); self.checklist = []
        try:
            self.links     = json.loads(d.get("links")     or "[]")
        except (json.JSONDecodeError, ValueError) as e:
            logger.debug("Ignored: %s", e); self.links = []
        # Colonnes jointes (optionnelles selon la requête)
        self.component_count = d.get("component_count")
        self.total_value     = d.get("total_value")
        self.image_path      = d.get("image_path")
        self.notes           = d.get("notes")


class ProjectComponent:
    def __init__(self, row):
        d = dict(row)
        self.id           = d["id"]
        self.project_id   = d["project_id"]
        self.component_id = d["component_id"]
        self.quantity     = d["quantity"]
        self.notes        = d["notes"]
        # Colonnes jointes depuis components (optionnelles selon la requête)
        self.description             = d.get("description")
        self.lcsc_part_number        = d.get("lcsc_part_number")
        self.mouser_part_number      = d.get("mouser_part_number")
        self.digikey_part_number     = d.get("digikey_part_number")
        self.manufacture_part_number = d.get("manufacture_part_number")
        self.manufacturer            = d.get("manufacturer")
        self.package                 = d.get("package")
        self.category                = d.get("category")
        self.stock_quantity          = d.get("stock_quantity")
        self.unit_price              = d.get("unit_price")
        self.image_path              = d.get("image_path")


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
            cur = db.execute(
                """INSERT INTO projects
                   (name, description, status, image_path, tags, checklist, links)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    data["name"],
                    data.get("description"),
                    data.get("status", "idea"),
                    data.get("image_path"),
                    json.dumps(data.get("tags",      []), ensure_ascii=False),
                    json.dumps(data.get("checklist", []), ensure_ascii=False),
                    json.dumps(data.get("links",     []), ensure_ascii=False),
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
            db = get_db()
            db.execute(
                """UPDATE projects SET name=?, description=?, status=?, image_path=?,
                   tags=?, checklist=?, links=?, notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (
                    data["name"],
                    data.get("description"),
                    data.get("status", "idea"),
                    data.get("image_path"),
                    json.dumps(data.get("tags", []),      ensure_ascii=False),
                    json.dumps(data.get("checklist", []), ensure_ascii=False),
                    json.dumps(data.get("links", []),     ensure_ascii=False),
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


    @staticmethod
    def get_active(limit: int = 4) -> list:
        """Projets actifs (non terminés/archivés) pour le dashboard."""
        db = get_db()
        return db.execute("""
            SELECT id, name, status, created_at
            FROM projects WHERE status NOT IN ('done', 'archived')
            ORDER BY created_at DESC LIMIT ?
        """, (limit,)).fetchall()

    @staticmethod
    def get_recent_movements(limit: int = 8) -> list:
        """Derniers mouvements de stock toutes sources confondues pour le dashboard."""
        db = get_db()
        return db.execute("""
            SELECT m.type, m.quantity, m.created_at, m.note,
                   c.id AS component_id, c.description, c.lcsc_part_number, c.image_path
            FROM stock_movements m
            JOIN components c ON c.id = m.component_id
            ORDER BY m.created_at DESC LIMIT ?
        """, (limit,)).fetchall()

