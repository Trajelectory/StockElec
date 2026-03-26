import io
import csv
import os
import math
import threading

from flask import Blueprint, request, redirect, url_for, flash, jsonify, send_from_directory, render_template

from ..models.component import ComponentModel, ITEMS_PER_PAGE_DEFAULT
from ..models.movement import MovementModel, TYPE_MANUAL_ADD, TYPE_MANUAL_REMOVE, TYPE_IMPORT
from ..models.category import CategoryModel
from ..models.settings import SettingsModel
from ..views.component_view import ComponentView
from ..services import lcsc_scraper

component_bp = Blueprint("components", __name__)


# ------------------------------------------------------------------ #
#  Dashboard / liste paginée
# ------------------------------------------------------------------ #

@component_bp.route("/")
def index():
    search   = request.args.get("search", "").strip()
    category = request.args.get("category", "").strip()
    sort_by  = request.args.get("sort_by", "description")
    order    = request.args.get("order", "asc")
    page     = max(int(request.args.get("page", 1) or 1), 1)
    per_page = int(request.args.get("per_page", ITEMS_PER_PAGE_DEFAULT) or ITEMS_PER_PAGE_DEFAULT)
    if per_page not in (25, 50, 100):
        per_page = ITEMS_PER_PAGE_DEFAULT

    # Filtre "alertes seulement"
    low_only = request.args.get("low_stock") == "1"

    components, total = ComponentModel.get_page(
        search=search or None,
        category=category or None,
        sort_by=sort_by,
        order=order,
        page=page,
        per_page=per_page,
        low_only=low_only,
    )
    total_pages  = max(math.ceil(total / per_page), 1)
    stats        = ComponentModel.get_stats()
    low_count    = ComponentModel.count_low_stock()
    from ..models.category import CategoryModel
    category_groups = CategoryModel.get_grouped_for_stock()

    return ComponentView.render_index(
        components=components,
        category_groups=category_groups,
        stats=stats,
        search=search,
        selected_category=category,
        sort_by=sort_by,
        order=order,
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
        low_only=low_only,
        low_count=low_count,
    )


# ------------------------------------------------------------------ #
#  Ajustement rapide AJAX (boutons +/-)
# ------------------------------------------------------------------ #

@component_bp.route("/component/<int:component_id>/adjust", methods=["POST"])
def adjust(component_id):
    delta = request.json.get("delta", 0) if request.is_json else request.form.get("delta", 0, type=int)
    delta = int(delta)
    if delta == 0:
        return jsonify({"ok": False, "error": "Delta nul"}), 400

    movement_type = TYPE_MANUAL_ADD if delta > 0 else TYPE_MANUAL_REMOVE
    result = ComponentModel.adjust_quantity(
        component_id, delta, movement_type,
        note="Ajustement rapide",
    )
    if result["ok"]:
        comp = ComponentModel.get_by_id(component_id)
        return jsonify({
            "ok":       True,
            "new_qty":  result["new_qty"],
            "is_low":   comp.is_low_stock,
            "min_stock": comp.min_stock,
        })
    return jsonify({"ok": False, "error": result["error"]}), 400


# ------------------------------------------------------------------ #
#  Ajout manuel
# ------------------------------------------------------------------ #

@component_bp.route("/add", methods=["GET", "POST"])
def add():
    if request.method == "POST":
        data    = _form_to_dict(request.form)
        comp_id = ComponentModel.create(data)

        lcsc_num = data.get("lcsc_part_number")
        if lcsc_num:
            flash("Récupération des données LCSC en arrière-plan…", "info")
            _enrich_async([(comp_id, lcsc_num)])

        flash("Composant ajouté avec succès.", "success")
        return redirect(url_for("components.index"))

    from ..models.category import CategoryModel
    return ComponentView.render_add(category_groups=CategoryModel.get_grouped_for_stock())


# ------------------------------------------------------------------ #
#  Import CSV
# ------------------------------------------------------------------ #

