from .database import get_db


class MovementModel:

    # (emoji, clé_i18n, badge_css_class)
    TYPES = {
        "in":             ("📥", "history.mv_in",      "mv-badge-in"),
        "out":            ("📤", "history.mv_out",     "mv-badge-out"),
        "adjust":         ("🔧", "history.mv_adjust",  "mv-badge-adj"),
        "init":           ("🌱", "history.mv_init",    "mv-badge-init"),
        "project_use":    ("🔩", "history.mv_proj_use","mv-badge-out"),
        "project_return": ("↩️",  "history.mv_proj_ret","mv-badge-in"),
    }

    @staticmethod
    def record(component_id: int, type_: str, quantity: int,
               note: str = None, project_id: int = None):
        """Enregistre un mouvement de stock."""
        if type_ not in MovementModel.TYPES:
            return
        db = get_db()
        try:
            db.execute(
                """INSERT INTO stock_movements (component_id, type, quantity, note, project_id)
                   VALUES (?, ?, ?, ?, ?)""",
                (component_id, type_, quantity, note, project_id)
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def get_recent(limit: int = 100, component_id: int = None,
                   project_id: int = None) -> list[dict]:
        db = get_db()
        conditions, params = [], []
        if component_id:
            conditions.append("m.component_id = ?")
            params.append(component_id)
        if project_id:
            conditions.append("m.project_id = ?")
            params.append(project_id)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        rows = db.execute(
            f"""SELECT m.*, c.description, c.lcsc_part_number,
                       c.mouser_part_number, c.digikey_part_number, c.image_path,
                       p.name AS project_name
                FROM stock_movements m
                JOIN components c ON c.id = m.component_id
                LEFT JOIN projects p ON p.id = m.project_id
                {where}
                ORDER BY m.created_at DESC
                LIMIT ?""",
            params + [limit]
        ).fetchall()
        return [dict(r) for r in rows]


