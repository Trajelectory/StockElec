"""
routes_projects.py — Routes Flask pour la gestion des projets maker.

20 routes Flask pures. La logique métier lourde (BOM, enrichissement,
images) est dans services/project_service.py.
"""

import csv
import io
import logging
import threading

from flask import (
    Blueprint, request, redirect, url_for, flash, jsonify,
    render_template, current_app, send_from_directory, Response,
)

from ..models.project import ProjectModel, STATUS_OPTIONS, TAG_OPTIONS, CHECKLIST_TEMPLATES
from ..models.component import ComponentModel
from ..models.movement import MovementModel
from ..models.database import get_db
from ..models.settings import SettingsModel
from ..services import lcsc_scraper
from ..services.project_service import (
    analyse_bom,
    save_project_image,
    generate_color_banner,
    delete_project_image,
)
from .utils import _t

logger = logging.getLogger(__name__)

project_bp = Blueprint("projects", __name__, url_prefix="/projects")


# ------------------------------------------------------------------ #
#  Liste des projets — Kanban
# ------------------------------------------------------------------ #

@project_bp.route("/")
def index():
    db       = get_db()
    projects = ProjectModel.get_all()
    avail = {}
    for p in projects:
        rows = db.execute("""
            SELECT pc.quantity, c.quantity AS stock_qty
            FROM project_components pc
            JOIN components c ON c.id = pc.component_id
            WHERE pc.project_id = ?
        """, (p.id,)).fetchall()
        if rows:
            n_ok = sum(1 for r in rows if r["stock_qty"] >= r["quantity"])
            avail[p.id] = {"n_ok": n_ok, "n_total": len(rows),
                           "pct": int(n_ok / len(rows) * 100)}
        else:
            avail[p.id] = {"n_ok": 0, "n_total": 0, "pct": 0}
    return render_template("projects/index.html", projects=projects, avail=avail)


# ------------------------------------------------------------------ #
#  Création
# ------------------------------------------------------------------ #

@project_bp.route("/new", methods=["GET", "POST"])
def new():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash(_t("msg.project_name_required"), "danger")
            return render_template("projects/form.html", project=None,
                                   status_options=STATUS_OPTIONS)
        image_path = save_project_image(request.files.get("image"))
        if not image_path:
            bc = request.form.get("banner_color", "").strip()
            if bc and bc.startswith("#"):
                image_path = generate_color_banner(bc)
        project_id = ProjectModel.create({
            "name":        name,
            "description": request.form.get("description"),
            "status":      request.form.get("status", "idea"),
            "image_path":  image_path,
            "tags":        request.form.getlist("tags"),
            "checklist":   [],
            "links":       [],
        })
        flash(_t("msg.project_created", name=name), "success")
        return redirect(url_for("projects.detail", project_id=project_id))
    existing = [{"id": p.id, "name": p.name} for p in ProjectModel.get_all()]
    return render_template("projects/form.html", project=None,
                           status_options=STATUS_OPTIONS, existing=existing,
                           tag_options=TAG_OPTIONS,
                           checklist_templates=CHECKLIST_TEMPLATES)


# ------------------------------------------------------------------ #
#  Détail
# ------------------------------------------------------------------ #

@project_bp.route("/<int:project_id>")
def detail(project_id):
    project = ProjectModel.get_by_id(project_id)
    if not project:
        flash(_t("msg.project_not_found"), "danger")
        return redirect(url_for("projects.index"))
    components     = ProjectModel.get_components(project_id)
    all_components = ComponentModel.get_all()
    journal        = MovementModel.get_recent(limit=20, project_id=project_id)
    return render_template(
        "projects/detail.html",
        project=project,
        components=components,
        all_components=all_components,
        journal=journal,
        tag_options=TAG_OPTIONS,
        checklist_templates=CHECKLIST_TEMPLATES,
    )


# ------------------------------------------------------------------ #
#  Édition
# ------------------------------------------------------------------ #