@component_bp.route("/import", methods=["GET", "POST"])
def import_csv():
    if request.method == "POST":
        file = request.files.get("csv_file")
        if not file or file.filename == "":
            flash("Aucun fichier sélectionné.", "danger")
            return redirect(url_for("components.import_csv"))
        if not file.filename.lower().endswith(".csv"):
            flash("Veuillez fournir un fichier CSV.", "danger")
            return redirect(url_for("components.import_csv"))

        stream = io.StringIO(file.stream.read().decode("utf-8-sig"), newline=None)
        rows   = list(csv.DictReader(stream))
        result = ComponentModel.import_from_csv_rows(rows)

        inserted      = result["inserted"]
        skipped       = result["skipped"]
        duplicates    = result["duplicates"]
        errors        = result["errors"]
        component_ids = result["component_ids"]

        for e in errors[:5]:
            flash(e, "warning")

        parts = [f"{inserted} composant(s) importé(s)"]
        if skipped:
            parts.append(f"{skipped} ligne(s) ignorée(s)")
        flash(", ".join(parts) + ".", "success" if inserted > 0 else "info")

        if duplicates:
            refs   = ", ".join(duplicates[:10])
            suffix = f" (et {len(duplicates)-10} autres)" if len(duplicates) > 10 else ""
            flash(f"⚠️ Déjà en stock, non importés : {refs}{suffix}", "warning")

        if component_ids:
            flash(f"🔍 Récupération LCSC en cours pour {len(component_ids)} composant(s)…", "info")
            _enrich_async(component_ids)

        return redirect(url_for("components.index"))

    return ComponentView.render_import()


# ------------------------------------------------------------------ #
#  Enrichissement LCSC (AJAX)
# ------------------------------------------------------------------ #

@component_bp.route("/enrich/<int:component_id>", methods=["POST"])
def enrich(component_id):
    comp = ComponentModel.get_by_id(component_id)
    if not comp:
        return jsonify({"ok": False, "error": "Composant introuvable"}), 404
    if not comp.lcsc_part_number:
        return jsonify({"ok": False, "error": "Pas de référence LCSC"}), 400

    info = lcsc_scraper.enrich_component(comp.lcsc_part_number)
    if info:
        ComponentModel.apply_enrichment(component_id, info)
        return jsonify({"ok": True, "fields": list(info.keys())})
    return jsonify({"ok": False, "error": "Aucune donnée retournée par LCSC"})


# ------------------------------------------------------------------ #
#  Prévisualisation LCSC (AJAX — ne crée rien, juste scrape)
# ------------------------------------------------------------------ #

@component_bp.route("/api/lcsc-preview")
def lcsc_preview():
    """
    GET /api/lcsc-preview?ref=C149504
    Retourne les infos LCSC pour pré-remplir le formulaire d'ajout.
    Ne touche pas à la base de données.
    """
    ref = request.args.get("ref", "").strip().upper()
    if not ref:
        return jsonify({"ok": False, "error": "Référence manquante"}), 400

    # Vérifie si déjà en stock
    from ..models.database import get_db
    existing = get_db().execute(
        "SELECT id, description FROM components WHERE lcsc_part_number = ?", (ref,)
    ).fetchone()
    if existing:
        return jsonify({
            "ok": False,
            "duplicate": True,
            "error": f"Ce composant est déjà dans votre stock (#{existing['id']} — {existing['description']})"
        })

    raw = lcsc_scraper.fetch_product(ref)
    if raw is None:
        return jsonify({"ok": False, "error": f"Référence « {ref} » introuvable sur LCSC"}), 404

    info = lcsc_scraper.extract_info(raw)

    # Champs du formulaire
    preview = {
        "ok":                       True,
        "lcsc_part_number":         raw.get("productCode", ref),
        "manufacture_part_number":  raw.get("productModel", ""),
        "manufacturer":             raw.get("brandNameEn", ""),
        "description":              raw.get("productIntroEn") or raw.get("productNameEn") or raw.get("productDescEn", ""),
        "package":                  raw.get("encapStandard", ""),
        "rohs":                     "YES" if raw.get("isEnvironment") else "",
        "category":                 "",
        "image_url":                info.get("image_url", ""),
        "datasheet_url":            info.get("datasheet_url", ""),
        # Prix : on prend le premier palier
        "unit_price":               "",
    }

    # Catégorie full_path
    cat  = info.get("category_name", "")
    pcat = info.get("parent_category_name", "")
    if pcat and cat and pcat != cat:
        preview["category"] = f"{pcat} / {cat}"
    elif cat:
        preview["category"] = cat

    # Prix premier palier
    prices = raw.get("productPriceList") or []
    if prices:
        preview["unit_price"] = prices[0].get("usdPrice") or prices[0].get("productPrice") or ""

    return jsonify(preview)


