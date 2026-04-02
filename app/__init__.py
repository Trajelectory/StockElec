import logging
import os
import json
from flask import Flask
from .models.database import init_db

logger = logging.getLogger(__name__)

# Cache des locales chargées en mémoire
_locale_cache: dict = {}

def load_locale(lang: str) -> dict:
    """Charge et met en cache le fichier de locale JSON."""
    if lang not in _locale_cache:
        locale_path = os.path.join(os.path.dirname(__file__), "locales", f"{lang}.json")
        fallback_path = os.path.join(os.path.dirname(__file__), "locales", "fr.json")
        try:
            with open(locale_path, encoding="utf-8") as f:
                _locale_cache[lang] = json.load(f)
        except FileNotFoundError:
            # Fallback silencieux vers FR si la langue demandée n'existe pas
            try:
                with open(fallback_path, encoding="utf-8") as f:
                    _locale_cache[lang] = json.load(f)
            except Exception:
                _locale_cache[lang] = {}
    return _locale_cache[lang]


def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-me-in-production")
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

    init_db(app)

    from .controllers.component_controller import component_bp
    from .controllers.project_controller import project_bp
    app.register_blueprint(component_bp)
    app.register_blueprint(project_bp)

    # Injecte les variables globales disponibles dans tous les templates
    @app.context_processor
    def inject_globals():
        from .models.settings import SettingsModel
        try:
            app_name = SettingsModel.get("app_name", "StockEleK") or "StockEleK"
            lang     = SettingsModel.get("lang", "fr") or "fr"
        except Exception:
            app_name = "StockEleK"
            lang     = "fr"
        t = load_locale(lang)
        return {"app_name": app_name, "t": t, "lang": lang}

    return app
