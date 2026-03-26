from .database import get_db

# Types de mouvements
TYPE_IMPORT         = "import"
TYPE_MANUAL_ADD     = "manual_add"
TYPE_MANUAL_REMOVE  = "manual_remove"
TYPE_PROJECT_USE    = "project_use"
TYPE_PROJECT_RETURN = "project_return"
TYPE_ADJUSTMENT     = "adjustment"

LABELS = {
    TYPE_IMPORT:         ("📥", "Import CSV"),
    TYPE_MANUAL_ADD:     ("➕", "Ajout manuel"),
    TYPE_MANUAL_REMOVE:  ("➖", "Retrait manuel"),
    TYPE_PROJECT_USE:    ("🔧", "Utilisé (projet)"),
    TYPE_PROJECT_RETURN: ("↩️",  "Retour (projet)"),
    TYPE_ADJUSTMENT:     ("✏️",  "Ajustement"),
}


class Movement:
    def __init__(self, row):
        self.id           = row["id"]
        self.component_id = row["component_id"]
        self.type         = row["type"]
        self.qty_before   = row["qty_before"]
        self.qty_change   = row["qty_change"]
        self.qty_after    = row["qty_after"]
        self.project_id   = row["project_id"]
        self.note         = row["note"]
        self.created_at   = row["created_at"]
        # Colonnes jointes (optionnelles)
        keys = row.keys()
        self.component_description = row["component_description"] if "component_description" in keys else None
        self.component_lcsc        = row["component_lcsc"]        if "component_lcsc"        in keys else None
        self.project_name          = row["project_name"]          if "project_name"          in keys else None

    @property
    def icon(self):
        return LABELS.get(self.type, ("❓", ""))[0]

    @property
    def label(self):
        return LABELS.get(self.type, ("❓", self.type))[1]

    @property
    def is_positive(self):
        return self.qty_change > 0


class MovementModel:

    @staticmethod
    def record(component_id: int, movement_type: str, qty_before: int,
               qty_change: int, project_id: int = None, note: str = None):
        """Enregistre un mouvement de stock."""
        db = get_db()
        db.execute(
            """
            INSERT INTO stock_movements
                (component_id, type, qty_before, qty_change, qty_after, project_id, note)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                component_id,
                movement_type,
                qty_before,
                qty_change,
                qty_before + qty_change,
                project_id,
                note,
            ),
        )
        db.commit()

    @staticmethod
    def get_for_component(component_id: int, limit: int = 50) -> list:
        db = get_db()
        rows = db.execute(
            """
            SELECT m.*,
                   p.name AS project_name
            FROM stock_movements m
            LEFT JOIN projects p ON p.id = m.project_id
            WHERE m.component_id = ?
            ORDER BY m.created_at DESC
            LIMIT ?
            """,
            (component_id, limit),
        ).fetchall()
        return [Movement(r) for r in rows]

    @staticmethod
    def get_recent(limit: int = 100) -> list:
        db = get_db()
        rows = db.execute(
            """
            SELECT m.*,
                   c.description AS component_description,
                   c.lcsc_part_number AS component_lcsc,
                   p.name AS project_name
            FROM stock_movements m
            JOIN  components c ON c.id = m.component_id
            LEFT JOIN projects p ON p.id = m.project_id
            ORDER BY m.created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [Movement(r) for r in rows]

    @staticmethod
    def get_stats() -> dict:
        db = get_db()
        row = db.execute(
            """
            SELECT
                COUNT(*)                                        AS total_movements,
                COALESCE(SUM(CASE WHEN qty_change > 0 THEN  qty_change ELSE 0 END), 0) AS total_in,
                COALESCE(SUM(CASE WHEN qty_change < 0 THEN -qty_change ELSE 0 END), 0) AS total_out
            FROM stock_movements
            """
        ).fetchone()
        return dict(row) if row else {}
