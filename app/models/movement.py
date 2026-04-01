from .database import get_db


class MovementModel:

    TYPES = {
        "in":     ("📥", "Entrée",       "mv-badge-in"),
        "out":    ("📤", "Sortie",       "mv-badge-out"),
        "adjust": ("🔧", "Ajustement",   "mv-badge-adj"),
        "init":   ("🌱", "Initialisation","mv-badge-init"),
    }

    @staticmethod
    def record(component_id: int, type_: str, quantity: int,
               note: str = None, project_id: int = None):
        """Enregistre un mouvement de stock."""
        if type_ not in MovementModel.TYPES:
            return
        db = get_db()
        db.execute(
            """INSERT INTO stock_movements (component_id, type, quantity, note, project_id)
               VALUES (?, ?, ?, ?, ?)""",
            (component_id, type_, quantity, note, project_id)
        )
        db.commit()

    @staticmethod
    def get_recent(limit: int = 100, component_id: int = None) -> list[dict]:
        db = get_db()
        where = "WHERE m.component_id = ?" if component_id else ""
        params = [component_id] if component_id else []
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

    @staticmethod
    def get_stats() -> dict:
        db = get_db()
        today = db.execute(
            """SELECT COUNT(*) FROM stock_movements
               WHERE date(created_at) = date('now','localtime')"""
        ).fetchone()[0]
        week = db.execute(
            """SELECT COUNT(*) FROM stock_movements
               WHERE created_at >= datetime('now','localtime','-7 days')"""
        ).fetchone()[0]
        total_out = db.execute(
            """SELECT COALESCE(SUM(ABS(quantity)),0) FROM stock_movements WHERE type='out'"""
        ).fetchone()[0]
        return {"today": today, "week": week, "total_out": total_out}

    @staticmethod
    def get_activity_chart(days: int = 30) -> list[dict]:
        """Retourne nb mouvements par jour sur les N derniers jours."""
        db = get_db()
        rows = db.execute(
            """SELECT date(created_at) AS day, COUNT(*) AS count
               FROM stock_movements
               WHERE created_at >= datetime('now','localtime',? || ' days')
               GROUP BY day ORDER BY day""",
            (f"-{days}",)
        ).fetchall()
        return [dict(r) for r in rows]