# ------------------------------------------------------------------ #
#  Détail
# ------------------------------------------------------------------ #

@component_bp.route("/component/<int:component_id>")
def detail(component_id):
    comp = ComponentModel.get_by_id(component_id)
    if comp is None:
        flash("Composant introuvable.", "danger")
        return redirect(url_for("components.index"))
    movements = MovementModel.get_for_component(component_id, limit=20)
    from ..models.project import ProjectModel
    projects_using = ProjectModel.get_projects_for_component(component_id)
    return ComponentView.render_detail(comp, movements=movements, projects_using=projects_using)


# ------------------------------------------------------------------ #
#  Édition / Suppression
# ------------------------------------------------------------------ #

@component_bp.route("/component/<int:component_id>/edit", methods=["GET", "POST"])
def edit(component_id):
    comp = ComponentModel.get_by_id(component_id)
    if comp is None:
        flash("Composant introuvable.", "danger")
        return redirect(url_for("components.index"))

    if request.method == "POST":
        data = _form_to_dict(request.form)
        if not data.get("image_path"):
            data["image_path"] = comp.image_path
        if not data.get("datasheet_url"):
            data["datasheet_url"] = comp.datasheet_url
        ComponentModel.update(component_id, data)
        flash("Composant mis à jour.", "success")
        return redirect(url_for("components.detail", component_id=component_id))

    from ..models.category import CategoryModel
    return ComponentView.render_edit(comp, category_groups=CategoryModel.get_grouped_for_stock())


@component_bp.route("/component/<int:component_id>/delete", methods=["POST"])
def delete(component_id):
    ComponentModel.delete(component_id)
    flash("Composant supprimé.", "success")
    return redirect(url_for("components.index"))


# ------------------------------------------------------------------ #
#  Page alertes stock bas
# ------------------------------------------------------------------ #

@component_bp.route("/alerts")
def alerts():
    low = ComponentModel.get_low_stock()
    return render_template("components/alerts.html", components=low)


# ------------------------------------------------------------------ #
#  Historique global
# ------------------------------------------------------------------ #

@component_bp.route("/history")
def history():
    movements = MovementModel.get_recent(limit=200)
    stats     = MovementModel.get_stats()
    return render_template("components/history.html", movements=movements, stats=stats)


# ------------------------------------------------------------------ #
#  Paramètres
# ------------------------------------------------------------------ #

@component_bp.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        flash("Paramètres sauvegardés.", "success")
        return redirect(url_for("components.settings"))
    return ComponentView.render_settings({}, False)


# ------------------------------------------------------------------ #
#  Serving images
# ------------------------------------------------------------------ #

@component_bp.route("/images/<path:filename>")
def component_image(filename):
    images_dir = os.path.abspath(
        os.path.join(component_bp.root_path, "..", "..", "instance", "images")
    )
    return send_from_directory(images_dir, filename)


# ------------------------------------------------------------------ #
#  API JSON
# ------------------------------------------------------------------ #

@component_bp.route("/api/components")
def api_list():
    search = request.args.get("search")
    return jsonify([c.to_dict() for c in ComponentModel.get_all(search=search)])


# ------------------------------------------------------------------ #
#  Helpers
# ------------------------------------------------------------------ #

def _form_to_dict(form):
    return {
        "lcsc_part_number":        form.get("lcsc_part_number"),
        "manufacture_part_number": form.get("manufacture_part_number"),
        "manufacturer":            form.get("manufacturer"),
        "customer_no":             form.get("customer_no"),
        "package":                 form.get("package"),
        "description":             form.get("description"),
        "rohs":                    form.get("rohs"),
        "quantity":                form.get("quantity"),
        "min_stock":               form.get("min_stock"),
        "unit_price":              form.get("unit_price"),
        "ext_price":               form.get("ext_price"),
        "category":                form.get("category"),
        "location":                form.get("location"),
        "notes":                   form.get("notes"),
        "datasheet_url":           form.get("datasheet_url"),
    }


def _enrich_async(component_ids):
    from flask import current_app
    app = current_app._get_current_object()

    def worker():
        with app.app_context():
            lcsc_scraper.enrich_batch(
                component_ids,
                apply_fn=ComponentModel.apply_enrichment,
                delay=0.5,
            )
    threading.Thread(target=worker, daemon=True).start()
