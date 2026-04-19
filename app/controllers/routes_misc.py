import os
import json as _j
import threading
import logging
import re as _re

logger = logging.getLogger(__name__)

from flask import (
    request,
    jsonify,
    send_from_directory,
    render_template,
    Response,
    current_app,
)

import requests as _requests

from ..models.component import ComponentModel
from ..models.settings import SettingsModel
from ..models.database import get_db
from ..services import lcsc_scraper
from ..services.kicad_jlc import get_component_kicad_status
from ..services import mouser_scraper, digikey_scraper
from .utils import _t, require_esp32_token
from . import component_bp


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
                return jsonify({"ok": True, "message": _t("msg.mouser_api_ok")})
            elif resp.status_code == 401:
                return jsonify({"ok": False, "error": _t("msg.err_key_401")})
            else:
                return jsonify({"ok": False, "error": _t("msg.err_http", code=resp.status_code)})
        except _requests.RequestException as e:
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
                return jsonify({"ok": True, "message": _t("msg.digikey_api_ok")})
            else:
                msg = (resp.json().get("error_description")
                       or resp.json().get("error")
                       or f"HTTP {resp.status_code}")
                return jsonify({"ok": False, "error": msg})
        except _requests.RequestException as e:
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
            except (ValueError, KeyError, OSError, _requests.RequestException) as e:
                logger.warning("[%s] enrichissement échoué : %s", source, e)

    threading.Thread(target=worker, daemon=True).start()


# ------------------------------------------------------------------ #
#  Plan de rangement
# ------------------------------------------------------------------ #


# ── Documentation CSS ─────────────────────────────────────────────

def _css_classes(prefix):
    """Extraire les classes CSS d'un namespace depuis les fichiers CSS."""
    import glob as _glob, re as _re, os as _os
    results = {}
    css_dir = _os.path.join(_os.path.dirname(__file__), '..', 'static', 'css', 'modules')
    for f in _glob.glob(_os.path.join(css_dir, '*.css')):
        src = open(f, encoding="utf-8", errors="ignore").read()
        for m in _re.finditer(r'(\.' + _re.escape(prefix) + r'[\w-]*)\s*\{([^}]+)\}', src):
            cls = m.group(1).lstrip('.')
            props = _re.sub(r'\s+', ' ', m.group(2).strip())[:120]
            if cls not in results:
                results[cls] = props
    return results




# ------------------------------------------------------------------ #
#  API JSON — fiche composant pour le P4 GUITION
# ------------------------------------------------------------------ #

@component_bp.route("/component/<int:component_id>/json")
@require_esp32_token
def component_json(component_id):
    """
    GET /component/<id>/json
    Retourne la fiche complète d'un composant en JSON.
    Utilisé par le firmware ESP32-P4 pour afficher la fiche sur l'écran.
    """
    import os

    comp = ComponentModel.get_by_id(component_id)
    if comp is None:
        return jsonify({"ok": False, "error": "Composant introuvable"}), 404

    # Statut fichiers KiCad
    kicad_dir = os.path.join(current_app.instance_path, "kicad")
    kicad_status = get_component_kicad_status(
        comp.lcsc_part_number or "", kicad_dir
    )

    return jsonify({
        "ok":                   True,
        "id":                   comp.id,
        "description":          comp.description          or "",
        "manufacturer":         comp.manufacturer         or "",
        "lcsc_part_number":     comp.lcsc_part_number     or "",
        "manufacture_part_number": comp.manufacture_part_number or "",
        "mouser_part_number":   comp.mouser_part_number   or "",
        "digikey_part_number":  comp.digikey_part_number  or "",
        "package":              comp.package              or "",
        "location":             comp.location             or "",
        "category":             comp.category             or "",
        "quantity":             comp.quantity             or 0,
        "min_stock":            comp.min_stock            or 0,
        "unit_price":           float(comp.unit_price)    if comp.unit_price else 0.0,
        "rohs":                 comp.rohs                 or "",
        "datasheet_url":        comp.datasheet_url        or "",
        "image_url":            f"/component/{comp.id}/image" if comp.image_path else "",
        "kicad_sym":            bool(kicad_status.get("symbol")),
        "kicad_fp":             bool(kicad_status.get("footprint")),
        "kicad_3d":             bool(kicad_status.get("model3d")),
    })


