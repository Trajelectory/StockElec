"""AtelierModel — gestion des ateliers de rangement multi-locaux."""
import json
from .database import get_db


class AtelierModel:

    @staticmethod
    def settings_key(atelier_id: str, key: str) -> str:
        return f"atelier_{atelier_id}_{key}"

    @staticmethod
    def get_all() -> list:
        db = get_db()
        rows = db.execute("SELECT * FROM ateliers ORDER BY position, id").fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def get(atelier_id: str) -> dict | None:
        db = get_db()
        row = db.execute("SELECT * FROM ateliers WHERE id=?", (atelier_id,)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def get_or_first(atelier_id: str) -> dict | None:
        a = AtelierModel.get(atelier_id)
        if a:
            return a
        all_a = AtelierModel.get_all()
        return all_a[0] if all_a else None

    @staticmethod
    def create(atelier_id: str, name: str, emoji: str = "📦", color: str = "#7c3aed") -> bool:
        db = get_db()
        pos = db.execute("SELECT COUNT(*) FROM ateliers").fetchone()[0]
        try:
            db.execute(
                "INSERT INTO ateliers(id,name,emoji,color,position) VALUES(?,?,?,?,?)",
                (atelier_id.lower().strip(), name.strip(), emoji, color, pos)
            )
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False

    @staticmethod
    def update(atelier_id: str, **kwargs) -> bool:
        allowed = {"name","emoji","color","position","esp32_url","esp32_token","esp32_duration","esp32_offsets"}
        fields  = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields: return False
        db = get_db()
        try:
            set_clause = ", ".join(f"{k}=?" for k in fields)
            db.execute(f"UPDATE ateliers SET {set_clause} WHERE id=?",
                       list(fields.values()) + [atelier_id])
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False

    @staticmethod
    def delete(atelier_id: str) -> bool:
        from .settings import SettingsModel
        db = get_db()
        try:
            for key in ("rangement_config","rangement_assign","rangement_sizes"):
                db.execute("DELETE FROM settings WHERE key=?",
                           (AtelierModel.settings_key(atelier_id, key),))
            db.execute("DELETE FROM ateliers WHERE id=?", (atelier_id,))
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False

    @staticmethod
    def get_rangement_config(atelier_id: str) -> dict:
        from .settings import SettingsModel
        raw = SettingsModel.get(AtelierModel.settings_key(atelier_id, "rangement_config"), "")
        try:
            return json.loads(raw) if raw else {"plateaux":[{"id":"A","label":"Plateau A","cols":5,"rows":4}]}
        except Exception:
            return {"plateaux":[{"id":"A","label":"Plateau A","cols":5,"rows":4}]}

    @staticmethod
    def get_rangement_assign(atelier_id: str) -> dict:
        from .settings import SettingsModel
        raw = SettingsModel.get(AtelierModel.settings_key(atelier_id, "rangement_assign"), "")
        try: return json.loads(raw) if raw else {}
        except Exception: return {}

    @staticmethod
    def get_rangement_sizes(atelier_id: str) -> dict:
        from .settings import SettingsModel
        raw = SettingsModel.get(AtelierModel.settings_key(atelier_id, "rangement_sizes"), "")
        try: return json.loads(raw) if raw else {}
        except Exception: return {}

    @staticmethod
    def set_rangement_config(atelier_id: str, config: dict):
        from .settings import SettingsModel
        SettingsModel.set(AtelierModel.settings_key(atelier_id, "rangement_config"), json.dumps(config))

    @staticmethod
    def set_rangement_assign(atelier_id: str, assign: dict):
        from .settings import SettingsModel
        SettingsModel.set(AtelierModel.settings_key(atelier_id, "rangement_assign"), json.dumps(assign))

    @staticmethod
    def set_rangement_sizes(atelier_id: str, sizes: dict):
        from .settings import SettingsModel
        SettingsModel.set(AtelierModel.settings_key(atelier_id, "rangement_sizes"), json.dumps(sizes))