@project_bp.route("/<int:project_id>/edit", methods=["GET", "POST"])
def edit(project_id):
    project = ProjectModel.get_by_id(project_id)
    if not project:
        flash(_t("msg.project_not_found"), "danger")
        return redirect(url_for("projects.index"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash(_t("msg.project_name_missing"), "danger")
            return render_template("projects/form.html", project=project,
                                   status_options=STATUS_OPTIONS)
        new_image  = save_project_image(request.files.get("image"))
        image_path = new_image if new_image else project.image_path
        if request.form.get("delete_image") == "1":
            delete_project_image(project.image_path)
            image_path = None
        ProjectModel.update(project_id, {
            "name":        name,
            "description": request.form.get("description"),
            "status":      request.form.get("status", "idea"),
            "image_path":  image_path,
            "tags":        request.form.getlist("tags"),
            "checklist":   project.checklist,
            "links":       project.links,
            "notes":       project.notes,
        })
        flash(_t("msg.project_updated"), "success")
        return redirect(url_for("projects.detail", project_id=project_id))
    existing = [{"id": p.id, "name": p.name} for p in ProjectModel.get_all()
                if p.id != project_id]
    return render_template("projects/form.html", project=project,
                           status_options=STATUS_OPTIONS, existing=existing,
                           tag_options=TAG_OPTIONS,
                           checklist_templates=CHECKLIST_TEMPLATES)


# ------------------------------------------------------------------ #
#  Suppression
# ------------------------------------------------------------------ #

@project_bp.route("/<int:project_id>/delete", methods=["POST"])
def delete(project_id):
    project = ProjectModel.get_by_id(project_id)
    if project and project.image_path:
        delete_project_image(project.image_path)
    ProjectModel.delete(project_id)
    flash(_t("msg.project_deleted"), "success")
    return redirect(url_for("projects.index"))


# ------------------------------------------------------------------ #
#  Images projet
# ------------------------------------------------------------------ #

@project_bp.route("/project-images/<path:filename>")
def project_image(filename):
    images_dir = current_app.instance_path
    return send_from_directory(
        str(current_app.instance_path) + "/project_images", filename
    )


@project_bp.route("/<int:project_id>/upload-note-image", methods=["POST"])
def upload_note_image(project_id):
    """Upload une image depuis l'éditeur de notes, retourne l'URL."""
    project = ProjectModel.get_by_id(project_id)
    if not project:
        return jsonify({"ok": False, "error": "Projet introuvable"}), 404
    filename = save_project_image(request.files.get("image"))
    if not filename:
        return jsonify({"ok": False, "error": "Fichier invalide"}), 400
    url = url_for("projects.project_image", filename=filename)
    return jsonify({"ok": True, "url": url, "filename": filename})


# ------------------------------------------------------------------ #
#  Mises à jour AJAX (notes, checklist, liens, statut)
# ------------------------------------------------------------------ #

@project_bp.route("/<int:project_id>/notes", methods=["POST"])
def update_notes(project_id):
    project = ProjectModel.get_by_id(project_id)
    if not project:
        return jsonify({"ok": False, "error": "Projet introuvable"}), 404
    notes = (request.get_json() or {}).get("notes", "")
    ProjectModel.update(project_id, {
        "name": project.name, "description": project.description or "",
        "status": project.status, "image_path": project.image_path,
        "tags": project.tags, "checklist": project.checklist,
        "links": project.links, "notes": notes,
    })
    return jsonify({"ok": True})


@project_bp.route("/<int:project_id>/checklist", methods=["POST"])
def update_checklist(project_id):
    project = ProjectModel.get_by_id(project_id)
    if not project:
        return jsonify({"ok": False, "error": "Projet introuvable"}), 404
    checklist = (request.get_json() or {}).get("checklist", [])
    ProjectModel.update(project_id, {
        "name": project.name, "description": project.description or "",
        "status": project.status, "image_path": project.image_path,
        "tags": project.tags, "checklist": checklist,
        "links": project.links, "notes": project.notes,
    })
    done  = sum(1 for i in checklist if i.get("done"))
    total = len(checklist)
    pct   = int(done / total * 100) if total else 0
    return jsonify({"ok": True, "done": done, "total": total, "pct": pct})


@project_bp.route("/<int:project_id>/links", methods=["POST"])
def update_links(project_id):
    project = ProjectModel.get_by_id(project_id)
    if not project:
        return jsonify({"ok": False, "error": "Projet introuvable"}), 404
    links = (request.get_json() or {}).get("links", [])
    ProjectModel.update(project_id, {
        "name": project.name, "description": project.description or "",
        "status": project.status, "image_path": project.image_path,
        "tags": project.tags, "checklist": project.checklist,
        "links": links, "notes": project.notes,
    })
    return jsonify({"ok": True, "count": len(links)})


@project_bp.route("/<int:project_id>/status", methods=["POST"])
def update_status(project_id):
    data   = request.get_json() or {}
    status = data.get("status", "").strip()
    if status not in STATUS_OPTIONS:
        return jsonify({"ok": False, "error": "Statut invalide"}), 400
    project = ProjectModel.get_by_id(project_id)
    if not project:
        return jsonify({"ok": False, "error": "Projet introuvable"}), 404
    ProjectModel.update(project_id, {
        "name": project.name, "description": project.description or "",
        "status": status, "image_path": project.image_path,
        "tags": project.tags, "checklist": project.checklist,
        "links": project.links, "notes": project.notes,
    })
    return jsonify({"ok": True, "status": status})


# ------------------------------------------------------------------ #
#  Gestion des composants du projet
# ------------------------------------------------------------------ #

@project_bp.route("/<int:project_id>/components/add", methods=["POST"])
def add_component(project_id):
    project = ProjectModel.get_by_id(project_id)
    if not project:
        return jsonify({"ok": False, "error": _t("msg.err_project_not_found")}), 404
    component_id = request.form.get("component_id", type=int)
    quantity     = request.form.get("quantity", 1, type=int)
    notes        = request.form.get("notes", "").strip() or None
    if not component_id or quantity < 1:
        flash(_t("msg.comp_qty_invalid"), "danger")
        return redirect(url_for("projects.detail", project_id=project_id))
    ProjectModel.add_component(project_id, component_id, quantity, notes)
    flash(_t("msg.comp_added_project"), "success")
    return redirect(url_for("projects.detail", project_id=project_id))


@project_bp.route("/<int:project_id>/components/<int:component_id>/remove", methods=["POST"])
def remove_component(project_id, component_id):
    ProjectModel.remove_component(project_id, component_id)
    flash(_t("msg.comp_removed_project"), "success")
    return redirect(url_for("projects.detail", project_id=project_id))


@project_bp.route("/<int:project_id>/components/<int:component_id>/use", methods=["POST"])
def use_component(project_id, component_id):
    """Débite le stock et enregistre un mouvement."""
    quantity = request.form.get("quantity", 1, type=int)
    result   = ComponentModel.adjust_quantity(component_id, -quantity)
    if result["ok"]:
        try:
            MovementModel.record(component_id, "project_use", quantity,
                                 note=f"Projet #{project_id}", project_id=project_id)
        except Exception as e:
            logger.debug("Ignored: %s", e)
        return jsonify({"ok": True, "new_qty": result["new_qty"]})
    return jsonify({"ok": False, "error": result["error"]}), 400


@project_bp.route("/<int:project_id>/components/<int:component_id>/return", methods=["POST"])
def return_component(project_id, component_id):
    """Recrédite le stock et enregistre un mouvement."""
    quantity = request.form.get("quantity", 1, type=int)
    result   = ComponentModel.adjust_quantity(component_id, +quantity)
    if result["ok"]:
        try:
            MovementModel.record(component_id, "project_return", quantity,
                                 note=f"Retour projet #{project_id}", project_id=project_id)
        except Exception as e:
            logger.debug("Ignored: %s", e)
        return jsonify({"ok": True, "new_qty": result["new_qty"]})
    return jsonify({"ok": False, "error": result["error"]}), 400


# ------------------------------------------------------------------ #
#  Mode kit — débit automatique
# ------------------------------------------------------------------ #

@project_bp.route("/<int:project_id>/kit", methods=["POST"])
def prepare_kit(project_id):
    """Débite du stock tous les composants disponibles du projet."""
    project = ProjectModel.get_by_id(project_id)
    if not project:
        return jsonify({"ok": False, "error": _t("msg.project_not_found")}), 404

    components = ProjectModel.get_components(project_id)
    debited    = 0
    details    = []
    for pc in components:
        available = min(pc.stock_quantity, pc.quantity)
        if available <= 0:
            continue
        result = ComponentModel.adjust_quantity(pc.component_id, -available)
        if result["ok"]:
            debited += 1
            details.append({"id": pc.component_id, "new_qty": result["new_qty"],
                             "desc": pc.description or pc.lcsc_part_number})
            try:
                MovementModel.record(pc.component_id, "project_use", available,
                                     note=f"Kit — Projet #{project_id}",
                                     project_id=project_id)
            except Exception as e:
                logger.debug("Ignored: %s", e)

    if debited == 0:
        return jsonify({"ok": False, "error": _t("projects.kit_none")})
    return jsonify({"ok": True, "debited": debited, "details": details,
                    "message": _t("projects.kit_ok", n=debited)})


# ------------------------------------------------------------------ #
#  Export BOM CSV
# ------------------------------------------------------------------ #

@project_bp.route("/<int:project_id>/export-bom")
def export_bom(project_id):
    project = ProjectModel.get_by_id(project_id)
    if not project:
        flash(_t("msg.project_not_found"), "danger")
        return redirect(url_for("projects.index"))

    components = ProjectModel.get_components(project_id)
    output     = io.StringIO()
    writer     = csv.writer(output)
    writer.writerow([
        _t("msg.csv_col_description"), "LCSC", "Mouser", "DigiKey",
        _t("msg.csv_col_manufacturer"), _t("msg.csv_col_package"),
        _t("msg.csv_col_qty_needed"), _t("msg.csv_col_in_stock"),
        _t("msg.csv_col_unit_price2"), _t("msg.csv_col_total_price2"),
    ])
    for pc in components:
        total = round(pc.unit_price * pc.quantity, 4) if pc.unit_price else ""
        writer.writerow([
            pc.description or "",
            pc.lcsc_part_number or "",
            pc.mouser_part_number or "",
            pc.digikey_part_number or "",
            pc.manufacturer or "",
            pc.package or "",
            pc.quantity,
            pc.stock_quantity,
            pc.unit_price or "",
            total,
        ])

    safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in project.name)
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=BOM_{safe_name}.csv"},
    )


