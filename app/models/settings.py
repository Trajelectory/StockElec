from .database import get_db


class SettingsModel:
    """Stockage clé/valeur persistant pour la configuration de l'app."""

    @staticmethod
    def get(key: str, default: str = "") -> str:
        db = get_db()
        row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    @staticmethod
    def set(key: str, value: str):
        db = get_db()
        db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        db.commit()

    @staticmethod
    def get_all() -> dict:
        db = get_db()
        rows = db.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}
