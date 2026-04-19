import sqlite3
import json as _j
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

import requests as _requests

from ..models.component import ComponentModel, ITEMS_PER_PAGE_DEFAULT
from ..models.category import CategoryModel
from ..models.settings import SettingsModel
from ..models.movement import MovementModel
from ..models.database import get_db
from ..views.component_view import ComponentView
from .utils import _t, require_esp32_token
from . import component_bp


@component_bp.route("/")
def home():
    """Page d'accueil — dashboard avec stats, alertes, mouvements récents."""
    db = get_db()

    stats = db.execute("""
        SELECT COUNT(*) AS n_components,
               SUM(quantity) AS n_total_qty,
               SUM(CASE WHEN min_stock > 0 AND quantity <= min_stock THEN 1 ELSE 0 END) AS n_alerts,
               SUM(CASE WHEN quantity = 0 THEN 1 ELSE 0 END) AS n_zero,
               ROUND(SUM(quantity * COALESCE(unit_price,0)),2) AS total_value
        FROM components
    """).fetchone()

    # Derniers composants ajoutés
    recent = db.execute("""
        SELECT id, description, manufacture_part_number, lcsc_part_number,
               mouser_part_number, digikey_part_number, product_url,
               package, quantity, min_stock, unit_price, image_path
        FROM components ORDER BY created_at DESC LIMIT 6
    """).fetchall()

    # Composants en alerte
    alerts = db.execute("""
        SELECT id, description, lcsc_part_number, mouser_part_number,
               quantity, min_stock, image_path
        FROM components
        WHERE min_stock > 0 AND quantity <= min_stock
        ORDER BY quantity ASC LIMIT 6
    """).fetchall()

    # Derniers mouvements
    movements = db.execute("""
        SELECT m.type, m.quantity, m.created_at, m.note,
               c.id AS component_id, c.description, c.lcsc_part_number, c.image_path
        FROM stock_movements m
        JOIN components c ON c.id = m.component_id
        ORDER BY m.created_at DESC LIMIT 8
    """).fetchall()

    # Projets actifs
    projects = db.execute("""
        SELECT id, name, status, created_at
        FROM projects WHERE status NOT IN ('terminé', 'archivé')
        ORDER BY created_at DESC LIMIT 4
    """).fetchall()

    return render_template("components/home.html",
        stats=stats, recent=recent, alerts=alerts,
        movements=movements, projects=projects)


@component_bp.route("/stock")
def stock():
    search   = request.args.get("search", "").strip()
    category = request.args.get("category", "").strip()
    sort_by  = request.args.get("sort_by", "created_at")
    order    = request.args.get("order", "desc")
    page     = max(int(request.args.get("page", 1) or 1), 1)
    per_page = int(request.args.get("per_page", ITEMS_PER_PAGE_DEFAULT) or ITEMS_PER_PAGE_DEFAULT)
    if per_page not in (5, 25, 50, 100):
        per_page = ITEMS_PER_PAGE_DEFAULT

    # Filtre "alertes seulement"
    low_only = request.args.get("low_stock") == "1"
    location_filter = request.args.get("location", "").strip()

    components, total = ComponentModel.get_page(
        search=search or None,
        category=category or None,
        sort_by=sort_by,
        order=order,
        page=page,
        per_page=per_page,
        low_only=low_only,
        location=location_filter,
    )
    total_pages  = max((total + per_page - 1) // per_page, 1)
    stats        = ComponentModel.get_stats()
    low_count    = ComponentModel.count_low_stock()
    category_groups = CategoryModel.get_grouped_for_stock()

    # Emplacements distincts pour le filtre sidebar
    import re as _re
    locations_raw = get_db().execute(
        "SELECT DISTINCT location FROM components WHERE location IS NOT NULL AND location != '' ORDER BY location"
    ).fetchall()
    drawer_letters = sorted(set(
        m.group(1) for r in locations_raw
        if (m := _re.match(r"^([A-Za-z]+)", r["location"]))
    ))

    return ComponentView.render_index(
        components=components,
        category_groups=category_groups,
        stats=stats,
        search=search,
        selected_category=category,
        location_filter=location_filter,
        drawer_letters=drawer_letters,
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
@require_esp32_token
def adjust(component_id):
    data     = request.json or {}
    absolute = data.get("absolute")
    delta    = int(data.get("delta", 0))

    comp = ComponentModel.get_by_id(component_id)
    if not comp:
        return jsonify({"ok": False, "error": "Composant introuvable"}), 404

    qty_before = comp.quantity

    if absolute is not None:
        delta = int(absolute) - comp.quantity

    if delta == 0:
        logger.info("[ADJUST] #%s %s — delta=0, rien à faire (qty=%s)",
                    component_id, comp.description[:40], comp.quantity)
        return jsonify({"ok": True, "new_qty": comp.quantity, "is_low": comp.is_low_stock})

    result = ComponentModel.adjust_quantity(component_id, delta)
    if result["ok"]:
        try:
            MovementModel.record(component_id, "in" if delta > 0 else "out", abs(delta))
        except (sqlite3.OperationalError, sqlite3.DatabaseError):
            pass  # Mouvement non enregistré mais adjust OK
        comp = ComponentModel.get_by_id(component_id)
        direction = "📈" if delta > 0 else "📉"
        logger.info(
            "\n"
            "┌─ ADJUST ───────────────────────────────────\n"
            "│  Composant : #%s  %s\n"
            "│  Delta     : %s%+d  (%s → %s)\n"
            "│  Seuil min : %s  %s\n"
            "└────────────────────────────────────────────",
            component_id, comp.description[:40],
            direction, delta, qty_before, result["new_qty"],
            comp.min_stock,
            "⚠️ STOCK BAS" if comp.is_low_stock else "✅ OK",
        )
        return jsonify({
            "ok": True, "new_qty": result["new_qty"],
            "is_low": comp.is_low_stock, "min_stock": comp.min_stock,
        })
    logger.warning("[ADJUST] ❌ #%s erreur : %s", component_id, result["error"])
    return jsonify({"ok": False, "error": result["error"]}), 400


# ------------------------------------------------------------------ #
#  Export CSV du stock (v2)
# ------------------------------------------------------------------ #
