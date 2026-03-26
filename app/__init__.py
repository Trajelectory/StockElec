import logging
from flask import Flask
from .models.database import init_db

logger = logging.getLogger(__name__)


def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["SECRET_KEY"] = "change-me-in-production"
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

    init_db(app)

    from .controllers.component_controller import component_bp
    from .controllers.project_controller import project_bp
    app.register_blueprint(component_bp)
    app.register_blueprint(project_bp)

    with app.app_context():
        try:
            from .models.settings import SettingsModel
            from .services import lcsc_api
            key    = SettingsModel.get("lcsc_api_key")
            secret = SettingsModel.get("lcsc_api_secret")
            if key and secret:
                lcsc_api.reload_config(key, secret)
        except Exception:
            pass

    return app