# ------------------------------------------------------------------ #
#  Import BOM KiCad
# ------------------------------------------------------------------ #

@project_bp.route("/<int:project_id>/import-bom", methods=["GET", "POST"])
def import_bom(project_id):
    project = ProjectModel.get_by_id(project_id)
    if not project:
        flash(_t("msg.project_not_found"), "danger")
        return redirect(url_for("projects.index"))

    if request.method == "POST":
        file = request.files.get("bom_file")
        if not file or file.filename == "":
            flash(_t("msg.bom_no_file"), "danger")
            return redirect(url_for("projects.import_bom", project_id=project_id))
        if not file.filename.lower().endswith(".csv"):
            flash(_t("msg.bom_not_csv"), "danger")
            return redirect(url_for("projects.import_bom", project_id=project_id))

        raw = file.stream.read().decode("utf-8-sig")
        sep = ";" if raw.count(";") > raw.count(",") else ","
        import csv as csvmod
        reader = csvmod.DictReader(io.StringIO(raw, newline=None), delimiter=sep)
        rows   = list(reader)

        if not rows:
            flash(_t("msg.bom_empty"), "danger")
            return redirect(url_for("projects.import_bom", project_id=project_id))

        report = analyse_bom(rows, project_id)
        if report is None:
            flash(
                "Impossible de trouver une colonne LCSC ou Mouser dans ce fichier. "
                "Colonnes détectées : " + ", ".join(rows[0].keys()),
                "danger",
            )
            return redirect(url_for("projects.import_bom", project_id=project_id))

        return render_template("projects/bom_report.html",
                               project=project, report=report,
                               filename=file.filename)

    return render_template("projects/import_bom.html", project=project)


