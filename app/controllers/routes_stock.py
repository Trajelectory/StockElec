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
from ..models.movement import MovementModel
from ..models.database import get_db
from ..views.component_view import ComponentView
from .utils import _t, require_esp32_token
from . import component_bp


@component_bp.route("/")
def home():
    """Page d'accueil — logo + barre de recherche uniquement."""
    return render_template("components/home.html")


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
    # Format nouveau : "atelier_id:PLATEAU_ID" (ex: "principal:A3")
    # Format ancien  : "A3" (rétrocompat)
    locations_raw = get_db().execute(
        "SELECT DISTINCT location FROM components WHERE location IS NOT NULL AND location != '' ORDER BY location"
    ).fetchall()

    # Construire la liste des ateliers avec leurs plateaux
    from ..models.atelier import AtelierModel
    all_ateliers_map = {a["id"]: a for a in AtelierModel.get_all()}

    drawer_ateliers = {}   # {atelier_id: {plateau_id, ...}}
    legacy_letters  = set()

    for r in locations_raw:
        loc = r["location"] or ""
        if ":" in loc:
            parts = loc.split(":", 1)
            aid   = parts[0]
            pid_m = _re.match(r"^([A-Za-z]+)", parts[1])
            pid   = pid_m.group(1) if pid_m else parts[1]
            drawer_ateliers.setdefault(aid, set()).add(pid)
        else:
            m = _re.match(r"^([A-Za-z]+)", loc)
            if m:
                legacy_letters.add(m.group(1))

    # drawer_letters reste pour rétrocompat (format ancien)
    drawer_letters = sorted(legacy_letters)

    return ComponentView.render_index(
        components=components,
        category_groups=category_groups,
        stats=stats,
        search=search,
        selected_category=category,
        location_filter=location_filter,
        drawer_letters=drawer_letters,
        drawer_ateliers=drawer_ateliers,
        all_ateliers_map=all_ateliers_map,
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


@component_bp.route("/component/<int:component_id>/notes", methods=["POST"])
def update_notes(component_id):
    """Mise à jour rapide des notes d'un composant (inline edit).
    Utilise une requête SQL ciblée pour ne toucher QUE la colonne notes,
    sans écraser les autres champs (ComponentModel.update fait un PUT complet).
    """
    from ..models.database import get_db
    data  = request.get_json(silent=True) or {}
    notes = data.get("notes", "").strip() or None  # None = valeur vide en DB

    comp = ComponentModel.get_by_id(component_id)
    if not comp:
        return jsonify({"ok": False, "error": "Composant introuvable"}), 404

    db = get_db()
    db.execute("UPDATE components SET notes = ?, updated_at = datetime('now') WHERE id = ?",
               (notes, component_id))
    db.commit()
    return jsonify({"ok": True})