@component_bp.route("/component/<int:component_id>/image")
@require_esp32_token
def component_image_by_id(component_id):
    """
    GET /component/<id>/image
    Sert l'image d'un composant directement (pour le P4).
    """
    comp = ComponentModel.get_by_id(component_id)
    if comp is None or not comp.image_path:
        abort(404)

    images_dir = os.path.join(current_app.instance_path, "images")
    filename   = os.path.basename(comp.image_path)
    return send_from_directory(images_dir, filename)


def register_docs(app):
    @app.route('/docs/manuel')
    def docs_manuel():
        return render_template('docs/manuel.html')

    @app.route('/docs')
    def docs_index():
        return render_template('docs/index.html',
            pf_classes   = _css_classes('pf-'),
            pd_classes   = _css_classes('pd-'),
            kb_classes   = _css_classes('kb-'),
            cd_classes   = _css_classes('cd-'),
            sk_classes   = _css_classes('sk-'),
            stg_classes  = _css_classes('stg-'),
            ls_classes   = _css_classes('ls-'),
            gf_classes   = _css_classes('gf-'),
            proj_classes = _css_classes('proj-'),
            bom_classes  = _css_classes('bom-'),
            dash_classes = _css_classes('dash-'),
            md_classes   = _css_classes('md-'),
            src_classes  = _css_classes('src-'),
            qty_classes  = _css_classes('qty-'),
            td_classes   = _css_classes('td-'),
            lbl_classes  = _css_classes('lbl-'),
            btn_classes  = _css_classes('btn-'),
            nav_classes  = _css_classes('nav-'),
            imp_classes  = _css_classes('imp-'),
            badge_classes= _css_classes('badge-'),
            alert_classes= _css_classes('alert-'),
        )


# ------------------------------------------------------------------ #
#  Vérification prix temps réel LCSC
# ------------------------------------------------------------------ #

@component_bp.route("/api/price-check/<lcsc_ref>")
def price_check(lcsc_ref):
    """
    GET /api/price-check/C149504
    Récupère le prix actuel sur LCSC et le compare au prix stocké en base.
    Retourne :
        {
            "ok": true,
            "current_usd": 0.0023,
            "stored":      0.0019,
            "delta_pct":   21.0,       # positif = plus cher, négatif = moins cher
            "trend":       "up"|"down"|"stable",
            "ladders":     [{"qty": 1, "price": 0.0023}, ...]
        }
    """
    lcsc_ref = lcsc_ref.strip().upper()
    if not lcsc_ref:
        return jsonify({"ok": False, "error": _t("msg.err_ref_missing")}), 400

    # Prix stocké en base
    db = get_db()
    row = db.execute(
        "SELECT unit_price FROM components WHERE lcsc_part_number = ?",
        (lcsc_ref,)
    ).fetchone()
    stored_price = float(row["unit_price"]) if row and row["unit_price"] else None

    # Prix actuel depuis l'API LCSC
    result = lcsc_scraper.fetch_product(lcsc_ref)
    if not result:
        return jsonify({"ok": False, "error": _t("msg.err_lcsc_no_data")}), 404

    price_list = result.get("productPriceList") or result.get("priceList") or []
    if not price_list:
        return jsonify({"ok": False, "error": "Aucun prix disponible sur LCSC."}), 404

    # Trier par quantité croissante
    try:
        sorted_prices = sorted(
            price_list,
            key=lambda x: x.get("ladder", 0) or x.get("quantity", 0)
        )
    except (TypeError, KeyError):
        sorted_prices = price_list

    # Prix unitaire palier 1
    first = sorted_prices[0]
    current_usd = first.get("price") or first.get("usdPrice") or first.get("productPrice")
    if current_usd is None:
        return jsonify({"ok": False, "error": "Prix introuvable dans la réponse LCSC."}), 404

    current_usd = round(float(current_usd), 6)

    # Calcul delta
    delta_pct = None
    trend = "unknown"
    if stored_price and stored_price > 0:
        delta_pct = round((current_usd - stored_price) / stored_price * 100, 1)
        if abs(delta_pct) <= 5:
            trend = "stable"
        elif delta_pct > 0:
            trend = "up"
        else:
            trend = "down"

    # Tous les paliers
    ladders = []
    for p in sorted_prices:
        qty   = p.get("ladder") or p.get("quantity") or p.get("startNumber") or 1
        price = p.get("price") or p.get("usdPrice") or p.get("productPrice")
        if price:
            ladders.append({"qty": int(qty), "price": round(float(price), 6)})

    return jsonify({
        "ok":          True,
        "lcsc_ref":    lcsc_ref,
        "current_usd": current_usd,
        "stored":      stored_price,
        "delta_pct":   delta_pct,
        "trend":       trend,
        "ladders":     ladders,
    })
