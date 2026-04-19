import os
import json
import logging
import re as _re
import uuid
import urllib.request

logger = logging.getLogger(__name__)

from flask import (
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    send_from_directory,
    render_template,
    Response,
    current_app,
)

import requests as _requests

from ..models.component import ComponentModel
from ..models.category import CategoryModel
from ..models.settings import SettingsModel
from ..models.database import get_db
from ..models.project import ProjectModel
from ..views.component_view import ComponentView
from ..services.qr_generator import qr_svg_data_url
from ..services.easyeda import fetch_and_save
from .utils import _t
from . import component_bp
from .routes_misc import _form_to_dict


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
        os.path.join(current_app.instance_path, "images")
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
        os.path.join(current_app.instance_path, "images")
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
        instance_path = current_app.instance_path
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
        current_app.instance_path
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
        os.path.join(current_app.instance_path, "easyeda_pngs")
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
