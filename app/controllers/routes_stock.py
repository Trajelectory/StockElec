import sqlite3
import json
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
    from ..models.project import ProjectModel
    from ..models.database import get_db
    db = get_db()

    stats     = ComponentModel.get_dashboard_stats()
    recent    = ComponentModel.get_recent(limit=8)
    alerts    = ComponentModel.get_alerts_summary(limit=8)
    movements = ProjectModel.get_recent_movements(limit=10)
    projects  = ProjectModel.get_active(limit=5)

    # Top catégories pour le graphe en barres
    top_cats = db.execute("""
        SELECT
          CASE
            WHEN category LIKE '%/%'
              THEN TRIM(SUBSTR(category, 1, INSTR(category,'/')-1))
            WHEN category IS NOT NULL AND category != '' THEN category
            ELSE 'Autres'
          END AS cat_group,
          COUNT(*) as n,
          SUM(quantity) as qty
        FROM components
        WHERE category IS NOT NULL AND category != ''
        GROUP BY cat_group
        ORDER BY n DESC
        LIMIT 8
    """).fetchall()

    # Top fabricants
    top_mfr = db.execute("""
        SELECT manufacturer, COUNT(*) as n
        FROM components
        WHERE manufacturer IS NOT NULL AND manufacturer != ''
        GROUP BY manufacturer
        ORDER BY n DESC
        LIMIT 6
    """).fetchall()

    # Activité des 7 derniers jours (mouvements par jour)
    activity = db.execute("""
        SELECT DATE(created_at) as day, COUNT(*) as n,
               SUM(CASE WHEN type='in' THEN quantity ELSE 0 END) as qty_in,
               SUM(CASE WHEN type='out' THEN quantity ELSE 0 END) as qty_out
        FROM stock_movements
        WHERE created_at >= DATE('now', '-7 days')
        GROUP BY day
        ORDER BY day ASC
    """).fetchall()

    return render_template("components/home.html",
        stats=stats, recent=recent, alerts=alerts,
        movements=movements, projects=projects,
        top_cats=[dict(r) for r in top_cats],
        top_mfr=[dict(r) for r in top_mfr],
        activity=[dict(r) for r in activity],
    )


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
    try:
        delta = int(data.get("delta") or 0)
    except (ValueError, TypeError):
        return jsonify({"ok": False, "error": "Paramètre delta invalide"}), 400

    comp = ComponentModel.get_by_id(component_id)
    if not comp:
        return jsonify({"ok": False, "error": _t("msg.err_not_found")}), 404

    qty_before = comp.quantity

    if absolute is not None:
        try:
            delta = int(absolute) - comp.quantity
        except (ValueError, TypeError):
            return jsonify({"ok": False, "error": "Paramètre absolute invalide"}), 400

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
    # Résolution i18n — le model retourne une clé quand i18n=True
    err_msg = result["error"]
    if result.get("i18n"):
        err_msg = _t(err_msg, qty=result.get("qty", ""))
    logger.warning("[ADJUST] ❌ #%s erreur : %s", component_id, err_msg)
    return jsonify({"ok": False, "error": err_msg}), 400


# ------------------------------------------------------------------ #
#  Export CSV du stock (v2)
# ------------------------------------------------------------------ #
