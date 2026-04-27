import json
import logging
import re as _re

logger = logging.getLogger(__name__)

from flask import request, jsonify, render_template, redirect, url_for, flash

from ..models.atelier  import AtelierModel
from ..models.settings import SettingsModel
from ..models.database import get_db
from .utils import _t
from . import component_bp


def _get_ateliers():
    ateliers = AtelierModel.get_all()
    if not ateliers:
        AtelierModel.create("principal", "Atelier principal", "🔧", "#7c3aed")
        ateliers = AtelierModel.get_all()
    return ateliers


def _build_context(atelier: dict, db):
    aid = atelier["id"]
    config      = AtelierModel.get_rangement_config(aid)
    assignments = AtelierModel.get_rangement_assign(aid)
    sizes       = AtelierModel.get_rangement_sizes(aid)

    assigned_ids = [v for v in assignments.values() if v]
    if assigned_ids:
        ph = ",".join("?" * len(assigned_ids))
        assigned_rows = db.execute(f"""
            SELECT id, description, manufacture_part_number, lcsc_part_number,
                   package, quantity, image_path, location
            FROM components WHERE id IN ({ph}) ORDER BY description
        """, assigned_ids).fetchall()
    else:
        assigned_rows = []

    esp32_url = (atelier.get("esp32_url") or SettingsModel.get("esp32_url","")).strip().rstrip("/")

    led_colors = {k: SettingsModel.get(f"led_color_{k}", v) for k, v in {
        "resistor":"#f97316","capacitor":"#3b82f6","inductor":"#8b5cf6",
        "transistor":"#06b6d4","diode":"#f59e0b","led":"#fbbf24",
        "amplifier":"#10b981","ic":"#6366f1","connector":"#ec4899",
        "switch":"#14b8a6","crystal":"#a78bfa","sensor":"#84cc16",
        "power":"#f43f5e","rf":"#38bdf8",
    }.items()}

    plateau_stats = {}
    for p in config.get("plateaux",[]):
        pid   = p["id"]
        total = p["cols"] * p["rows"]
        filled = sum(1 for k,v in assignments.items() if k.startswith(pid) and v)
        plateau_stats[pid] = {"total":total,"filled":filled}

    absorbed_cells = set()
    for p in config.get("plateaux",[]):
        pid, cols, rows = p["id"], p["cols"], p["rows"]
        for cell_id, size in sizes.items():
            if not cell_id.startswith(pid): continue
            suffix = cell_id[len(pid):]
            if not suffix.isdigit(): continue
            idx = int(suffix)
            if idx < 1 or idx > cols*rows: continue
            sw, sh = map(int, size.split("x")) if "x" in size else (1,1)
            if sw==1 and sh==1: continue
            col = (idx-1)%cols; row = (idx-1)//cols
            for r in range(row, row+sh):
                for c in range(col, col+sw):
                    if r==row and c==col: continue
                    absorbed_cells.add(f"{pid}{r*cols+c+1}")

    active_pid = request.args.get("pid","").strip().upper()
    if not active_pid or active_pid not in {p["id"] for p in config.get("plateaux",[])}:
        active_pid = config["plateaux"][0]["id"] if config.get("plateaux") else ""

    n_placed = len([v for v in assignments.values() if v])
    n_total  = db.execute("SELECT COUNT(*) FROM components").fetchone()[0]

    return dict(config=config, assignments=assignments, sizes=sizes,
                components=[dict(c) for c in assigned_rows],
                current_esp32_url=esp32_url, led_colors=led_colors,
                plateau_stats=plateau_stats, absorbed_cells=absorbed_cells,
                active_pid=active_pid,
                n_placed=n_placed, n_total=n_total, n_unplaced=n_total-n_placed)


@component_bp.route("/rangement")
def rangement():
    ateliers = _get_ateliers()
    return redirect(url_for("components.rangement_atelier", atelier_id=ateliers[0]["id"]))


@component_bp.route("/rangement/<atelier_id>")
def rangement_atelier(atelier_id):
    db       = get_db()
    ateliers = _get_ateliers()
    atelier  = AtelierModel.get_or_first(atelier_id)
    if not atelier:
        flash("Atelier introuvable.", "danger")
        return redirect(url_for("components.stock"))
    ctx = _build_context(atelier, db)
    return render_template("components/rangement.html",
                           atelier=atelier, ateliers=ateliers, **ctx)