@project_bp.route("/<int:project_id>/import-bom/create-missing", methods=["POST"])
def create_missing(project_id):
    """Crée un composant manquant dans le stock et lance l'enrichissement LCSC."""
    lcsc = request.form.get("lcsc", "").strip().upper()
    desc = request.form.get("description", lcsc)
    qty  = request.form.get("quantity", 0, type=int)

    if not lcsc:
        flash(_t("msg.bom_lcsc_missing"), "danger")
        return redirect(url_for("projects.detail", project_id=project_id))

    db       = get_db()
    existing = db.execute(
        "SELECT id FROM components WHERE lcsc_part_number=?", (lcsc,)
    ).fetchone()

    if existing:
        comp_id = existing["id"]
        flash(_t("msg.bom_already_exists", ref=lcsc), "info")
    else:
        comp_id = ComponentModel.create({
            "lcsc_part_number": lcsc,
            "description":      "",
            "description_long": desc or "",
            "quantity":         qty,
            "min_stock":        0,
        })
        flash(_t("msg.bom_created", ref=lcsc), "success")
        _app = current_app._get_current_object()
        def _enrich():
            with _app.app_context():
                try:
                    info = lcsc_scraper.enrich_component(lcsc)
                    if info:
                        ComponentModel.apply_enrichment(comp_id, info)
                except Exception as e:
                    logger.debug("Ignored: %s", e)
        threading.Thread(target=_enrich, daemon=True).start()

    try:
        ProjectModel.add_component(project_id, comp_id, max(1, qty))
    except Exception as e:
        logger.debug("Ignored: %s", e)

    return redirect(url_for("projects.detail", project_id=project_id))


