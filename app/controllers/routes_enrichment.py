import json
import logging

logger = logging.getLogger(__name__)

from flask import (
    request,
    jsonify,
    render_template,
    Response,
    current_app,
)


from ..models.component import ComponentModel
from ..models.settings import SettingsModel
from ..models.database import get_db
from ..services import lcsc_scraper
from ..services import mouser_scraper, digikey_scraper
from .utils import _t
from . import component_bp


@component_bp.route("/enrich/<int:component_id>", methods=["POST"])
def enrich(component_id):
    comp = ComponentModel.get_by_id(component_id)
    if not comp:
        return jsonify({"ok": False, "error": _t("msg.err_not_found")}), 404

    # Priorité d'enrichissement : DigiKey → Mouser → LCSC
    # Raison : on utilise la source dont on a déjà la référence sur le composant.
    # DigiKey en premier car son API v4 retourne les attributs techniques les plus complets.
    # LCSC en dernier car ses attributs sont déjà récupérés lors de l'ajout initial.
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