@component_bp.route("/rangement/<atelier_id>/save", methods=["POST"])
def rangement_save(atelier_id):
    data    = request.get_json() or {}
    atelier = AtelierModel.get(atelier_id)
    if not atelier:
        return jsonify({"ok":False,"error":"Atelier introuvable"}), 404

    if "config" in data:
        AtelierModel.set_rangement_config(atelier_id, data["config"])

    if "assignments" in data:
        raw = data["assignments"]
        new_assign = {k: v for k,v in raw.items()
                      if isinstance(v,int) and v>0
                      and _re.match(r'^[A-Za-z]{1,4}[0-9]{1,4}$', str(k))}
        db = get_db()
        if new_assign:
            all_ids = [v for v in new_assign.values() if v]
            if all_ids:
                ph = ",".join("?"*len(all_ids))
                valid_ids = {str(r[0]) for r in
                             db.execute(f"SELECT id FROM components WHERE id IN ({ph})",all_ids).fetchall()}
                new_assign = {k:v for k,v in new_assign.items() if not v or str(v) in valid_ids}

        old_assign = AtelierModel.get_rangement_assign(atelier_id)
        AtelierModel.set_rangement_assign(atelier_id, new_assign)

        assigned_ids = {str(v) for v in new_assign.values() if v}
        try:
            for cell_id, comp_id in old_assign.items():
                if comp_id and str(comp_id) not in assigned_ids:
                    db.execute("UPDATE components SET location='' WHERE id=?", (comp_id,))
            for cell_id, comp_id in new_assign.items():
                if comp_id:
                    db.execute("UPDATE components SET location=? WHERE id=?",
                               (f"{atelier_id}:{cell_id}", comp_id))
            db.commit()
        except Exception:
            db.rollback()
            raise

    if "sizes" in data:
        AtelierModel.set_rangement_sizes(atelier_id, data["sizes"])

    return jsonify({"ok":True})


@component_bp.route("/api/components/for-rangement")
def api_components_for_rangement():
    db = get_db()
    rows = db.execute("""
        SELECT id, description, manufacture_part_number, lcsc_part_number,
               package, quantity, image_path, location
        FROM components ORDER BY description
    """).fetchall()
    return jsonify([dict(r) for r in rows])


@component_bp.route("/api/ateliers")
def api_ateliers():
    return jsonify(AtelierModel.get_all())


@component_bp.route("/ateliers/create", methods=["POST"])
def atelier_create():
    data  = request.get_json() or {}
    aid   = _re.sub(r'[^a-z0-9_]', '', data.get("id","").lower().strip())[:20]
    name  = data.get("name","Nouvel atelier").strip()[:60]
    emoji = data.get("emoji","📦")[:4]
    color = data.get("color","#7c3aed")
    if not aid or not name:
        return jsonify({"ok":False,"error":"ID et nom requis"}), 400
    if AtelierModel.get(aid):
        return jsonify({"ok":False,"error":"Cet ID existe déjà"}), 409
    ok = AtelierModel.create(aid, name, emoji, color)
    return jsonify({"ok":ok,"id":aid})


@component_bp.route("/ateliers/<atelier_id>/update", methods=["POST"])
def atelier_update(atelier_id):
    data = request.get_json() or {}
    allowed = {"name","emoji","color","esp32_url","esp32_token","esp32_duration","esp32_offsets","position"}
    fields  = {k: v for k,v in data.items() if k in allowed}
    ok = AtelierModel.update(atelier_id, **fields)
    return jsonify({"ok":ok})


@component_bp.route("/ateliers/<atelier_id>/delete", methods=["POST"])
def atelier_delete(atelier_id):
    ateliers = AtelierModel.get_all()
    if len(ateliers) <= 1:
        return jsonify({"ok":False,"error":"Impossible de supprimer le seul atelier"}), 400
    ok = AtelierModel.delete(atelier_id)
    return jsonify({"ok":ok})
