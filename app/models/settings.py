import time
import threading
from .database import get_db

# ── Cache module-level TTL 30s ─────────────────────────────────────────
_cache: dict = {"data": None, "ts": 0.0}
_cache_lock = threading.Lock()
_CACHE_TTL  = 30.0


def _load_all() -> dict:
    """Charge tous les settings en une seule requête SELECT *."""
    db   = get_db()
    rows = db.execute("SELECT key, value FROM settings").fetchall()
    data = {r["key"]: r["value"] for r in rows}
    with _cache_lock:
        _cache["data"] = data
        _cache["ts"]   = time.monotonic()
    return data


def _get_cache() -> dict:
    """
    Retourne les settings depuis le cache.

    Priorité 1 — cache par requête HTTP (flask.g) :
        Au premier appel d'une requête HTTP, charge tous les settings
        en 1 SELECT et les stocke dans g._settings_cache.
        Tous les appels suivants dans la même requête lisent g directement
        sans toucher à la DB. C'est ce qui élimine le N+1.

    Priorité 2 — cache module TTL 30s :
        Hors contexte Flask (CLI, threads background...), on utilise
        un cache module-level invalidé toutes les 30s.
    """
    try:
        from flask import g
        if not hasattr(g, "_settings_cache"):
            g._settings_cache = _load_all()
        return g._settings_cache
    except RuntimeError:
        pass  # pas de contexte Flask

    # Fallback TTL
    with _cache_lock:
        if _cache["data"] is not None and time.monotonic() - _cache["ts"] < _CACHE_TTL:
            return _cache["data"]
    return _load_all()


def invalidate_cache():
    """Invalide les deux niveaux de cache après un SettingsModel.set()."""
    with _cache_lock:
        _cache["data"] = None
        _cache["ts"]   = 0.0
    try:
        from flask import g
        if hasattr(g, "_settings_cache"):
            del g._settings_cache
    except RuntimeError:
        pass


class SettingsModel:
    """Stockage clé/valeur persistant pour la configuration de l'app.

    Après cette réécriture :
    - get()     → 0 SQL (cache g ou module)
    - set()     → 1 SQL INSERT/UPDATE + invalidation du cache
    - get_all() → 0 SQL (cache)

    Le premier appel par requête HTTP charge tout en 1 SELECT *.
    """

    @staticmethod
    def get(key: str, default: str = "") -> str:
        return _get_cache().get(key, default)

    @staticmethod
    def set(key: str, value: str):
        db = get_db()
        try:
            db.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            invalidate_cache()

    @staticmethod
    def get_all() -> dict:
        return _get_cache()
