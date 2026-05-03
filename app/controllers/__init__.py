from flask import Blueprint

component_bp = Blueprint("components", __name__)

from . import routes_stock          # noqa: F401,E402
from . import routes_import_export  # noqa: F401,E402
from . import routes_enrichment     # noqa: F401,E402
from . import routes_labels         # noqa: F401,E402
from . import routes_settings       # noqa: F401,E402
from . import routes_led            # noqa: F401,E402
from . import routes_misc           # noqa: F401,E402
from . import routes_rangement      # noqa: F401,E402

from .routes_api import api_bp
