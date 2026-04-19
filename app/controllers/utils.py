"""
Utilitaires partagés entre les controllers.
"""
import functools
import logging

from flask import request, jsonify
from ..models.settings import SettingsModel

logger = logging.getLogger(__name__)


def _t(key: str, **kwargs) -> str:
    """Retourne la string traduite selon la langue configurée."""
    from app import load_locale
    lang = SettingsModel.get("lang", "fr") or "fr"
    locale = load_locale(lang)
    parts = key.split(".")
    val = locale
    for p in parts:
        val = val.get(p, key) if isinstance(val, dict) else key
    if kwargs:
        try:
            val = val.format(**kwargs)
        except (KeyError, ValueError):
            pass
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

        # Requête navigateur — Referer présent (vient de l'interface web)
        if request.referrer:
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