@project_bp.route("/<int:project_id>/import-bom/apply", methods=["POST"])
def apply_bom(project_id):
    project = ProjectModel.get_by_id(project_id)
    if not project:
        flash(_t("msg.project_not_found"), "danger")
        return redirect(url_for("projects.index"))

    db    = get_db()
    added = 0

    # ── 1. Composants existants cochés ──────────────────────────────
    component_ids = request.form.getlist("component_id")
    quantities    = request.form.getlist("quantity")
    for comp_id, qty in zip(component_ids, quantities):
        try:
            ProjectModel.add_component(project_id, int(comp_id), int(qty))
            added += 1
        except Exception as e:
            logger.debug("Ignored: %s", e)

    # ── 2. Composants manquants cochés → créer + enrichir ───────────
    missing_ids     = request.form.getlist("missing_id")
    to_enrich       = []
    to_enrich_mouser  = []
    to_enrich_digikey = []

    # Index en mémoire pour éviter N+1 queries
    all_rows    = db.execute(
        "SELECT id, lcsc_part_number, mouser_part_number, digikey_part_number FROM components"
    ).fetchall()
    idx_lcsc    = {r["lcsc_part_number"]:    r for r in all_rows if r["lcsc_part_number"]}
    idx_mouser  = {r["mouser_part_number"]:  r for r in all_rows if r["mouser_part_number"]}
    idx_digikey = {r["digikey_part_number"]: r for r in all_rows if r["digikey_part_number"]}

    for idx in missing_ids:
        qty         = request.form.get(f"missing_qty_{idx}",     0,  type=int)
        desc        = request.form.get(f"missing_desc_{idx}",    "")
        lcsc        = request.form.get(f"missing_lcsc_{idx}",    "").strip().upper()
        mouser_ref  = request.form.get(f"missing_mouser_{idx}",  "").strip()
        digikey_ref = request.form.get(f"missing_digikey_{idx}", "").strip()

        if not lcsc and not mouser_ref and not digikey_ref:
            continue

        existing = (idx_lcsc.get(lcsc) or idx_mouser.get(mouser_ref)
                    or idx_digikey.get(digikey_ref))

        if existing:
            comp_id = existing["id"]
            updates = {}
            if lcsc       and not existing["lcsc_part_number"]:    updates["lcsc_part_number"]    = lcsc
            if mouser_ref and not existing["mouser_part_number"]:  updates["mouser_part_number"]  = mouser_ref
            if digikey_ref and not existing["digikey_part_number"]: updates["digikey_part_number"] = digikey_ref
            if updates:
                fields = ", ".join(f"{k} = ?" for k in updates)
                try:
                    db.execute(f"UPDATE components SET {fields} WHERE id = ?",
                               list(updates.values()) + [comp_id])
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
        else:
            comp_data = {"description": "", "description_long": desc or "",
                         "quantity": 0, "min_stock": 0}
            if lcsc:        comp_data["lcsc_part_number"]    = lcsc
            if mouser_ref:  comp_data["mouser_part_number"]  = mouser_ref
            if digikey_ref: comp_data["digikey_part_number"] = digikey_ref
            comp_id = ComponentModel.create(comp_data)
            if lcsc:        to_enrich.append((comp_id, lcsc))
            if mouser_ref:  to_enrich_mouser.append((comp_id, mouser_ref))
            if digikey_ref: to_enrich_digikey.append((comp_id, digikey_ref))

        try:
            ProjectModel.add_component(project_id, comp_id, max(1, qty))
            added += 1
        except Exception as e:
            logger.debug("Ignored: %s", e)

    # ── Enrichissement en arrière-plan ──────────────────────────────
    _app = current_app._get_current_object()

    if to_enrich:
        def _enrich_lcsc():
            with _app.app_context():
                for cid, ref in to_enrich:
                    try:
                        info = lcsc_scraper.enrich_component(ref)
                        if info:
                            ComponentModel.apply_enrichment(cid, info)
                    except Exception as e:
                        logger.debug("Ignored: %s", e)
        threading.Thread(target=_enrich_lcsc, daemon=True).start()
        flash(_t("msg.bom_enrich_started", n=len(to_enrich)), "info")

    if to_enrich_mouser:
        def _enrich_mouser():
            with _app.app_context():
                api_key = SettingsModel.get("mouser_api_key", "")
                if not api_key:
                    return
                from ..services import mouser_scraper as _ms
                for cid, ref in to_enrich_mouser:
                    try:
                        info = _ms.enrich_component(ref, api_key)
                        if info:
                            ComponentModel.apply_enrichment(cid, info)
                    except Exception as e:
                        logger.debug("Ignored: %s", e)
        threading.Thread(target=_enrich_mouser, daemon=True).start()

    if to_enrich_digikey:
        def _enrich_digikey():
            with _app.app_context():
                client_id     = SettingsModel.get("digikey_client_id", "")
                client_secret = SettingsModel.get("digikey_client_secret", "")
                if not client_id or not client_secret:
                    return
                from ..services import digikey_scraper as _dk
                for cid, ref in to_enrich_digikey:
                    try:
                        info = _dk.enrich_component(ref, client_id, client_secret)
                        if info:
                            ComponentModel.apply_enrichment(cid, info)
                    except Exception as e:
                        logger.debug("Ignored: %s", e)
        threading.Thread(target=_enrich_digikey, daemon=True).start()

    flash(_t("msg.bom_added", n=added), "success")
    return redirect(url_for("projects.detail", project_id=project_id))
