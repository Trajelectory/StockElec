# TODO M5 : Ce contrôleur (991 lignes) mériterait d'être découpé en :
#   - routes_projects.py  : uniquement les routes Flask
#   - services/project_service.py : logique métier (BOM, enrichissement, stats)
#   Reporté — à faire avec une suite de tests pour éviter les régressions.

import os
import uuid
import threading
from flask import Blueprint, request, redirect, url_for, flash, jsonify, render_template, current_app

from ..models.project import ProjectModel, STATUS_OPTIONS, TAG_OPTIONS, CHECKLIST_TEMPLATES
from ..models.component import ComponentModel
from ..models.movement import MovementModel
from ..models.database import get_db
from ..models.settings import SettingsModel
from ..services import lcsc_scraper, mouser_scraper, digikey_scraper
from .utils import _t

project_bp = Blueprint("projects", __name__, url_prefix="/projects")


# ------------------------------------------------------------------ #
#  Liste des projets
# ------------------------------------------------------------------ #

_ALLOWED_COMP_UPDATE_COLS = {
    "description", "description_long", "manufacturer", "manufacture_part_number",
    "package", "rohs", "datasheet_url", "lcsc_part_number", "mouser_part_number",
    "digikey_part_number", "source_url", "unit_price", "image_path",
    "symbol_png", "footprint_png", "quantity", "min_stock", "location", "notes",
}

@project_bp.route("/")


