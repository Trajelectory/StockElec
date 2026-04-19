import io
import csv
import json
import logging
import re as _re

logger = logging.getLogger(__name__)

from flask import (
    request,
    redirect,
    url_for,
    flash,
    render_template,
    Response,
    current_app,
)

import requests as _requests

from ..models.component import ComponentModel
from ..models.category import CategoryModel
from ..models.movement import MovementModel
from ..models.database import get_db
from ..views.component_view import ComponentView
from .utils import _t
from . import component_bp
from .routes_misc import _form_to_dict, _enrich_async, _enrich_async_source
from .routes_labels import _save_component_image, _download_image_from_url


@component_bp.route("/export/csv")
def export_csv():
    db = get_db()
    rows = db.execute("""
        SELECT lcsc_part_number, mouser_part_number, digikey_part_number,
               manufacture_part_number, manufacturer,
               description, description_long, package, rohs,
               quantity, min_stock, unit_price, ext_price,
               category, location, notes, datasheet_url, product_url, source_url,
               created_at
        FROM components ORDER BY description
    """).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "LCSC", "Mouser", "DigiKey",
        _t("msg.csv_col_ref_fab"), _t("msg.csv_col_manufacturer"),
        _t("msg.csv_col_description"), _t("msg.csv_col_desc_long"),
        _t("msg.csv_col_package"), _t("msg.csv_col_rohs"),
        _t("msg.csv_col_qty"), _t("msg.csv_col_min_stock"),
        _t("msg.csv_col_unit_price"), _t("msg.csv_col_total_price"),
        "Catégorie", "Emplacement", "Notes", "Datasheet", "Lien produit", "Source / URL achat",
        "Créé le",
    ])
    for r in rows:
        writer.writerow(list(r))

    return Response(
        output.getvalue(),
        mimetype="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": "attachment; filename=stockelec_export.csv"}
    )


# ------------------------------------------------------------------ #
#  Historique des mouvements (v2)
# ------------------------------------------------------------------ #

@component_bp.route("/history")
def history():
    db = get_db()

    component_id = request.args.get("component_id", type=int)
    type_filter  = request.args.get("type", "")
    per_page     = int(request.args.get("per_page", 50))
    page         = max(1, int(request.args.get("page", 1)))
    sort_by      = request.args.get("sort", "date")   # date | type | component
    order        = request.args.get("order", "desc")

    # Récupère TOUS les mouvements filtrés pour compter, puis pagine
    all_movements = MovementModel.get_recent(limit=10000, component_id=component_id)
    if type_filter:
        all_movements = [m for m in all_movements if m["type"] == type_filter]

    # Tri côté Python (les données viennent déjà triées par date desc par défaut)
    reverse = (order == "desc")
    if sort_by == "type":
        all_movements.sort(key=lambda m: m["type"], reverse=reverse)
    elif sort_by == "component":
        all_movements.sort(key=lambda m: (m["description"] or "").lower(), reverse=reverse)
    # "date" = ordre par défaut de get_recent

    total      = len(all_movements)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page        = min(page, total_pages)
    offset      = (page - 1) * per_page
    movements   = all_movements[offset:offset + per_page]

    component = None
    if component_id:
        comp = db.execute("SELECT id, description FROM components WHERE id=?", (component_id,)).fetchone()
        component = dict(comp) if comp else None

    return render_template("components/history.html",
        movements=movements, component=component,
        type_filter=type_filter, per_page=per_page, page=page,
        total=total, total_pages=total_pages,
        sort_by=sort_by, order=order,
        movement_types=__import__('app.models.movement', fromlist=['MovementModel']).MovementModel.TYPES
    )


# ------------------------------------------------------------------ #
#  Commandes / Réapprovisionnement (v2)
# ------------------------------------------------------------------ #

@component_bp.route("/reorder")
def reorder():
    db = get_db()

    show_all_zero = request.args.get("show_zero", "0") == "1"

    if show_all_zero:
        where = "WHERE quantity = 0 OR (min_stock > 0 AND quantity <= min_stock)"
    else:
        where = "WHERE (min_stock > 0 AND quantity <= min_stock) OR quantity = 0"

    # safe: `where` est une constante littérale (jamais d'input utilisateur)
    rows = db.execute(f"""
        SELECT id, description, lcsc_part_number, mouser_part_number, digikey_part_number,
               manufacture_part_number, product_url,
               manufacturer, quantity, min_stock, unit_price, image_path,
               CASE WHEN quantity = 0 THEN 'rupture'
                    WHEN quantity <= min_stock THEN 'bas'
                    ELSE 'ok' END AS stock_status,
               MAX(0, COALESCE(min_stock, 1) * 3 - quantity) AS suggested_qty
        FROM components
        {where}
        ORDER BY quantity ASC, description
    """).fetchall()

    return render_template("components/reorder.html",
        items=[dict(r) for r in rows],
        show_all_zero=show_all_zero)



