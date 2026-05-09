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
    """Page d'accueil — logo + barre de recherche + stats globales."""
    from ..models.component import ComponentModel
    from ..models.atelier   import AtelierModel
    db   = get_db()
    comp = ComponentModel.get_dashboard_stats()
    stats = {
        "total":         comp["n_components"]   if comp else 0,
        "ruptures":      comp["n_zero"]         if comp else 0,
        "bas":           comp["n_alerts"]        if comp else 0,
        "ok":            (comp["n_components"] - comp["n_zero"] - comp["n_alerts"]) if comp else 0,
        "places":        db.execute("SELECT COUNT(*) FROM components WHERE location IS NOT NULL AND location != ''").fetchone()[0],
        "non_places":    db.execute("SELECT COUNT(*) FROM components WHERE location IS NULL OR location = ''").fetchone()[0],
        "ateliers":      len(AtelierModel.get_all()),
        "projets":       db.execute("SELECT COUNT(*) FROM projects").fetchone()[0],
        "valeur_totale": round(float(comp["total_value"] or 0), 2) if comp else 0.0,
    }
    return render_template("components/home.html", stats=stats)


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
    low_only      = request.args.get("low_stock") == "1"
    location_filter = request.args.get("location", "").strip()
    smart_filter  = request.args.get("smart_filter", "").strip()

    # Filtres KiCad filesystem : post-filtrage après get_page
    # (nécessitent un accès au dossier instance/kicad/)
    KICAD_FS_FILTERS = {"no_kicad", "no_kicad_sym", "no_kicad_fp", "no_kicad_3d", "no_lcsc_img"}
    is_kicad_fs = smart_filter in KICAD_FS_FILTERS
    sql_smart   = None if is_kicad_fs else (smart_filter or None)

    components, total = ComponentModel.get_page(
        search=search or None,
        category=category or None,
        sort_by=sort_by,
        order=order,
        page=page,
        per_page=per_page,
        low_only=low_only,
        location=location_filter,
        smart_filter=sql_smart,
    )

    # Post-filtrage filesystem pour les filtres KiCad
    # On charge TOUS les composants (pas juste la page) puis on pagine manuellement
    if is_kicad_fs:
        import os
        kicad_dir = os.path.join(current_app.instance_path, "kicad")

        # Index KiCad commun à tous les filtres KiCad filesystem
        kicad_idx = ComponentModel.build_kicad_index(kicad_dir)

        # Charger tous les composants (on pagine manuellement ensuite)
        all_comps, _ = ComponentModel.get_page(
            search=search or None,
            category=category or None,
            sort_by=sort_by, order=order,
            page=1, per_page=9999,
            low_only=low_only, location=location_filter,
        )

        # Fonctions de test par type de fichier manquant
        def _miss(c, key):
            return bool(c.lcsc_part_number and
                        not kicad_idx.get(c.lcsc_part_number, {}).get(key))

        kicad_predicates = {
            "no_kicad":     lambda c: c.lcsc_part_number and not (
                                kicad_idx.get(c.lcsc_part_number, {}).get("sym") and
                                kicad_idx.get(c.lcsc_part_number, {}).get("fp") and
                                kicad_idx.get(c.lcsc_part_number, {}).get("model")),
            "no_kicad_sym": lambda c: _miss(c, "sym"),
            "no_kicad_fp":  lambda c: _miss(c, "fp"),
            "no_kicad_3d":  lambda c: _miss(c, "model"),
        }

        if smart_filter in kicad_predicates:
            filtered   = [c for c in all_comps if kicad_predicates[smart_filter](c)]
            total      = len(filtered)
            offset     = (max(page, 1) - 1) * per_page
            components = filtered[offset:offset + per_page]

        elif smart_filter == "no_lcsc_img":
            all_comps, _ = ComponentModel.get_page(
                search=search or None,
                category=category or None,
                sort_by=sort_by, order=order,
                page=1, per_page=9999,
                low_only=low_only, location=location_filter,
            )
            filtered   = [c for c in all_comps
                          if c.lcsc_part_number and not c.image_path]
            total      = len(filtered)
            offset     = (max(page, 1) - 1) * per_page
            components = filtered[offset:offset + per_page]
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

    # Compteurs smart_filters pour la sidebar
    # Cache en mémoire 60s pour éviter les glob() répétés à chaque page
    import os, time
    from flask import g
    _cache_key   = "_smart_counts_cache"
    _cache_ts_key = "_smart_counts_ts"
    _CACHE_TTL   = 60  # secondes

    _cached_counts = getattr(current_app, _cache_key, None)
    _cached_ts     = getattr(current_app, _cache_ts_key, 0)
    if _cached_counts is None or (time.time() - _cached_ts) > _CACHE_TTL:
        kicad_dir = os.path.join(current_app.instance_path, "kicad")
        _cached_counts = ComponentModel.count_smart_filters(
            kicad_dir=kicad_dir if os.path.isdir(kicad_dir) else None
        )
        setattr(current_app, _cache_key,   _cached_counts)
        setattr(current_app, _cache_ts_key, time.time())
    smart_counts = _cached_counts

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
        smart_filter=smart_filter,
        smart_counts=smart_counts,
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