def index():
    db       = get_db()
    projects = ProjectModel.get_all()
    # Calcul disponibilité par projet (n_ok / n_total)
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
            return render_template("projects/form.html", project=None, status_options=STATUS_OPTIONS)
        image_path = _save_project_image(request.files.get("image"))
        if not image_path:
            bc = request.form.get("banner_color", "").strip()
            if bc and bc.startswith("#"):
                image_path = _generate_color_banner(bc)
        raw_tags = request.form.getlist("tags")
        project_id = ProjectModel.create({
            "name":        name,
            "description": request.form.get("description"),
            "status":      request.form.get("status", "idée"),
            "image_path":  image_path,
            "tags":        raw_tags,
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
    project    = ProjectModel.get_by_id(project_id)
    if not project:
        flash(_t("msg.project_not_found"), "danger")
        return redirect(url_for("projects.index"))
    components     = ProjectModel.get_components(project_id)
    all_components = ComponentModel.get_all()
    # Journal d'activité (mouvements liés à ce projet)
    journal = MovementModel.get_recent(limit=20, project_id=project_id)
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
            return render_template("projects/form.html", project=project, status_options=STATUS_OPTIONS)
        # Image : nouvelle upload ou conservation de l'existante
        new_image = _save_project_image(request.files.get("image"))
        image_path = new_image if new_image else project.image_path
        # Option suppression
        if request.form.get("delete_image") == "1":
            _delete_project_image(project.image_path)
            image_path = None
        raw_tags = request.form.getlist("tags")
        ProjectModel.update(project_id, {
            "name":        name,
            "description": request.form.get("description"),
            "status":      request.form.get("status", "idée"),
            "image_path":  image_path,
            "tags":        raw_tags,
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

@project_bp.route("/<int:project_id>/upload-note-image", methods=["POST"])
def upload_note_image(project_id):
    """Upload une image depuis l'éditeur de notes, retourne l'URL."""
    project = ProjectModel.get_by_id(project_id)
    if not project:
        return jsonify({"ok": False, "error": "Projet introuvable"}), 404
    file = request.files.get("image")
    filename = _save_project_image(file)
    if not filename:
        return jsonify({"ok": False, "error": "Fichier invalide"}), 400
    url = url_for("projects.project_image", filename=filename)
    return jsonify({"ok": True, "url": url, "filename": filename})


@project_bp.route("/<int:project_id>/notes", methods=["POST"])
def update_notes(project_id):
    """Sauvegarde les notes libres via AJAX (auto-save)."""
    project = ProjectModel.get_by_id(project_id)
    if not project:
        return jsonify({"ok": False, "error": "Projet introuvable"}), 404
    data  = request.get_json() or {}
    notes = data.get("notes", "")
    ProjectModel.update(project_id, {
        "name":        project.name,
        "description": project.description or "",
        "status":      project.status,
        "image_path":  project.image_path,
        "tags":        project.tags,
        "checklist":   project.checklist,
        "links":       project.links,
        "notes":       notes,
    })
    return jsonify({"ok": True})


@project_bp.route("/<int:project_id>/checklist", methods=["POST"])
def update_checklist(project_id):
    """Met à jour la checklist via AJAX."""
    project = ProjectModel.get_by_id(project_id)
    if not project:
        return jsonify({"ok": False, "error": "Projet introuvable"}), 404
    data = request.get_json() or {}
    checklist = data.get("checklist", [])
    ProjectModel.update(project_id, {
        "name": project.name, "description": project.description or "",
        "status": project.status, "image_path": project.image_path,
        "tags": project.tags, "checklist": checklist, "links": project.links,
        "notes": project.notes,
    })
    done  = sum(1 for i in checklist if i.get("done"))
    total = len(checklist)
    pct   = int(done / total * 100) if total else 0
    return jsonify({"ok": True, "done": done, "total": total, "pct": pct})


@project_bp.route("/<int:project_id>/links", methods=["POST"])
def update_links(project_id):
    """Met à jour les liens via AJAX."""
    project = ProjectModel.get_by_id(project_id)
    if not project:
        return jsonify({"ok": False, "error": "Projet introuvable"}), 404
    data  = request.get_json() or {}
    links = data.get("links", [])
    ProjectModel.update(project_id, {
        "name": project.name, "description": project.description or "",
        "status": project.status, "image_path": project.image_path,
        "tags": project.tags, "checklist": project.checklist, "links": links,
        "notes": project.notes,
    })
    return jsonify({"ok": True, "count": len(links)})


@project_bp.route("/<int:project_id>/status", methods=["POST"])
def update_status(project_id):
    """Change le statut d'un projet via AJAX (drag & drop Kanban)."""
    data   = request.get_json() or {}
    status = data.get("status", "").strip()
    if status not in STATUS_OPTIONS:
        return jsonify({"ok": False, "error": "Statut invalide"}), 400
    project = ProjectModel.get_by_id(project_id)
    if not project:
        return jsonify({"ok": False, "error": "Projet introuvable"}), 404
    ProjectModel.update(project_id, {
        "name":        project.name,
        "description": project.description or "",
        "status":      status,
        "image_path":  project.image_path,
        "tags":        project.tags,
        "checklist":   project.checklist,
        "links":       project.links,
        "notes":       project.notes,
    })
    return jsonify({"ok": True, "status": status})


@project_bp.route("/<int:project_id>/delete", methods=["POST"])
def delete(project_id):
    project = ProjectModel.get_by_id(project_id)
    if project and project.image_path:
        _delete_project_image(project.image_path)
    ProjectModel.delete(project_id)
    flash(_t("msg.project_deleted"), "success")
    return redirect(url_for("projects.index"))


@project_bp.route("/project-images/<path:filename>")
def project_image(filename):
    from flask import send_from_directory
    images_dir = os.path.abspath(
        os.path.join(current_app.instance_path, "project_images")
    )
    return send_from_directory(images_dir, filename)


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
            MovementModel.record(component_id, "project_use", quantity, note=f"Projet #{project_id}", project_id=project_id)
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
            MovementModel.record(component_id, "project_return", quantity, note=f"Retour projet #{project_id}", project_id=project_id)
        except Exception as e:
            logger.debug("Ignored: %s", e)
        return jsonify({"ok": True, "new_qty": result["new_qty"]})
    return jsonify({"ok": False, "error": result["error"]}), 400




# ------------------------------------------------------------------ #
#  Mode kit
# ------------------------------------------------------------------ #

@project_bp.route("/<int:project_id>/kit", methods=["POST"])
def prepare_kit(project_id):
    """Débite du stock tous les composants disponibles du projet."""
    project = ProjectModel.get_by_id(project_id)
    if not project:
        return jsonify({"ok": False, "error": _t("msg.project_not_found")}), 404

    components = ProjectModel.get_components(project_id)
    debited = 0
    details = []
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
    """Exporte la BOM du projet en CSV."""
    import csv, io
    project = ProjectModel.get_by_id(project_id)
    if not project:
        flash(_t("msg.project_not_found"), "danger")
        return redirect(url_for("projects.index"))

    components = ProjectModel.get_components(project_id)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([_t("msg.csv_col_description"), "LCSC", "Mouser", "DigiKey",
                     _t("msg.csv_col_manufacturer"), _t("msg.csv_col_package"),
                     _t("msg.csv_col_qty_needed"), _t("msg.csv_col_in_stock"),
                     _t("msg.csv_col_unit_price2"), _t("msg.csv_col_total_price2")])
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
    from flask import Response
    return Response(
        "﻿" + output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=BOM_{safe_name}.csv"}
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

        import io, csv as csvmod
        # KiCad peut utiliser , ou ; comme séparateur
        raw = file.stream.read().decode("utf-8-sig")
        # Détecte le séparateur
        sep = ";" if raw.count(";") > raw.count(",") else ","
        reader = csvmod.DictReader(io.StringIO(raw, newline=None), delimiter=sep)
        rows = list(reader)

        if not rows:
            flash(_t("msg.bom_empty"), "danger")
            return redirect(url_for("projects.import_bom", project_id=project_id))

        report = _analyse_bom(rows, project_id)
        if report is None:
            flash(
                "Impossible de trouver une colonne LCSC ou Mouser dans ce fichier. "
                "Colonnes attendues : 'LCSC', 'Mouser', 'LCSC Part Number', etc."
                "Colonnes détectées : " + ", ".join(rows[0].keys()),
                "danger",
            )
            return redirect(url_for("projects.import_bom", project_id=project_id))

        return render_template(
            "projects/bom_report.html",
            project=project,
            report=report,
            filename=file.filename,
        )

    return render_template("projects/import_bom.html", project=project)


@project_bp.route("/<int:project_id>/import-bom/create-missing", methods=["POST"])
def create_missing(project_id):
    """Crée un composant manquant dans le stock et lance l'enrichissement LCSC."""

    lcsc    = request.form.get("lcsc", "").strip().upper()
    desc    = request.form.get("description", lcsc)
    qty     = request.form.get("quantity", 0, type=int)

    if not lcsc:
        flash(_t("msg.bom_lcsc_missing"), "danger")
        return redirect(url_for("projects.detail", project_id=project_id))

    db = get_db()
    # Vérifie si déjà existant
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
        # Enrichissement en arrière-plan
        _app = current_app._get_current_object()
        def _enrich(_app=_app):
            with _app.app_context():
                try:
                    info = lcsc_scraper.enrich_component(lcsc)
                    if info:
                        ComponentModel.apply_enrichment(comp_id, info)
                except Exception as e:
                    logger.debug("Ignored: %s", e)
        threading.Thread(target=_enrich, daemon=True).start()

    # Ajoute au projet
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

    db = get_db()
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
    missing_ids = request.form.getlist("missing_id")
    to_enrich = []
    to_enrich_mouser  = []
    to_enrich_digikey = []

    # Chargement en 1 seule requête de tous les composants existants
    # Indexés par référence pour éviter les N+1 queries
    all_rows = db.execute(
        "SELECT id, lcsc_part_number, mouser_part_number, digikey_part_number FROM components"
    ).fetchall()
    idx_lcsc    = {r["lcsc_part_number"]:    r for r in all_rows if r["lcsc_part_number"]}
    idx_mouser  = {r["mouser_part_number"]:  r for r in all_rows if r["mouser_part_number"]}
    idx_digikey = {r["digikey_part_number"]: r for r in all_rows if r["digikey_part_number"]}

    for idx in missing_ids:
        qty         = request.form.get(f"missing_qty_{idx}",     0,   type=int)
        desc        = request.form.get(f"missing_desc_{idx}",    "")
        lcsc        = request.form.get(f"missing_lcsc_{idx}",    "").strip().upper()
        mouser_ref  = request.form.get(f"missing_mouser_{idx}",  "").strip()
        digikey_ref = request.form.get(f"missing_digikey_{idx}", "").strip()

        if not lcsc and not mouser_ref and not digikey_ref:
            continue

        # Lookup en mémoire — zéro requête SQL supplémentaire
        existing = None
        if lcsc:
            existing = idx_lcsc.get(lcsc)
        if not existing and mouser_ref:
            existing = idx_mouser.get(mouser_ref)
        if not existing and digikey_ref:
            existing = idx_digikey.get(digikey_ref)

        if existing:
            comp_id = existing["id"]
            # Complète les refs manquantes (1 UPDATE ciblé si nécessaire)
            updates = {}
            if lcsc       and not existing["lcsc_part_number"]:    updates["lcsc_part_number"]    = lcsc
            if mouser_ref and not existing["mouser_part_number"]:  updates["mouser_part_number"]  = mouser_ref
            if digikey_ref and not existing["digikey_part_number"]: updates["digikey_part_number"] = digikey_ref
            if updates:
                fields = ", ".join(f"{k} = ?" for k in updates if k in _ALLOWED_COMP_UPDATE_COLS)
                # safe: `fields` est construit uniquement depuis des clés dict whitelistées
                # safe: `fields` est construit uniquement depuis des clés dict whitelistées
                try:
                    db.execute(f"UPDATE components SET {fields} WHERE id = ?",
                               list(updates.values()) + [comp_id])
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
        else:
            comp_data = {
                "description":      "",
                "description_long": desc or "",
                "quantity":         0,
                "min_stock":        0,
            }
            if lcsc:        comp_data["lcsc_part_number"]    = lcsc
            if mouser_ref:  comp_data["mouser_part_number"]  = mouser_ref
            if digikey_ref: comp_data["digikey_part_number"] = digikey_ref
            comp_id = ComponentModel.create(comp_data)
            if lcsc:
                to_enrich.append((comp_id, lcsc))
            elif mouser_ref:
                to_enrich_mouser.append((comp_id, mouser_ref))
            elif digikey_ref:
                to_enrich_digikey.append((comp_id, digikey_ref))

        try:
            ProjectModel.add_component(project_id, comp_id, max(1, qty))
            added += 1
        except Exception as e:
            logger.debug("Ignored: %s", e)

    # Enrichissement en arrière-plan — LCSC
    if to_enrich:
        from flask import current_app as _ca2
        _app2 = _ca2._get_current_object()
        def _enrich_missing():
            with _app2.app_context():
                for cid, lcsc_ref in to_enrich:
                    try:
                        info = lcsc_scraper.enrich_component(lcsc_ref)
                        if info:
                            ComponentModel.apply_enrichment(cid, info)
                    except Exception as e:
                        logger.debug("Ignored: %s", e)
        threading.Thread(target=_enrich_missing, daemon=True).start()
        flash(_t("msg.bom_enrich_started", n=len(to_enrich)), "info")

    # Enrichissement en arrière-plan — Mouser
    if to_enrich_mouser:
        from flask import current_app as _app
        _app_obj = _app._get_current_object()
        def _enrich_mouser():
            with _app_obj.app_context():
                
                for cid, mref in to_enrich_mouser:
                    _enrich_async_source(cid, mref, "mouser")
        threading.Thread(target=_enrich_mouser, daemon=True).start()

    # Enrichissement en arrière-plan — DigiKey
    if to_enrich_digikey:
        from flask import current_app as _app
        _app_obj = _app._get_current_object()
        def _enrich_digikey():
            with _app_obj.app_context():
                from .routes_misc import _enrich_async_source
                for cid, dref in to_enrich_digikey:
                    _enrich_async_source(cid, dref, "digikey")
        threading.Thread(target=_enrich_digikey, daemon=True).start()

    flash(_t("msg.bom_added", n=added), "success")
    return redirect(url_for("projects.detail", project_id=project_id))


# ------------------------------------------------------------------ #
#  Analyse BOM (logique métier)
# ------------------------------------------------------------------ #

# Noms de colonnes LCSC reconnus (insensible à la casse)
# Couvre : export commande LCSC, export panier LCSC, BOM KiCad JLCPCB, etc.
_LCSC_COLS = [
    # Format export commande LCSC classique
    "lcsc part number",
    # Format export panier LCSC (export_cart_*.csv)
    "lcsc#",
    # Variantes KiCad/JLCPCB
    "lcsc part #", "lcsc part", "lcsc",
    "lcsc_part_number",
    # Autres variantes
    "supplier part number", "supplier part #",
    "lcsc number", "lcsc no",
]
# Noms de colonnes quantité reconnus
_QTY_COLS = [
    "quantity", "qty", "quantite", "quantité", "qté", "amount",
]
# Noms de colonnes désignateur (R1, C2…)
_REF_COLS = [
    "reference", "ref", "designator", "references", "designators",
    "refdes", "designation",
]
# Noms de colonnes valeur/description
_VAL_COLS = [
    "value", "comment", "description", "val", "designation", "valeur",
    "mpn",  # export panier LCSC : MPN contient la référence fabricant
]


# Noms de colonnes DigiKey reconnus
_DIGIKEY_COLS = [
    "digikey", "digi-key", "digikey part number", "digikey part #",
    "digikey#", "digikey_part_number", "dk part number", "dk#",
]
_MOUSER_COLS = [
    "mouser", "mouser part number", "mouser part #",
    "mouser#", "mouser_part_number", "mouser no", "mouser number",
]


# _find_col, _analyse_bom et helpers d'enrichissement BOM
# → déplacés dans services/bom_analyser.py (audit P2)
from ..services.bom_analyser import _analyse_bom, _find_col


# ------------------------------------------------------------------ #
#  Helpers image projet
# ------------------------------------------------------------------ #

_ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

# Magic bytes des formats image autorisés
_IMAGE_MAGIC = {
    b"\xff\xd8\xff": ".jpg",
    b"\x89PNG":       ".png",
    b"GIF8":           ".gif",
    b"RIFF":           ".webp",  # RIFF....WEBP
}

def _save_project_image(file_storage) -> str | None:
    """Sauvegarde l'image uploadée, retourne le chemin relatif ou None."""
    if not file_storage:
        return None

    # Lire les premiers octets pour vérifier les magic bytes (ne pas se fier au content-type)
    header = file_storage.read(12)
    file_storage.seek(0)  # rembobiner pour la sauvegarde

    ext = ""
    for magic, candidate_ext in _IMAGE_MAGIC.items():
        if header.startswith(magic):
            ext = candidate_ext
            break

    # Fallback : extension déclarée si magic bytes non reconnus (ex: format futur)
    if not ext:
        ext = os.path.splitext(file_storage.filename)[-1].lower() if file_storage.filename else ""

    if ext not in _ALLOWED_EXTS:
        return None
    images_dir = os.path.abspath(
        os.path.join(current_app.instance_path, "project_images")
    )
    os.makedirs(images_dir, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ext}"
    file_storage.save(os.path.join(images_dir, filename))
    return filename


def _generate_color_banner(hex_color: str) -> str | None:
    """Génère une image PNG de bannière avec la couleur choisie."""
    try:
        from PIL import Image as PilImage
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        img = PilImage.new("RGB", (800, 200), (r, g, b))
        images_dir = os.path.join(current_app.instance_path, "project_images")
        os.makedirs(images_dir, exist_ok=True)
        import uuid
        filename = f"banner_{uuid.uuid4().hex}.png"
        img.save(os.path.join(images_dir, filename))
        return filename
    except Exception:
        return None


def _delete_project_image(image_path: str | None):
    """Supprime le fichier image si il existe."""
    if not image_path:
        return
    images_dir = os.path.abspath(
        os.path.join(current_app.instance_path, "project_images")
    )
    filepath = os.path.join(images_dir, image_path)
    if os.path.exists(filepath):
        os.remove(filepath)