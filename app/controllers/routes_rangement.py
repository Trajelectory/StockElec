import json
import logging
import re as _re

logger = logging.getLogger(__name__)

from flask import (
    request,
    jsonify,
    render_template,
    Response,
    current_app,
)

import requests as _requests

from ..models.settings import SettingsModel
from ..models.database import get_db
from .utils import _t
from . import component_bp


@component_bp.route("/rangement")
def rangement():
    db = get_db()

    # Config des plateaux (sauvegardée en settings)
    raw = SettingsModel.get("rangement_config", "")
    try:
        config = json.loads(raw) if raw else {"plateaux": [
            {"id": "A", "label": "Plateau A", "cols": 5, "rows": 4},
        ]}
    except Exception:
        config = {"plateaux": [{"id": "A", "label": "Plateau A", "cols": 5, "rows": 4}]}

    # Assignations case → composant
    raw_assign = SettingsModel.get("rangement_assign", "")
    try:
        assignments = json.loads(raw_assign) if raw_assign else {}
    except Exception:
        assignments = {}

    # Tailles des cases
    raw_sizes = SettingsModel.get("rangement_sizes", "")
    try:
        sizes = json.loads(raw_sizes) if raw_sizes else {}
    except Exception:
        sizes = {}

    # Tous les composants pour le sélecteur
    components = db.execute("""
        SELECT id, description, manufacture_part_number, lcsc_part_number,
               package, quantity, image_path, location
        FROM components ORDER BY description
    """).fetchall()

    esp32_url = SettingsModel.get("esp32_url", "").strip().rstrip("/")
    return render_template("components/rangement.html",
        config=config,
        assignments=assignments,
        sizes=sizes,
        components=[dict(c) for c in components],
        current_esp32_url=esp32_url,
    )


@component_bp.route("/rangement/save", methods=["POST"])
def rangement_save():
    data = request.get_json() or {}

    if "config" in data:
        SettingsModel.set("rangement_config", json.dumps(data["config"]))

    if "assignments" in data:
        raw = data["assignments"]
        # Valider : garder seulement les valeurs qui sont des entiers > 0
        new_assignments = {
            k: v for k, v in raw.items()
            if isinstance(v, int) and v > 0
            and _re.match(r'^[A-Za-z]{1,4}[0-9]{1,4}$', str(k))
        }

        db = get_db()

        # Lit les ANCIENNES assignations avant d'écraser
        raw_old = SettingsModel.get("rangement_assign", "")
        try:
            old_assignments = json.loads(raw_old) if raw_old else {}
        except Exception:
            old_assignments = {}

        # Validation : ne garder que les component_id qui existent réellement en base
        if new_assignments:
            all_ids = [v for v in new_assignments.values() if v]
            if all_ids:
                placeholders = ",".join("?" * len(all_ids))
                valid_ids = {
                    str(r[0]) for r in
                    db.execute(f"SELECT id FROM components WHERE id IN ({placeholders})", all_ids)
                    .fetchall()
                }
                new_assignments = {k: v for k, v in new_assignments.items()
                                   if not v or str(v) in valid_ids}

        # Sauvegarde les nouvelles
        SettingsModel.set("rangement_assign", json.dumps(new_assignments))

        # IDs des composants encore assignés dans le nouvel état
        assigned_ids = {str(v) for v in new_assignments.values() if v}

        # Vide le location des composants retirés
        try:
            for cell_id, comp_id in old_assignments.items():
                if comp_id and str(comp_id) not in assigned_ids:
                    db.execute("UPDATE components SET location='' WHERE id=?", (comp_id,))

            # Met à jour le location des composants assignés
            for cell_id, comp_id in new_assignments.items():
                if comp_id:
                    db.execute("UPDATE components SET location=? WHERE id=?",
                               (cell_id, comp_id))

            db.commit()
        except Exception:
            db.rollback()
            raise

    if "sizes" in data:
        SettingsModel.set("rangement_sizes", json.dumps(data["sizes"]))

    return jsonify({"ok": True})
