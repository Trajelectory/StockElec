import io
import csv
import os
import threading
import logging
import tempfile
import zipfile

logger = logging.getLogger(__name__)

from flask import (Blueprint, request, redirect, url_for, flash, jsonify,
                   send_from_directory, send_file, render_template,
                   Response, current_app)

import requests as _requests

from ..models.component import ComponentModel, ITEMS_PER_PAGE_DEFAULT
from ..models.category import CategoryModel
from ..models.settings import SettingsModel
from ..models.movement import MovementModel
from ..models.database import get_db
from ..models.project import ProjectModel
from ..views.component_view import ComponentView
from ..services import lcsc_scraper
from ..services import mouser_scraper, digikey_scraper
from ..services.qr_generator import qr_svg_data_url
from ..services.easyeda import fetch_and_save

component_bp = Blueprint("components", __name__)


def _t(key: str, **kwargs) -> str:
    """Retourne la string traduite selon la langue configurée."""
    from app import load_locale
    lang = SettingsModel.get("lang", "fr") or "fr"
    locale = load_locale(lang)
    # Navigue dans le dict avec "section.key"
    parts = key.split(".")
    val = locale
    for p in parts:
        val = val.get(p, key) if isinstance(val, dict) else key
    if kwargs:
        try:
            val = val.format(**kwargs)
        except (KeyError, ValueError):
            pass
    return val


# ------------------------------------------------------------------ #
#  Dashboard / liste paginée
# ------------------------------------------------------------------ #

@component_bp.route("/")
def home():
    """Page d'accueil — barre de recherche + derniers composants."""
    db = get_db()

    stats = db.execute("""
        SELECT COUNT(*) AS n_components,
               SUM(quantity) AS n_total_qty,
               SUM(CASE WHEN min_stock > 0 AND quantity <= min_stock THEN 1 ELSE 0 END) AS n_alerts
        FROM components
    """).fetchone()

    # per_page depuis l'URL ou settings (défaut 8)
    try:
        home_limit = int(request.args.get("per_page", SettingsModel.get("home_recent_limit", "5")))
    except ValueError:
        home_limit = 8
    home_limit = max(5, min(home_limit, 100))

    recent = db.execute("""
        SELECT id, description, manufacture_part_number, lcsc_part_number,
               mouser_part_number, digikey_part_number, product_url,
               package, quantity, min_stock, unit_price, image_path
        FROM components
        ORDER BY created_at DESC LIMIT ?
    """, (home_limit,)).fetchall()

    return render_template("components/home.html",
        stats=stats, recent=recent, home_limit=home_limit)


