"""
Utilitaires partagés entre les controllers.
"""
import functools
import logging
import threading
import time as _time

from flask import request, jsonify
from ..models.settings import SettingsModel

logger = logging.getLogger(__name__)

# Cache TTL pour la langue courante — évite 1 SQL par appel à _t()
# (le context_processor Jinja a son propre cache ; celui-ci couvre les appels Python)
_lang_cache: dict = {"lang": None, "ts": 0.0}
_lang_lock = threading.Lock()
_LANG_TTL  = 2.0  # secondes


def _get_lang() -> str:
    """Retourne la langue courante avec cache TTL 2s — 1 SQL max toutes les 2s."""
    now = _time.time()
    with _lang_lock:
        if _lang_cache["lang"] is None or now - _lang_cache["ts"] > _LANG_TTL:
            _lang_cache["lang"] = SettingsModel.get("lang", "fr") or "fr"
            _lang_cache["ts"]   = now
    return _lang_cache["lang"]


def _t(key: str, **kwargs) -> str:
    """Retourne la string traduite selon la langue configurée."""
    from app import load_locale
    lang   = _get_lang()
    locale = load_locale(lang)
    parts  = key.split(".")
    val    = locale
    for p in parts:
        val = val.get(p, key) if isinstance(val, dict) else key
    if kwargs:
        try:
            val = val.format(**kwargs)
        except (KeyError, ValueError) as e:
            logger.debug("Ignored: %s", e)
    return val


def require_esp32_token(f):
    """
    Décorateur — vérifie le header X-Token sur les routes mixtes ESP32 / navigateur.

    Logique :
      - Requête navigateur (X-Requested-With: XMLHttpRequest ou Referer présent) → autorisé
      - Requête ESP32 (pas de Referer, pas de X-Requested-With) → X-Token requis
      - esp32_token vide dans les settings → auth désactivée (dev mode)
    """
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        expected = SettingsModel.get("esp32_token", "").strip()

        # Pas de token configuré → accès libre (dev mode)
        if not expected:
            return f(*args, **kwargs)

        # Requête navigateur — Referer présent ET appartenant au même hôte
        # (vérifié pour éviter qu'un attaquant forge un header Referer arbitraire)
        if request.referrer and request.referrer.startswith(request.host_url):
            return f(*args, **kwargs)

        # Requête AJAX navigateur — header standard des fetch()/XMLHttpRequest
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return f(*args, **kwargs)

        # Requête ESP32 — vérifier le header X-Token
        received = request.headers.get("X-Token", "").strip()
        if received != expected:
            logger.warning(
                "[AUTH] Token invalide sur %s — reçu: %r",
                request.path, received[:8] + "…" if received else "(vide)"
            )
            return jsonify({
                "ok": False,
                "error": "Token invalide ou manquant"
            }), 401

        return f(*args, **kwargs)
    return decorated
