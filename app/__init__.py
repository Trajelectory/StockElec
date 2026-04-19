import logging
import os
import json
import threading
from flask import Flask
from .models.database import init_db

logger = logging.getLogger(__name__)

# Cache des locales chargées en mémoire — protégé par un Lock pour la sécurité thread
_locale_cache: dict = {}
_locale_lock  = threading.Lock()

def load_locale(lang: str) -> dict:
    """Charge et met en cache le fichier de locale JSON (thread-safe)."""
    if lang in _locale_cache:
        return _locale_cache[lang]
    with _locale_lock:
        # Double-check après acquisition du lock
        if lang in _locale_cache:
            return _locale_cache[lang]
        locale_path   = os.path.join(os.path.dirname(__file__), "locales", f"{lang}.json")
        fallback_path = os.path.join(os.path.dirname(__file__), "locales", "fr.json")
        try:
            with open(locale_path, encoding="utf-8") as f:
                _locale_cache[lang] = json.load(f)
        except FileNotFoundError:
            try:
                with open(fallback_path, encoding="utf-8") as f:
                    _locale_cache[lang] = json.load(f)
            except Exception:
                _locale_cache[lang] = {}
    return _locale_cache[lang]


def _get_or_create_secret_key(instance_path: str) -> str:
    """Retourne la SECRET_KEY depuis la variable d'env, ou la génère/recharge depuis instance/."""
    env_key = os.environ.get("SECRET_KEY", "")
    if env_key:
        return env_key
    key_file = os.path.join(instance_path, "secret_key")
    if os.path.exists(key_file):
        return open(key_file).read().strip()
    import secrets
    os.makedirs(instance_path, exist_ok=True)
    new_key = secrets.token_hex(32)
    open(key_file, "w").write(new_key)
    logger.info("SECRET_KEY générée et sauvegardée dans %s", key_file)
    return new_key


import time as _time

def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["SECRET_KEY"] = _get_or_create_secret_key(app.instance_path)
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
    _CACHE_BUSTER = int(_time.time())

    init_db(app)

    from .controllers import component_bp
    from .controllers.project_controller import project_bp
    from .controllers.routes_kicad import kicad_bp
    app.register_blueprint(component_bp)
    app.register_blueprint(project_bp)
    app.register_blueprint(kicad_bp)
    from .controllers.routes_misc import register_docs
    register_docs(app)

    # Cache settings pour le context_processor (TTL 5s)
    # Évite 1 requête SQL par page vue tout en restant réactif aux changements
    _settings_cache: dict = {}
    _settings_cache_ts: list = [0.0]  # liste pour mutabilité dans la closure
    _settings_cache_lock = threading.Lock()

    # Injecte les variables globales disponibles dans tous les templates
    @app.context_processor
    def inject_globals():
        from .models.settings import SettingsModel
        import time as _time

        now = _time.time()
        with _settings_cache_lock:
            if now - _settings_cache_ts[0] > 5.0 or not _settings_cache:
                try:
                    fresh = SettingsModel.get_all()
                    _settings_cache.clear()
                    _settings_cache.update(fresh)
                    _settings_cache_ts[0] = now
                except Exception:
                    pass

        app_name = _settings_cache.get("app_name", "") or "StockEleK"
        lang     = _settings_cache.get("lang", "")     or "fr"
        t = load_locale(lang)
        return {"app_name": app_name, "t": t, "lang": lang, "cache_buster": _CACHE_BUSTER}

    # ── Gestionnaires d'erreur HTTP ──────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        from flask import render_template, request
        if request.path.startswith("/api/") or request.path.startswith("/kicad/"):
            from flask import jsonify
            return jsonify({"ok": False, "error": "Ressource introuvable"}), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        from flask import render_template, request
        import logging
        logging.getLogger(__name__).error("Erreur 500 sur %s : %s", request.path, e)
        if request.path.startswith("/api/") or request.path.startswith("/kicad/"):
            from flask import jsonify
            return jsonify({"ok": False, "error": "Erreur interne du serveur"}), 500
        return render_template("errors/500.html"), 500

    return app
