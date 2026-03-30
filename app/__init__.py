import logging
import os
from flask import Flask
from .models.database import init_db

logger = logging.getLogger(__name__)


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
            app_name = SettingsModel.get("app_name", "StockElec") or "StockElec"
        except Exception:
            app_name = "StockElec"
        return {"app_name": app_name}

    return app