@component_bp.route("/stock")
def stock():
    search   = request.args.get("search", "").strip()
    category = request.args.get("category", "").strip()
    sort_by  = request.args.get("sort_by", "description")
    order    = request.args.get("order", "asc")
    page     = max(int(request.args.get("page", 1) or 1), 1)
    per_page = int(request.args.get("per_page", ITEMS_PER_PAGE_DEFAULT) or ITEMS_PER_PAGE_DEFAULT)
    if per_page not in (5, 25, 50, 100):
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
    total_pages  = max((total + per_page - 1) // per_page, 1)
    stats        = ComponentModel.get_stats()
    low_count    = ComponentModel.count_low_stock()
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
        return jsonify({"ok": False, "error": _t("msg.err_delta_zero")}), 400

    result = ComponentModel.adjust_quantity(component_id, delta)
    if result["ok"]:
        # Enregistre le mouvement
        try:
                    MovementModel.record(component_id, "in" if delta > 0 else "out", abs(delta))
        except Exception:
            pass
        comp = ComponentModel.get_by_id(component_id)
        return jsonify({
            "ok":       True,
            "new_qty":  result["new_qty"],
            "is_low":   comp.is_low_stock,
            "min_stock": comp.min_stock,
        })
    return jsonify({"ok": False, "error": result["error"]}), 400


# ------------------------------------------------------------------ #
#  Export CSV du stock (v2)
# ------------------------------------------------------------------ #

@component_bp.route("/export/csv")
def export_csv():
    import csv, io
    db = get_db()
    rows = db.execute("""
        SELECT lcsc_part_number, mouser_part_number, digikey_part_number,
               manufacture_part_number, manufacturer,
               description, description_long, package, rohs,
               quantity, min_stock, unit_price, ext_price,
               category, location, notes, datasheet_url, product_url,
               created_at
        FROM components ORDER BY description
    """).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "LCSC", "Mouser", "DigiKey",
        "Réf. fab.", "Fabricant",
        "Description", "Description longue", "Package", "RoHS",
        "Quantité", "Seuil alerte", "Prix unit.", "Prix total",
        "Catégorie", "Emplacement", "Notes", "Datasheet", "Lien produit",
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

@component_bp.route("/enrich/<int:component_id>", methods=["POST"])
def enrich(component_id):
    comp = ComponentModel.get_by_id(component_id)
    if not comp:
        return jsonify({"ok": False, "error": _t("msg.err_not_found")}), 404

    # DigiKey
    if comp.digikey_part_number:
        client_id     = SettingsModel.get("digikey_client_id", "")
        client_secret = SettingsModel.get("digikey_client_secret", "")
        if not client_id or not client_secret:
            return jsonify({"ok": False, "error": _t("msg.err_dk_not_configured")}), 400
        info = digikey_scraper.enrich_component(comp.digikey_part_number, client_id, client_secret)
        if info:
            ComponentModel.apply_enrichment(component_id, info, force_attributes=True)
            return jsonify({"ok": True, "source": "digikey", "fields": list(info.keys())})
        return jsonify({"ok": False, "error": _t("msg.err_dk_no_data")})

    # Mouser
    if comp.mouser_part_number:
        api_key = SettingsModel.get("mouser_api_key", "")
        if not api_key:
            return jsonify({"ok": False, "error": _t("msg.err_mouser_not_configured")}), 400
        info = mouser_scraper.enrich_component(comp.mouser_part_number, api_key)
        if info:
            ComponentModel.apply_enrichment(component_id, info, force_attributes=True)
            return jsonify({"ok": True, "source": "mouser", "fields": list(info.keys())})
        return jsonify({"ok": False, "error": _t("msg.err_mouser_no_data")})

    # LCSC
    if comp.lcsc_part_number:
        info = lcsc_scraper.enrich_component(comp.lcsc_part_number)
        if info:
            ComponentModel.apply_enrichment(component_id, info, force_attributes=True)
            return jsonify({"ok": True, "source": "lcsc", "fields": list(info.keys())})
        return jsonify({"ok": False, "error": _t("msg.err_lcsc_no_data")})

    return jsonify({"ok": False, "error": _t("msg.err_no_ref")}), 400


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
        return jsonify({"ok": False, "error": _t("msg.err_ref_missing")}), 400

    # Vérifie si déjà en stock
    existing = get_db().execute(
        "SELECT id, description FROM components WHERE lcsc_part_number = ?", (ref,)
    ).fetchone()
    if existing:
        return jsonify({
            "ok": False,
            "duplicate": True,
            "error": _t("msg.err_already_in_stock", id=existing['id'], desc=existing['description'])
        })

    raw = lcsc_scraper.fetch_product(ref)
    if raw is None:
        return jsonify({"ok": False, "error": _t("msg.err_not_on_lcsc", ref=ref)}), 404

    info = lcsc_scraper.extract_info(raw)

    # Champs du formulaire
    prod_name = raw.get("productNameEn") or raw.get("productIntroEn") or raw.get("productDescEn", "")
    prod_desc = ""
    for key in ("productDescEn", "productIntroEn"):
        val = raw.get(key, "")
        if val and val != prod_name:
            prod_desc = val
            break

    preview = {
        "ok":                       True,
        "lcsc_part_number":         raw.get("productCode", ref),
        "manufacture_part_number":  raw.get("productModel", ""),
        "manufacturer":             raw.get("brandNameEn", ""),
        "description":              prod_name,
        "description_long":         prod_desc,
        "package":                  raw.get("encapStandard", ""),
        "rohs":                     "YES" if raw.get("isEnvironment") else "",
        "category":                 "",
        "image_url":                info.get("image_url", ""),
        "datasheet_url":            info.get("datasheet_url", ""),
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


@component_bp.route("/api/mouser-preview")
def mouser_preview():
    """
    GET /api/mouser-preview?ref=652-3852A-282101AL
    Retourne les infos Mouser pour pré-remplir le formulaire d'ajout.
    """

    ref     = request.args.get("ref", "").strip()
    api_key = SettingsModel.get("mouser_api_key", "")

    if not ref:
        return jsonify({"ok": False, "error": _t("msg.err_ref_missing")}), 400
    if not api_key:
        return jsonify({"ok": False, "error": _t("msg.err_mouser_no_key")}), 400

    part = mouser_scraper.fetch_product(ref, api_key)
    if not part:
        return jsonify({"ok": False, "error": _t("msg.err_not_on_mouser", ref=ref)}), 404

    info = mouser_scraper.extract_info(part)
    return jsonify({
        "ok":                       True,
        "source":                   "mouser",
        "mouser_part_number":       info.get("mouser_part_number", ref),
        "lcsc_part_number":         "",
        "digikey_part_number":      "",
        "manufacture_part_number":  info.get("manufacture_part_number", ""),
        "manufacturer":             info.get("manufacturer", ""),
        "description":              info.get("description", ""),
        "description_long":         "",
        "package":                  info.get("package", ""),
        "rohs":                     info.get("rohs", ""),
        "category":                 info.get("category_name", ""),
        "image_url":                info.get("image_url", ""),
        "datasheet_url":            info.get("datasheet_url", ""),
        "unit_price":               info.get("unit_price", ""),
        "product_url":              info.get("product_url", ""),
    })


# ------------------------------------------------------------------ #
#  DigiKey preview
# ------------------------------------------------------------------ #
@component_bp.route("/api/digikey-preview")
def digikey_preview():
    """
    GET /api/digikey-preview?ref=296-6501-1-ND
    Retourne les infos DigiKey pour pré-remplir le formulaire d'ajout.
    """

    ref           = request.args.get("ref", "").strip()
    client_id     = SettingsModel.get("digikey_client_id", "")
    client_secret = SettingsModel.get("digikey_client_secret", "")

    if not ref:
        return jsonify({"ok": False, "error": _t("msg.err_ref_missing")}), 400
    if not client_id or not client_secret:
        return jsonify({"ok": False, "error": _t("msg.err_dk_no_creds")}), 400

    product = digikey_scraper.fetch_product(ref, client_id, client_secret)
    if not product:
        return jsonify({"ok": False, "error": _t("msg.err_not_on_digikey", ref=ref)}), 404

    info = digikey_scraper.extract_info(product)

    preview = {
        "ok":                       True,
        "source":                   "digikey",
        "digikey_part_number":      info.get("digikey_part_number", ref),
        "lcsc_part_number":         "",
        "mouser_part_number":       "",
        "manufacture_part_number":  info.get("manufacture_part_number", ""),
        "manufacturer":             info.get("manufacturer", ""),
        "description":              info.get("description", ""),
        "description_long":         info.get("description_long", ""),
        "package":                  info.get("package", ""),
        "rohs":                     info.get("rohs", ""),
        "category":                 info.get("category_name", ""),
        "image_url":                info.get("image_url", ""),
        "datasheet_url":            info.get("datasheet_url", ""),
        "unit_price":               info.get("unit_price", ""),
        "product_url":              info.get("product_url", ""),
    }

    return jsonify(preview)




@component_bp.route("/labels")
def labels_print():
    """
    Page d'impression multi-étiquettes.
    Paramètres GET :
      ids=1,2,3        → liste d'IDs séparés par virgule
    """

    raw_ids = request.args.get("ids", "")
    try:
        ids = [int(x.strip()) for x in raw_ids.split(",") if x.strip().isdigit()]
    except ValueError:
        ids = []

    if not ids:
        flash(_t("msg.no_component_sel"), "warning")
        return redirect(url_for("components.stock"))

    _configured = SettingsModel.get("base_url", "").strip().rstrip("/")
    base_url = _configured if _configured else request.host_url.rstrip("/")

    components_data = []
    for cid in ids:
        comp = ComponentModel.get_by_id(cid)
        if comp is None:
            continue
        fiche_url = f"{base_url}{url_for('components.detail', component_id=cid)}"
        qr_data_url = qr_svg_data_url(fiche_url)
        components_data.append({
            "comp":        comp,
            "fiche_url":   fiche_url,
            "qr_data_url": qr_data_url,
        })

    if not components_data:
        flash(_t("msg.component_not_found2"), "warning")
        return redirect(url_for("components.stock"))

    # Charge la config étiquette
    lbl_config = {k: SettingsModel.get(k, v) for k, v in LABEL_DEFAULTS.items()}

    return render_template(
        "components/labels_print.html",
        components_data=components_data,
        lbl=lbl_config,
    )


# ------------------------------------------------------------------ #
#  Détail
# ------------------------------------------------------------------ #

@component_bp.route("/component/<int:component_id>")
def detail(component_id):
    comp = ComponentModel.get_by_id(component_id)
    if comp is None:
        flash(_t("msg.component_not_found"), "danger")
        return redirect(url_for("components.stock"))
    projects_using = ProjectModel.get_projects_for_component(component_id)
    return ComponentView.render_detail(comp, projects_using=projects_using)


# ------------------------------------------------------------------ #
#  Helpers image composant
# ------------------------------------------------------------------ #

def _download_image_from_url(image_url: str, ref: str) -> str | None:
    """Télécharge une image depuis une URL distante, retourne le chemin relatif ou None."""
    if not image_url:
        return None
    import urllib.request
    import urllib.parse
    import uuid as _uuid

    images_dir = os.path.abspath(
        os.path.join(component_bp.root_path, "..", "..", "instance", "images")
    )
    os.makedirs(images_dir, exist_ok=True)

    # Encoder l'URL pour gérer les espaces et caractères de contrôle
    parsed = urllib.parse.urlsplit(image_url)
    safe_url = urllib.parse.urlunsplit(
        parsed._replace(path=urllib.parse.quote(parsed.path, safe="/%"))
    )

    clean_url = safe_url.split("?")[0]
    ext = os.path.splitext(clean_url)[-1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        ext = ".jpg"

    filename = f"{_uuid.uuid4().hex}{ext}"
    filepath = os.path.join(images_dir, filename)

    try:
        # Referer adapté selon le domaine de l'image
        if "mouser.com" in safe_url:
            referer = "https://www.mouser.com/"
        elif "digikey.com" in safe_url:
            referer = "https://www.digikey.com/"
        else:
            referer = "https://www.google.com/"
        req = urllib.request.Request(
            safe_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer":    referer,
                "Accept":     "image/webp,image/apng,image/*,*/*;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            content_type = r.headers.get("Content-Type", "")
            content = r.read()
        if len(content) < 500:
            logger.warning("[add] Image trop petite pour %s (%d bytes)", ref, len(content))
            return None
        if "text/html" in content_type or content[:15].lstrip().startswith(b"<"):
            logger.warning("[add] Réponse HTML reçue à la place de l'image pour %s", ref)
            return None
        with open(filepath, "wb") as f:
            f.write(content)
        logger.info("[add] Image téléchargée pour %s → %s", ref, filename)
        return f"images/{filename}"
    except Exception as e:
        logger.warning("[add] Échec téléchargement image %s : %s", ref, e)
        return None


def _save_component_image(file_storage) -> str | None:
    """Sauvegarde une image uploadée pour un composant, retourne le chemin relatif ou None."""
    if not file_storage or file_storage.filename == "":
        return None
    ext = os.path.splitext(file_storage.filename)[-1].lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return None
    images_dir = os.path.abspath(
        os.path.join(component_bp.root_path, "..", "..", "instance", "images")
    )
    os.makedirs(images_dir, exist_ok=True)
    import uuid as _uuid
    filename = f"{_uuid.uuid4().hex}{ext}"
    file_storage.save(os.path.join(images_dir, filename))
    return f"images/{filename}"


# ------------------------------------------------------------------ #
#  Édition / Suppression
# ------------------------------------------------------------------ #

@component_bp.route("/component/<int:component_id>/edit", methods=["GET", "POST"])
def edit(component_id):
    comp = ComponentModel.get_by_id(component_id)
    if comp is None:
        flash(_t("msg.component_not_found3"), "danger")
        return redirect(url_for("components.stock"))

    if request.method == "POST":
        data = _form_to_dict(request.form)
        # Gère l'upload d'image manuelle
        uploaded = _save_component_image(request.files.get("image_file"))
        if uploaded:
            data["image_path"] = uploaded
        elif not data.get("image_path"):
            data["image_path"] = comp.image_path
        if not data.get("datasheet_url"):
            data["datasheet_url"] = comp.datasheet_url
        # Préserver product_url si absent du formulaire (champ non affiché dans l'éditeur)
        if not data.get("product_url"):
            data["product_url"] = comp.product_url
        try:
            ComponentModel.update(component_id, data)
            flash(_t("msg.component_updated"), "success")
            return redirect(url_for("components.detail", component_id=component_id))
        except Exception as e:
            if "UNIQUE" in str(e):
                flash(_t("msg.component_dup"), "danger")
            else:
                flash(f"❌ {e}", "danger")

    return ComponentView.render_edit(comp, category_groups=CategoryModel.get_grouped_for_stock())


@component_bp.route("/component/<int:component_id>/delete", methods=["POST"])
def delete(component_id):
    confirm = request.form.get("confirm_delete", "")
    if confirm != "yes":
        flash(_t("msg.delete_cancelled"), "warning")
        return redirect(url_for("components.detail", component_id=component_id))
    comp = ComponentModel.get_by_id(component_id)
    if not comp:
        flash(_t("msg.component_not_found3"), "danger")
        return redirect(url_for("components.stock"))
    ComponentModel.delete(component_id)
    flash(_t("msg.component_deleted", name=comp.description or comp.lcsc_part_number or '?'), "success")
    return redirect(url_for("components.stock"))


# ------------------------------------------------------------------ #
#  Symbole & Footprint EasyEDA (proxy + cache)
# ------------------------------------------------------------------ #

@component_bp.route("/api/easyeda-pngs/<lcsc_ref>")
def easyeda_pngs(lcsc_ref):
    """
    Télécharge et sauvegarde les PNGs EasyEDA (symbole + footprint).
    Met en cache dans la base et dans instance/easyeda_pngs/.
    Paramètre GET ?force=1 pour forcer le rechargement.
    """
    import os

    lcsc_ref = lcsc_ref.strip().upper()
    if not lcsc_ref:
        return jsonify({"ok": False, "error": _t("msg.err_ref_missing")}), 400

    force = request.args.get("force") == "1"
    db    = get_db()

    # Cherche le composant en base
    row = db.execute(
        "SELECT id, symbol_png, footprint_png FROM components WHERE lcsc_part_number = ?",
        (lcsc_ref,),
    ).fetchone()

    # Cache valide ?
    if not force and row and (row["symbol_png"] or row["footprint_png"]):
        # Vérifie que les fichiers existent encore
        instance_path = os.path.join(component_bp.root_path, "..", "..", "instance")
        sym_ok = row["symbol_png"] and os.path.exists(
            os.path.join(os.path.abspath(instance_path), row["symbol_png"])
        )
        fp_ok  = row["footprint_png"] and os.path.exists(
            os.path.join(os.path.abspath(instance_path), row["footprint_png"])
        )
        if sym_ok or fp_ok:
            return jsonify({
                "ok":           True,
                "symbol_png":   row["symbol_png"],
                "footprint_png": row["footprint_png"],
                "cached":       True,
            })

    # Téléchargement + conversion
    instance_path = os.path.abspath(
        os.path.join(component_bp.root_path, "..", "..", "instance")
    )
    result = fetch_and_save(lcsc_ref, instance_path)
    sym = result.get("symbol_png")
    fp  = result.get("footprint_png")

    if not sym and not fp:
        return jsonify({"ok": False, "error": _t("msg.err_no_image", ref=lcsc_ref)}), 404

    # Sauvegarde les chemins en base
    if row:
        ComponentModel.save_easyeda_pngs(row["id"], sym, fp)

    return jsonify({
        "ok":           True,
        "symbol_png":   sym,
        "footprint_png": fp,
        "cached":       False,
    })


@component_bp.route("/easyeda-pngs/<path:filename>")
def easyeda_png_file(filename):
    """Sert les fichiers PNG EasyEDA depuis instance/easyeda_pngs/."""
    import os
    pngs_dir = os.path.abspath(
        os.path.join(component_bp.root_path, "..", "..", "instance", "easyeda_pngs")
    )
    return send_from_directory(pngs_dir, filename)



# ------------------------------------------------------------------ #
#  Configuration des étiquettes
# ------------------------------------------------------------------ #

# Valeurs par défaut de la config étiquette
LABEL_DEFAULTS = {
    "lbl_width_mm":       "60",
    "lbl_height_mm":      "30",
    "lbl_bg_color":       "#ffffff",
    "lbl_text_color":     "#111111",
    "lbl_show_image":     "1",
    "lbl_show_qr":        "1",
    "lbl_show_lcsc":      "1",
    "lbl_show_mfr_part":  "1",
    "lbl_show_mfg":       "1",
    "lbl_show_package":   "1",
    "lbl_show_rohs":      "1",
    "lbl_show_qty":       "1",
    "lbl_show_location":  "1",
    "lbl_show_category":  "1",
    "lbl_show_price":     "1",
    "lbl_desc_size_mm":   "2.1",
    "lbl_ref_size_mm":    "1.7",
    "lbl_badge_size_mm":  "1.4",
    "lbl_color_pkg":      "#ebebeb",
    "lbl_color_rohs":     "#d4f0dd",
    "lbl_color_qty":      "#d0e8ff",
    "lbl_color_loc":      "#fff3cc",
    "lbl_color_cat":      "#efe8ff",
}


@component_bp.route("/label-settings", methods=["GET", "POST"])
def label_settings():
    """Page de configuration visuelle des étiquettes."""

    if request.method == "POST":
        for key in LABEL_DEFAULTS:
            # Les checkboxes non cochées ne sont pas envoyées → valeur "0"
            if key.startswith("lbl_show_"):
                val = "1" if request.form.get(key) else "0"
            else:
                val = request.form.get(key, LABEL_DEFAULTS[key]).strip()
            SettingsModel.set(key, val)
        flash(_t("msg.labels_saved"), "success")
        return redirect(url_for("components.label_settings"))

    # Charge la config courante (avec fallback sur les défauts)
    config = {k: SettingsModel.get(k, v) for k, v in LABEL_DEFAULTS.items()}

    # Prend un composant du stock pour l'aperçu (préfère un avec image)
    all_comps = ComponentModel.get_all()
    preview_comp = next((c for c in all_comps if c.image_path), None) or (all_comps[0] if all_comps else None)

    return render_template(
        "components/label_settings.html",
        config=config,
        preview_comp=preview_comp,
    )

# ------------------------------------------------------------------ #
#  Page alertes stock bas
# ------------------------------------------------------------------ #

@component_bp.route("/alerts")
def alerts():
    low = ComponentModel.get_low_stock()
    return render_template("components/alerts.html", components=low)



# ------------------------------------------------------------------ #
#  Paramètres
# ------------------------------------------------------------------ #

@component_bp.route("/settings", methods=["GET", "POST"])
def settings():
    import os, shutil

    if request.method == "POST":
        action = request.form.get("action")

        # ── Paramètres généraux ──────────────────────────────────────
        if action == "save_general":
            for key in ("app_name", "base_url", "default_min_stock", "lang",
                        "mouser_api_key", "digikey_client_id", "digikey_client_secret"):
                val = request.form.get(key, "").strip()
                SettingsModel.set(key, val)
            # Invalider le cache locale si la langue a changé
            import app as _app_module
            _app_module._locale_cache.clear()
            flash(_t("msg.settings_saved"), "success")

        # ── Enrichissement en masse ──────────────────────────────────
        elif action == "enrich_all":
            db = get_db()
            rows = db.execute(
                """SELECT id, lcsc_part_number FROM components
                   WHERE lcsc_part_number IS NOT NULL AND lcsc_part_number != ''
                     AND (image_path IS NULL OR image_path = ''
                          OR category IS NULL OR category = '')"""
            ).fetchall()
            ids = [(r["id"], r["lcsc_part_number"]) for r in rows]
            if ids:
                _enrich_async(ids)
                flash(_t("msg.enrich_launched", n=len(ids)), "info")
            else:
                flash(_t("msg.all_enriched"), "success")

        # ── Vider l'historique des mouvements ───────────────────────
        elif action == "clear_history":
            db = get_db()
            count = db.execute("SELECT COUNT(*) FROM stock_movements").fetchone()[0]
            db.execute("DELETE FROM stock_movements")
            db.commit()
            flash(_t("msg.history_cleared", n=count), "success")

        # ── Nettoyage images orphelines ──────────────────────────────
        elif action == "clean_images":
            instance_path = os.path.abspath(
                os.path.join(component_bp.root_path, "..", "..", "instance")
            )
            db = get_db()
            used = {r["image_path"] for r in db.execute(
                "SELECT image_path FROM components WHERE image_path IS NOT NULL"
            ).fetchall()}
            img_dir = os.path.join(instance_path, "images")
            deleted = 0
            if os.path.isdir(img_dir):
                for fname in os.listdir(img_dir):
                    fpath = f"images/{fname}"
                    if fpath not in used:
                        os.remove(os.path.join(img_dir, fname))
                        deleted += 1
            flash(_t("msg.images_cleaned", n=deleted), "success")

        # ── Réconciliation EasyEDA (fichiers présents mais pas en base) ─
        elif action == "reconcile_easyeda":
            instance_path = os.path.abspath(
                os.path.join(component_bp.root_path, "..", "..", "instance")
            )
            pngs_dir = os.path.join(instance_path, "easyeda_pngs")
            db = get_db()
            updated = 0
            if os.path.isdir(pngs_dir):
                # Groupe les fichiers par référence LCSC
                files = os.listdir(pngs_dir)
                refs = {}
                for f in files:
                    if not f.endswith(".png"): continue
                    # Format attendu : C149504_symbol.png ou C149504_footprint.png
                    if "_symbol." in f:
                        ref = f.split("_symbol.")[0].upper()
                        refs.setdefault(ref, {})["symbol"] = f"easyeda_pngs/{f}"
                    elif "_footprint." in f:
                        ref = f.split("_footprint.")[0].upper()
                        refs.setdefault(ref, {})["footprint"] = f"easyeda_pngs/{f}"

                for ref, paths in refs.items():
                    row = db.execute(
                        "SELECT id, symbol_png, footprint_png FROM components WHERE lcsc_part_number = ?",
                        (ref,)
                    ).fetchone()
                    if not row: continue
                    sym = paths.get("symbol")
                    fp  = paths.get("footprint")
                    # Met à jour seulement les colonnes vides
                    if (sym and not row["symbol_png"]) or (fp and not row["footprint_png"]):
                        ComponentModel.save_easyeda_pngs(
                            row["id"],
                            sym if not row["symbol_png"] else None,
                            fp  if not row["footprint_png"] else None,
                        )
                        updated += 1

            if updated:
                flash(_t("msg.easyeda_reconciled", n=updated), "success")
            else:
                flash(_t("msg.easyeda_ok"), "info")

        # ── Téléchargement EasyEDA en masse ─────────────────────────
        elif action == "easyeda_all":
            from ..services.easyeda import fetch_and_save
            import threading
            db = get_db()
            # Composants avec ref LCSC mais sans symbol ou footprint
            rows = db.execute(
                """SELECT id, lcsc_part_number FROM components
                   WHERE lcsc_part_number IS NOT NULL AND lcsc_part_number != ''
                     AND (symbol_png IS NULL OR symbol_png = ''
                          OR footprint_png IS NULL OR footprint_png = '')"""
            ).fetchall()
            if not rows:
                flash(_t("msg.easyeda_all_done"), "success")
            else:
                instance_path = os.path.abspath(
                    os.path.join(component_bp.root_path, "..", "..", "instance")
                )
                def _fetch_all_easyeda(items, inst_path):
                    import time
                    _db_app = component_bp.wsgi_app if hasattr(component_bp, 'wsgi_app') else None
                    for comp_id, lcsc_ref in items:
                        try:
                            result = fetch_and_save(lcsc_ref, inst_path)
                            sym = result.get("symbol_png")
                            fp  = result.get("footprint_png")
                            if sym or fp:
                                ComponentModel.save_easyeda_pngs(comp_id, sym, fp)
                            time.sleep(0.5)
                        except Exception:
                            pass

                items = [(r["id"], r["lcsc_part_number"]) for r in rows]
                t = threading.Thread(
                    target=_fetch_all_easyeda,
                    args=(items, instance_path),
                    daemon=True
                )
                t.start()
                flash(_t("msg.easyeda_launched", n=len(items)), "info")

        # ── Sauvegarde ────────────────────────────────────────────────
        elif action == "backup":
            instance_path = os.path.abspath(
                os.path.join(component_bp.root_path, "..", "..", "instance")
            )
            tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
            try:
                with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as zf:
                    for root, dirs, files in os.walk(instance_path):
                        for f in files:
                            fp = os.path.join(root, f)
                            zf.write(fp, os.path.relpath(fp, instance_path))
                from datetime import datetime
                fname = f"stockelec_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
                response = send_file(tmp.name, as_attachment=True, download_name=fname,
                                     mimetype="application/zip")
            finally:
                # Nettoyage du fichier temporaire après envoi
                try:
                    os.unlink(tmp.name)
                except Exception:
                    pass
            return response

        # ── Reset complet BDD (garde settings) ──────────────────────
        elif action == "reset_db":
            confirm = request.form.get("confirm_reset", "").strip()
            if confirm != "RESET":
                flash(_t("msg.reset_wrong"), "danger")
            else:
                db = get_db()
                # Supprime toutes les données sauf settings
                db.execute("DELETE FROM stock_movements")
                db.execute("DELETE FROM project_components")
                db.execute("DELETE FROM projects")
                db.execute("DELETE FROM components")
                db.execute("DELETE FROM categories")
                # Remet les séquences autoincrement à zéro
                db.execute("DELETE FROM sqlite_sequence WHERE name != 'settings'")
                db.commit()
                # Supprime aussi les images et PNGs EasyEDA
                instance_path = os.path.abspath(
                    os.path.join(component_bp.root_path, "..", "..", "instance")
                )
                import shutil
                for folder in ("images", "easyeda_pngs", "project_images"):
                    folder_path = os.path.join(instance_path, folder)
                    if os.path.isdir(folder_path):
                        shutil.rmtree(folder_path)
                        os.makedirs(folder_path, exist_ok=True)
                flash(_t("msg.reset_done"), "success")

        return redirect(url_for("components.settings"))

    # ── GET : collecte les stats ─────────────────────────────────────
    db = get_db()

    n_components = db.execute("SELECT COUNT(*) FROM components").fetchone()[0]
    n_projects   = db.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    n_no_image   = db.execute(
        "SELECT COUNT(*) FROM components WHERE image_path IS NULL OR image_path = ''"
    ).fetchone()[0]
    n_no_cat     = db.execute(
        "SELECT COUNT(*) FROM components WHERE category IS NULL OR category = ''"
    ).fetchone()[0]
    n_to_enrich  = db.execute(
        """SELECT COUNT(*) FROM components
           WHERE lcsc_part_number IS NOT NULL AND lcsc_part_number != ''
             AND (image_path IS NULL OR image_path = ''
                  OR category IS NULL OR category = '')"""
    ).fetchone()[0]
    n_no_easyeda = db.execute(
        """SELECT COUNT(*) FROM components
           WHERE lcsc_part_number IS NOT NULL AND lcsc_part_number != ''
             AND (symbol_png IS NULL OR symbol_png = ''
                  OR footprint_png IS NULL OR footprint_png = '')"""
    ).fetchone()[0]

    no_easyeda_list = db.execute(
        """SELECT id, description, lcsc_part_number, symbol_png, footprint_png
           FROM components
           WHERE lcsc_part_number IS NOT NULL AND lcsc_part_number != ''
             AND (symbol_png IS NULL OR symbol_png = ''
                  OR footprint_png IS NULL OR footprint_png = '')
           ORDER BY description"""
    ).fetchall()

    # Taille des fichiers
    instance_path = os.path.abspath(
        os.path.join(component_bp.root_path, "..", "..", "instance")
    )
    def dir_size(path):
        total = 0
        if os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                total += sum(os.path.getsize(os.path.join(root, f)) for f in files)
        return total

    db_size  = os.path.getsize(os.path.join(instance_path, "stock.db"))                if os.path.exists(os.path.join(instance_path, "stock.db")) else 0
    img_size = dir_size(os.path.join(instance_path, "images"))
    prj_size = dir_size(os.path.join(instance_path, "project_images"))

    def fmt_size(b):
        if b < 1024: return f"{b} o"
        if b < 1024**2: return f"{b/1024:.1f} Ko"
        return f"{b/1024**2:.1f} Mo"

    # Paramètres courants
    current = {
        "app_name":               SettingsModel.get("app_name", "StockElec"),
        "base_url":               SettingsModel.get("base_url", ""),
        "default_min_stock":      SettingsModel.get("default_min_stock", "0"),
        "home_recent_limit":      SettingsModel.get("home_recent_limit", "5"),
        "lang":                   SettingsModel.get("lang", "fr"),
        "mouser_api_key":         SettingsModel.get("mouser_api_key", ""),
        "digikey_client_id":      SettingsModel.get("digikey_client_id", ""),
        "digikey_client_secret":  SettingsModel.get("digikey_client_secret", ""),
    }

    stats = {
        "n_components": n_components,
        "n_projects":   n_projects,
        "n_no_image":   n_no_image,
        "n_no_cat":     n_no_cat,
        "n_to_enrich":  n_to_enrich,
        "n_no_easyeda":    n_no_easyeda,
        "no_easyeda_list": [dict(r) for r in no_easyeda_list],
        "db_size":      fmt_size(db_size),
        "img_size":     fmt_size(img_size),
        "prj_size":     fmt_size(prj_size),
        "total_size":   fmt_size(db_size + img_size + prj_size),
    }

    return ComponentView.render_settings(current, stats)


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

@component_bp.route("/api/test-key", methods=["POST"])
def api_test_key():
    """Teste une clé API Mouser ou DigiKey et retourne le statut."""
    source = request.json.get("source", "")

    if source == "mouser":
        api_key = request.json.get("api_key", "").strip()
        if not api_key:
            return jsonify({"ok": False, "error": _t("msg.err_key_missing")})
        try:
            resp = _requests.post(
                "https://api.mouser.com/api/v1/search/partnumber",
                params={"apiKey": api_key},
                json={"SearchByPartRequest": {"mouserPartNumber": "TESTPING", "partSearchOptions": "Exact"}},
                timeout=8,
            )
            if resp.status_code == 200:
                errors = resp.json().get("Errors") or []
                auth_errors = [e for e in errors if "401" in str(e) or "auth" in str(e).lower()]
                if auth_errors:
                    return jsonify({"ok": False, "error": _t("msg.err_key_invalid")})
                return jsonify({"ok": True, "message": "API Mouser accessible ✓"})
            elif resp.status_code == 401:
                return jsonify({"ok": False, "error": _t("msg.err_key_401")})
            else:
                return jsonify({"ok": False, "error": _t("msg.err_http", code=resp.status_code)})
        except Exception as e:
            return jsonify({"ok": False, "error": _t("msg.err_connection", err=str(e))})

    elif source == "digikey":
        client_id     = request.json.get("client_id", "").strip()
        client_secret = request.json.get("client_secret", "").strip()
        if not client_id or not client_secret:
            return jsonify({"ok": False, "error": _t("msg.err_creds_missing")})
        try:
            resp = _requests.post(
                digikey_scraper.TOKEN_URL,
                data={
                    "client_id":     client_id,
                    "client_secret": client_secret,
                    "grant_type":    "client_credentials",
                },
                timeout=8,
            )
            if resp.status_code == 200 and resp.json().get("access_token"):
                return jsonify({"ok": True, "message": "API DigiKey accessible ✓"})
            else:
                msg = (resp.json().get("error_description")
                       or resp.json().get("error")
                       or f"HTTP {resp.status_code}")
                return jsonify({"ok": False, "error": msg})
        except Exception as e:
            return jsonify({"ok": False, "error": _t("msg.err_connection", err=str(e))})

    return jsonify({"ok": False, "error": _t("msg.err_source_unknown")}), 400


@component_bp.route("/api/components")
def api_list():
    # Filtre par IDs pour le polling d'enrichissement
    ids_param = request.args.get("ids", "")
    if ids_param:
        try:
            ids = [int(i) for i in ids_param.split(",") if i.strip().isdigit()]
        except ValueError:
            ids = []
        if ids:
            db = get_db()
            placeholders = ",".join("?" * len(ids))
            rows = db.execute(
                f"SELECT id, description, attributes, image_path FROM components WHERE id IN ({placeholders})",
                ids
            ).fetchall()
            return jsonify([dict(r) for r in rows])
    search = request.args.get("search")
    return jsonify([c.to_dict() for c in ComponentModel.get_all(search=search)])


# ------------------------------------------------------------------ #
#  Helpers
# ------------------------------------------------------------------ #

def _form_to_dict(form):
    def _f(key):
        v = form.get(key, "").strip()
        return v if v else None

    def _fnum(key):
        v = form.get(key, "").strip().replace(",", ".")
        try:
            return float(v) if v else None
        except ValueError:
            return None

    unit_price = _fnum("unit_price")
    quantity   = _fnum("quantity")
    ext_price  = _fnum("ext_price")

    # Recalcul automatique de ext_price si non saisi manuellement
    if ext_price is None and unit_price is not None and quantity is not None:
        ext_price = round(unit_price * quantity, 4)

    return {
        "lcsc_part_number":        _f("lcsc_part_number"),
        "mouser_part_number":      _f("mouser_part_number"),
        "digikey_part_number":     _f("digikey_part_number"),
        "manufacture_part_number": _f("manufacture_part_number"),
        "manufacturer":            _f("manufacturer"),
        "customer_no":             _f("customer_no"),
        "package":                 _f("package"),
        "description":             form.get("description"),
        "description_long":        form.get("description_long"),
        "rohs":                    _f("rohs"),
        "quantity":                quantity,
        "min_stock":               _fnum("min_stock"),
        "unit_price":              unit_price,
        "ext_price":               ext_price,
        "category":                _f("category"),
        "location":                _f("location"),
        "notes":                   form.get("notes"),
        "datasheet_url":           _f("datasheet_url"),
        "product_url":             _f("product_url"),
        "image_url":               _f("image_url"),
    }


def _enrich_async(component_ids):
    """Enrichissement LCSC en arrière-plan pour une liste de (comp_id, lcsc_ref)."""
    app = current_app._get_current_object()

    def worker():
        with app.app_context():
            lcsc_scraper.enrich_batch(
                component_ids,
                apply_fn=ComponentModel.apply_enrichment,
                delay=0.5,
            )
    threading.Thread(target=worker, daemon=True).start()


def _enrich_async_source(comp_id: int, ref: str, source: str):
    """Enrichissement Mouser ou DigiKey en arrière-plan."""
    app = current_app._get_current_object()

    def worker():
        with app.app_context():
            try:
                if source == "mouser":
                    api_key = SettingsModel.get("mouser_api_key", "")
                    if not api_key:
                        return
                    info = mouser_scraper.enrich_component(ref, api_key)
                elif source == "digikey":
                    client_id     = SettingsModel.get("digikey_client_id", "")
                    client_secret = SettingsModel.get("digikey_client_secret", "")
                    if not client_id or not client_secret:
                        return
                    info = digikey_scraper.enrich_component(ref, client_id, client_secret)
                else:
                    return
                if info:
                    ComponentModel.apply_enrichment(comp_id, info)
            except Exception as e:
                logger.warning("[%s] enrichissement échoué : %s", source, e)

    threading.Thread(target=worker, daemon=True).start()


# ------------------------------------------------------------------ #
#  Plan de rangement
# ------------------------------------------------------------------ #

@component_bp.route("/rangement")
def rangement():
    import json as _json
    db = get_db()

    # Config des plateaux (sauvegardée en settings)
    raw = SettingsModel.get("rangement_config", "")
    try:
        config = _json.loads(raw) if raw else {"plateaux": [
            {"id": "A", "label": "Plateau A", "cols": 5, "rows": 4},
        ]}
    except Exception:
        config = {"plateaux": [{"id": "A", "label": "Plateau A", "cols": 5, "rows": 4}]}

    # Assignations case → composant
    raw_assign = SettingsModel.get("rangement_assign", "")
    try:
        assignments = _json.loads(raw_assign) if raw_assign else {}
    except Exception:
        assignments = {}

    # Tailles des cases
    raw_sizes = SettingsModel.get("rangement_sizes", "")
    try:
        sizes = _json.loads(raw_sizes) if raw_sizes else {}
    except Exception:
        sizes = {}

    # Tous les composants pour le sélecteur
    components = db.execute("""
        SELECT id, description, manufacture_part_number, lcsc_part_number,
               package, quantity, image_path, location
        FROM components ORDER BY description
    """).fetchall()

    return render_template("components/rangement.html",
        config=config,
        assignments=assignments,
        sizes=sizes,
        components=[dict(c) for c in components],
    )


@component_bp.route("/rangement/save", methods=["POST"])
def rangement_save():
    import json as _json
    data = request.get_json() or {}

    if "config" in data:
        SettingsModel.set("rangement_config", _json.dumps(data["config"]))

    if "assignments" in data:
        new_assignments = data["assignments"]

        db = get_db()

        # Lit les ANCIENNES assignations avant d'écraser
        raw_old = SettingsModel.get("rangement_assign", "")
        try:
            old_assignments = _json.loads(raw_old) if raw_old else {}
        except Exception:
            old_assignments = {}

        # Sauvegarde les nouvelles
        SettingsModel.set("rangement_assign", _json.dumps(new_assignments))

        # IDs des composants encore assignés dans le nouvel état
        assigned_ids = {str(v) for v in new_assignments.values() if v}

        # Vide le location des composants retirés
        for cell_id, comp_id in old_assignments.items():
            if comp_id and str(comp_id) not in assigned_ids:
                db.execute("UPDATE components SET location='' WHERE id=?", (comp_id,))

        # Met à jour le location des composants assignés
        for cell_id, comp_id in new_assignments.items():
            if comp_id:
                db.execute("UPDATE components SET location=? WHERE id=?",
                           (cell_id, comp_id))

        db.commit()

    if "sizes" in data:
        SettingsModel.set("rangement_sizes", _json.dumps(data["sizes"]))

    return jsonify({"ok": True})