# ------------------------------------------------------------------ #
#  Export CSV reorder par distributeur
# ------------------------------------------------------------------ #

@component_bp.route("/reorder/export")
def reorder_export():
    db          = get_db()
    distributor = request.args.get("dist", "all")   # lcsc | mouser | digikey | all
    show_zero   = request.args.get("show_zero", "0") == "1"

    where = "WHERE (min_stock > 0 AND quantity <= min_stock) OR quantity = 0"
    # safe: `where` est une constante littérale (jamais d'input utilisateur)
    rows = db.execute(f"""
        SELECT description, lcsc_part_number, mouser_part_number, digikey_part_number,
               manufacture_part_number, manufacturer, package, quantity, min_stock,
               unit_price,
               MAX(0, COALESCE(min_stock, 1) * 3 - quantity) AS suggested_qty
        FROM components
        {where}
        ORDER BY quantity ASC, description
    """).fetchall()

    output  = io.StringIO()
    writer  = csv.writer(output)
    today   = __import__('datetime').date.today().isoformat()

    if distributor == "lcsc":
        # Format import panier LCSC : LCSC Part Number, Qty
        writer.writerow(["LCSC Part Number", "Qty"])
        for r in rows:
            if r["lcsc_part_number"]:
                writer.writerow([r["lcsc_part_number"], r["suggested_qty"] or 1])
        filename = f"commande_LCSC_{today}.csv"

    elif distributor == "mouser":
        # Format panier Mouser : Mouser Part Number, Qty
        writer.writerow(["Mouser Part Number", "Quantity"])
        for r in rows:
            if r["mouser_part_number"]:
                writer.writerow([r["mouser_part_number"], r["suggested_qty"] or 1])
        filename = f"commande_Mouser_{today}.csv"

    elif distributor == "digikey":
        # Format panier DigiKey : Part Number, Quantity
        writer.writerow(["Part Number", "Quantity"])
        for r in rows:
            if r["digikey_part_number"]:
                writer.writerow([r["digikey_part_number"], r["suggested_qty"] or 1])
        filename = f"commande_DigiKey_{today}.csv"

    else:
        # CSV complet multi-distributeurs
        writer.writerow([
            _t("msg.csv_col_description"), _t("msg.csv_col_manufacturer"),
            _t("msg.csv_col_ref_fab"), _t("msg.csv_col_package"),
            "LCSC", "Mouser", "DigiKey",
            _t("msg.csv_col_in_stock"), _t("msg.csv_col_threshold"),
            _t("msg.csv_col_qty_suggest"), _t("msg.csv_col_unit_price2")
        ])
        for r in rows:
            writer.writerow([
                r["description"] or "",
                r["manufacturer"] or "",
                r["manufacture_part_number"] or "",
                r["package"] or "",
                r["lcsc_part_number"] or "",
                r["mouser_part_number"] or "",
                r["digikey_part_number"] or "",
                r["quantity"],
                r["min_stock"] or "",
                r["suggested_qty"] or "",
                r["unit_price"] or "",
            ])
        filename = f"reorder_{today}.csv"

    from flask import Response
    return Response(
        "﻿" + output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ------------------------------------------------------------------ #
#  Gestion des catégories personnalisées
# ------------------------------------------------------------------ #

@component_bp.route("/categories", methods=["GET", "POST"])
def categories():

    if request.method == "POST":
        action = request.form.get("action")

        if action == "create":
            parent = request.form.get("parent_name", "").strip()
            child  = request.form.get("child_name", "").strip() or None
            if parent:
                CategoryModel.create_custom(parent, child)
                flash(_t("msg.cat_created"), "success")
            else:
                flash(_t("msg.cat_name_required"), "danger")

        elif action == "delete":
            cat_id = int(request.form.get("category_id", 0))
            if cat_id < 0:
                CategoryModel.delete_custom(cat_id)
                flash(_t("msg.cat_deleted"), "success")
            else:
                flash(_t("msg.cat_lcsc_protected"), "danger")

        return redirect(url_for("components.categories"))

    custom_cats = CategoryModel.get_custom()
    # Groupe par parent pour l'affichage
    groups = {}
    for c in custom_cats:
        parent = c["parent_name"] or c["name"]
        groups.setdefault(parent, []).append(c)

    return render_template("components/categories.html", groups=groups)


# ------------------------------------------------------------------ #
#  Ajout manuel
# ------------------------------------------------------------------ #

@component_bp.route("/add", methods=["GET", "POST"])
def add():
    if request.method == "POST":
        data    = _form_to_dict(request.form)
        # Gère l'upload d'image manuelle (utile pour composants hors LCSC)
        uploaded = _save_component_image(request.files.get("image_file"))
        if uploaded:
            data["image_path"] = uploaded
        elif data.get("image_url") and not data.get("image_path"):
            # Image récupérée via preview DigiKey/Mouser — télécharger immédiatement
            local_path = _download_image_from_url(
                data["image_url"],
                ref=data.get("digikey_part_number") or data.get("mouser_part_number") or "component"
            )
            if local_path:
                data["image_path"] = local_path

        comp_id = ComponentModel.create(data)

        lcsc_num    = data.get("lcsc_part_number")
        mouser_num  = data.get("mouser_part_number")
        digikey_num = data.get("digikey_part_number")

        if lcsc_num:
            flash(_t("msg.enrich_lcsc"), "info")
            _enrich_async([(comp_id, lcsc_num)])
        elif mouser_num:
            # L'enrich async récupère les attributs techniques — l'image sera skippée
            # si déjà téléchargée via preview (apply_enrichment vérifie image_path non vide)
            flash(_t("msg.enrich_mouser"), "info")
            _enrich_async_source(comp_id, mouser_num, "mouser")
        elif digikey_num:
            # Idem DigiKey — les Parameters ne sont disponibles que via enrich async
            flash(_t("msg.enrich_digikey"), "info")
            _enrich_async_source(comp_id, digikey_num, "digikey")

        # Mode série : reste sur la page d'ajout avec confirmation
        desc = data.get("description") or data.get("lcsc_part_number") or "Composant"
        return redirect(url_for("components.add", added=desc[:60]))

    return ComponentView.render_add(category_groups=CategoryModel.get_grouped_for_stock())


# ------------------------------------------------------------------ #
#  Import CSV
# ------------------------------------------------------------------ #

@component_bp.route("/import", methods=["GET", "POST"])
def import_csv():
    if request.method == "POST":
        file = request.files.get("csv_file")
        if not file or file.filename == "":
            flash(_t("msg.no_file"), "danger")
            return redirect(url_for("components.import_csv"))
        if not file.filename.lower().endswith(".csv"):
            flash(_t("msg.not_csv"), "danger")
            return redirect(url_for("components.import_csv"))

        stream = io.StringIO(file.stream.read().decode("utf-8-sig"), newline=None)
        rows   = list(csv.DictReader(stream))
        result = ComponentModel.import_from_csv_rows(rows)

        inserted      = result["inserted"]
        skipped       = result["skipped"]
        duplicates    = result["duplicates"]
        errors        = result["errors"]
        component_ids = result["component_ids"]
        mouser_ids    = result.get("mouser_ids", [])
        digikey_ids   = result.get("digikey_ids", [])

        # Lance les enrichissements en arrière-plan
        if component_ids:
            _enrich_async(component_ids)
        if mouser_ids:
            for cid, mref in mouser_ids:
                _enrich_async_source(cid, mref, "mouser")
        if digikey_ids:
            for cid, dref in digikey_ids:
                _enrich_async_source(cid, dref, "digikey")

        # Affiche le rapport détaillé plutôt qu'un simple redirect
        return render_template("components/import_result.html",
            inserted=inserted, skipped=skipped,
            duplicates=duplicates, errors=errors,
            component_ids=component_ids,
            mouser_ids=mouser_ids, digikey_ids=digikey_ids,
            total_rows=len(rows),
        )

    return ComponentView.render_import()


# ------------------------------------------------------------------ #
#  Enrichissement LCSC (AJAX)
# ------------------------------------------------------------------ #
