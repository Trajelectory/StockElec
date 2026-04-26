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

    # Composants assignés uniquement (pour l'affichage de la grille)
    assigned_ids = [v for v in assignments.values() if v]
    if assigned_ids:
        placeholders = ",".join("?" * len(assigned_ids))
        assigned_rows = db.execute(f"""
            SELECT id, description, manufacture_part_number, lcsc_part_number,
                   package, quantity, image_path, location
            FROM components
            WHERE id IN ({placeholders})
            ORDER BY description
        """, assigned_ids).fetchall()
    else:
        assigned_rows = []

    esp32_url = SettingsModel.get("esp32_url", "").strip().rstrip("/")

    # Couleurs LED par catégorie
    led_colors = {
        "resistor":      SettingsModel.get("led_color_resistor",       "#f97316"),
        "capacitor":     SettingsModel.get("led_color_capacitor",       "#3b82f6"),
        "inductor":      SettingsModel.get("led_color_inductor",        "#8b5cf6"),
        "transistor":    SettingsModel.get("led_color_transistor",      "#06b6d4"),
        "diode":         SettingsModel.get("led_color_diode",           "#f59e0b"),
        "led":           SettingsModel.get("led_color_led",             "#fbbf24"),
        "amplifier":     SettingsModel.get("led_color_amplifier",       "#10b981"),
        "ic":            SettingsModel.get("led_color_ic",              "#6366f1"),
        "connector":     SettingsModel.get("led_color_connector",       "#ec4899"),
        "switch":        SettingsModel.get("led_color_switch",          "#14b8a6"),
        "crystal":       SettingsModel.get("led_color_crystal",         "#a78bfa"),
        "sensor":        SettingsModel.get("led_color_sensor",          "#84cc16"),
        "power":         SettingsModel.get("led_color_power",           "#f43f5e"),
        "rf":            SettingsModel.get("led_color_rf",              "#38bdf8"),
    }

    # Stats par plateau
    plateau_stats = {}
    for p in config.get("plateaux", []):
        pid   = p["id"]
        total = p["cols"] * p["rows"]
        filled = sum(1 for k, v in assignments.items()
                     if k.startswith(pid) and v and
                     not any(k[len(pid):].isdigit() is False for _ in [1]))
        # Valeur totale des composants sur ce plateau
        pids_ids = [v for k, v in assignments.items()
                    if k.startswith(pid) and v]
        plateau_stats[pid] = {"total": total, "filled": filled}

    # Cellules absorbées (calculées côté Python pour le template Jinja)
    absorbed_cells = set()
    for p in config.get("plateaux", []):
        pid  = p["id"]
        cols = p["cols"]
        rows = p["rows"]
        for cell_id, size in sizes.items():
            if not cell_id.startswith(pid): continue
            suffix = cell_id[len(pid):]
            if not suffix.isdigit(): continue
            idx = int(suffix)
            if idx < 1 or idx > cols * rows: continue
            sw, sh = map(int, size.split("x")) if "x" in size else (1, 1)
            if sw == 1 and sh == 1: continue
            col = (idx - 1) % cols
            row = (idx - 1) // cols
            for r in range(row, row + sh):
                for c in range(col, col + sw):
                    if r == row and c == col: continue
                    aidx = r * cols + c + 1
                    absorbed_cells.add(f"{pid}{aidx}")

    # Plateau actif (mémorisé via ?pid= après reload)
    active_pid = request.args.get("pid", "").strip().upper()
    if not active_pid or active_pid not in {p["id"] for p in config.get("plateaux", [])}:
        active_pid = config["plateaux"][0]["id"] if config.get("plateaux") else ""

    n_placed   = len([v for v in assignments.values() if v])
    n_total    = db.execute("SELECT COUNT(*) FROM components").fetchone()[0]
    n_unplaced = n_total - n_placed

    return render_template("components/rangement.html",
        config=config,
        assignments=assignments,
        sizes=sizes,
        components=[dict(c) for c in assigned_rows],
        current_esp32_url=esp32_url,
        led_colors=led_colors,
        plateau_stats=plateau_stats,
        absorbed_cells=absorbed_cells,
        active_pid=active_pid,
        n_placed=n_placed,
        n_total=n_total,
        n_unplaced=n_unplaced,
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


@component_bp.route("/api/components/for-rangement")
def api_components_for_rangement():
    """Charge tous les composants pour le popup de sélection du rangement.
    Appelé en AJAX au premier clic sur une case — pas au chargement de la page.
    """
    db = get_db()
    rows = db.execute("""
        SELECT id, description, manufacture_part_number, lcsc_part_number,
               package, quantity, image_path, location
        FROM components ORDER BY description
    """).fetchall()
    return jsonify([dict(r) for r in rows])
