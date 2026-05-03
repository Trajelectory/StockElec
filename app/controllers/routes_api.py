"""
routes_api.py — API REST complète StockEleK
Utilisée par le Waveshare 10", des scripts externes, ou tout client HTTP.

── STOCK ────────────────────────────────────────────────────────────────
GET  /api/stats                         — compteurs globaux
GET  /api/stock                         — liste paginée + filtres
GET  /api/stock/search?q=               — recherche rapide (20 résultats)
GET  /api/stock/<id>                    — fiche composant complète
POST /api/stock                         — créer un composant
PUT  /api/stock/<id>                    — modifier un composant
DELETE /api/stock/<id>                  — supprimer un composant
POST /api/stock/<id>/adjust             — ajuster la quantité (+/- delta ou absolute)

── CATÉGORIES ───────────────────────────────────────────────────────────
GET  /api/categories                    — liste des catégories avec compteurs

── RANGEMENT ────────────────────────────────────────────────────────────
GET  /api/rangement                     — tous les ateliers + plateaux + stats
GET  /api/rangement/<atelier_id>        — plateau complet avec cases + composants

── HISTORIQUE ───────────────────────────────────────────────────────────
GET  /api/historique                    — flux des mouvements de stock

── PROJETS ──────────────────────────────────────────────────────────────
GET  /api/projets                       — liste des projets
GET  /api/projets/<id>                  — détail projet + BOM
POST /api/projets                       — créer un projet
PUT  /api/projets/<id>                  — modifier un projet
DELETE /api/projets/<id>               — supprimer un projet
POST /api/projets/<id>/components       — ajouter un composant au projet
DELETE /api/projets/<id>/components/<comp_id>  — retirer un composant
POST /api/projets/<id>/components/<comp_id>/use    — utiliser (décrémente stock)
POST /api/projets/<id>/components/<comp_id>/return — rendre (incrémente stock)

── LEDs ─────────────────────────────────────────────────────────────────
POST /api/led/on                        — allumer LED
POST /api/led/off                       — éteindre
GET  /api/led/status                    — état courant
GET  /api/led/ping                      — ping ESP32
"""
import logging
from flask import Blueprint, jsonify, request
from ..models.database   import get_db
from ..models.atelier    import AtelierModel
from ..models.component  import ComponentModel
from ..models.movement   import MovementModel
from ..models.project    import ProjectModel

logger = logging.getLogger(__name__)
api_bp = Blueprint("api", __name__, url_prefix="/api")


# ─────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────
def _safe(s):
    """Remplace les caractères hors ASCII courants."""
    if not s:
        return ""
    return (s
        .replace("℃", "°C").replace("℉", "°F")
        .replace("μ", "u").replace("Ω", "ohm")
        .replace("±", "+/-").replace("×", "x")
        .replace("≤", "<=").replace("≥", ">=")
    )


def _comp_dict(row):
    """Composant DB → dict JSON propre."""
    d = dict(row) if not isinstance(row, dict) else row
    image_path = d.get("image_path") or ""
    return {
        "id":           d.get("id"),
        "name":         _safe(d.get("manufacture_part_number") or d.get("description") or ""),
        "description":  _safe(d.get("description") or ""),
        "manufacturer": _safe(d.get("manufacturer") or ""),
        "lcsc_ref":     d.get("lcsc_part_number") or "",
        "package":      d.get("package") or "",
        "category":     _safe(d.get("category") or ""),
        "quantity":     d.get("quantity") or 0,
        "min_stock":    d.get("min_stock") or 0,
        "unit_price":   d.get("unit_price") or 0.0,
        "location":     d.get("location") or "",
        "image_url":    f"/component/{d['id']}/image/raw?w=220&h=220" if image_path else "",
        "stock_state":  (
            "rupture" if (d.get("quantity") or 0) == 0 else
            "bas"     if (d.get("min_stock") or 0) > 0 and
                         (d.get("quantity") or 0) <= (d.get("min_stock") or 0) else
            "ok"
        ),
        "notes":        d.get("notes") or "",
        "datasheet_url": d.get("datasheet_url") or "",
        "created_at":   d.get("created_at") or "",
        "updated_at":   d.get("updated_at") or "",
    }


def _stock_query(where_clauses=None, params=None, extra="", limit=None, offset=None):
    """Construit et exécute une requête SELECT sur components."""
    db = get_db()
    where_clauses = where_clauses or []
    params        = params or []
    sql_where     = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    sql_limit     = f"LIMIT {limit} OFFSET {offset}" if limit is not None else ""
    rows = db.execute(
        f"""SELECT id, description, manufacture_part_number, lcsc_part_number,
                   package, category, manufacturer, quantity, min_stock,
                   unit_price, location, image_path, notes, datasheet_url,
                   created_at, updated_at
            FROM components {sql_where} {extra} {sql_limit}""",
        params
    ).fetchall()
    return rows


# ─────────────────────────────────────────────────────────────────────
#  GET /api/stats
# ─────────────────────────────────────────────────────────────────────
@api_bp.route("/stats")
def api_stats():
    db = get_db()
    total    = db.execute("SELECT COUNT(*) FROM components").fetchone()[0]
    ruptures = db.execute("SELECT COUNT(*) FROM components WHERE quantity = 0").fetchone()[0]
    bas      = db.execute(
        "SELECT COUNT(*) FROM components WHERE quantity > 0 AND min_stock > 0 AND quantity <= min_stock"
    ).fetchone()[0]
    places   = db.execute(
        "SELECT COUNT(*) FROM components WHERE location IS NOT NULL AND location != ''"
    ).fetchone()[0]
    valeur   = db.execute(
        "SELECT COALESCE(SUM(quantity * unit_price), 0) FROM components"
    ).fetchone()[0]
    projets  = db.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    return jsonify({
        "total":      total,
        "ruptures":   ruptures,
        "bas":        bas,
        "ok":         total - ruptures - bas,
        "places":     places,
        "non_places": total - places,
        "ateliers":   len(AtelierModel.get_all()),
        "projets":    projets,
        "valeur_totale": round(valeur, 2),
    })


# ─────────────────────────────────────────────────────────────────────
#  GET /api/stock
# ─────────────────────────────────────────────────────────────────────
@api_bp.route("/stock", methods=["GET"])
def api_stock():
    page     = max(1, int(request.args.get("page", 1)))
    per_page = min(200, max(1, int(request.args.get("per_page", 50))))
    q        = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    atelier  = request.args.get("atelier", "").strip()
    stock_f  = request.args.get("stock_filter", "").strip()
    sort     = request.args.get("sort", "description").strip()
    order    = "DESC" if request.args.get("order", "asc").lower() == "desc" else "ASC"

    allowed_sorts = {"description", "quantity", "category", "manufacturer", "unit_price", "updated_at"}
    if sort not in allowed_sorts:
        sort = "description"

    where, params = [], []
    if q:
        where.append("(description LIKE ? OR manufacture_part_number LIKE ? OR lcsc_part_number LIKE ? OR manufacturer LIKE ?)")
        like = f"%{q}%"
        params += [like, like, like, like]
    if category:
        where.append("category LIKE ?")
        params.append(f"%{category}%")
    if atelier:
        where.append("location LIKE ?")
        params.append(f"{atelier}:%")
    if stock_f == "rupture":
        where.append("quantity = 0")
    elif stock_f == "bas":
        where.append("quantity > 0 AND min_stock > 0 AND quantity <= min_stock")
    elif stock_f == "ok":
        where.append("(min_stock = 0 OR quantity > min_stock) AND quantity > 0")

    db       = get_db()
    sql_w    = ("WHERE " + " AND ".join(where)) if where else ""
    total    = db.execute(f"SELECT COUNT(*) FROM components {sql_w}", params).fetchone()[0]
    offset   = (page - 1) * per_page
    rows     = _stock_query(where, params, extra=f"ORDER BY {sort} {order}", limit=per_page, offset=offset)

    return jsonify({
        "page":       page,
        "per_page":   per_page,
        "total":      total,
        "pages":      (total + per_page - 1) // per_page,
        "components": [_comp_dict(r) for r in rows],
    })


# ─────────────────────────────────────────────────────────────────────
#  GET /api/stock/search?q=
# ─────────────────────────────────────────────────────────────────────
@api_bp.route("/stock/search")
def api_stock_search():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    like = f"%{q}%"
    rows = _stock_query(
        ["(description LIKE ? OR manufacture_part_number LIKE ? OR lcsc_part_number LIKE ? OR manufacturer LIKE ?)"],
        [like, like, like, like],
        extra="ORDER BY description",
        limit=20, offset=0
    )
    return jsonify([_comp_dict(r) for r in rows])


# ─────────────────────────────────────────────────────────────────────
#  GET /api/stock/<id>
# ─────────────────────────────────────────────────────────────────────
@api_bp.route("/stock/<int:comp_id>")
def api_stock_detail(comp_id):
    rows = _stock_query(["id = ?"], [comp_id])
    if not rows:
        return jsonify({"error": "Composant introuvable"}), 404
    return jsonify(_comp_dict(rows[0]))


# ─────────────────────────────────────────────────────────────────────
#  POST /api/stock — créer un composant
# ─────────────────────────────────────────────────────────────────────
@api_bp.route("/stock", methods=["POST"])
def api_stock_create():
    data = request.get_json(force=True, silent=True) or {}
    if not data.get("description"):
        return jsonify({"ok": False, "error": "description requis"}), 400
    try:
        comp_id = ComponentModel.create(data)
        if comp_id:
            MovementModel.record(comp_id, "init", data.get("quantity", 0), note="Créé via API")
            return jsonify({"ok": True, "id": comp_id}), 201
        return jsonify({"ok": False, "error": "Erreur création"}), 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ─────────────────────────────────────────────────────────────────────
#  PUT /api/stock/<id> — modifier un composant
# ─────────────────────────────────────────────────────────────────────
@api_bp.route("/stock/<int:comp_id>", methods=["PUT"])
def api_stock_update(comp_id):
    data = request.get_json(force=True, silent=True) or {}
    if not data:
        return jsonify({"ok": False, "error": "Données manquantes"}), 400
    try:
        ComponentModel.update(comp_id, data)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ─────────────────────────────────────────────────────────────────────
#  DELETE /api/stock/<id>
# ─────────────────────────────────────────────────────────────────────
@api_bp.route("/stock/<int:comp_id>", methods=["DELETE"])
def api_stock_delete(comp_id):
    db  = get_db()
    row = db.execute("SELECT id FROM components WHERE id=?", (comp_id,)).fetchone()
    if not row:
        return jsonify({"ok": False, "error": "Composant introuvable"}), 404
    try:
        ComponentModel.delete(comp_id)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ─────────────────────────────────────────────────────────────────────
#  POST /api/stock/<id>/adjust — ajuster la quantité
# ─────────────────────────────────────────────────────────────────────
@api_bp.route("/stock/<int:comp_id>/adjust", methods=["POST"])
def api_stock_adjust(comp_id):
    data     = request.get_json(force=True, silent=True) or {}
    absolute = data.get("absolute")
    note     = data.get("note", "")

    comp = ComponentModel.get_by_id(comp_id)
    if not comp:
        return jsonify({"ok": False, "error": "Composant introuvable"}), 404

    # delta ou absolute
    if absolute is not None:
        try:
            delta = int(absolute) - comp.quantity
        except (ValueError, TypeError):
            return jsonify({"ok": False, "error": "Paramètre absolute invalide"}), 400
    else:
        try:
            delta = int(data.get("delta", 0))
        except (ValueError, TypeError):
            return jsonify({"ok": False, "error": "Paramètre delta invalide"}), 400

    if delta == 0:
        return jsonify({"ok": True, "new_qty": comp.quantity, "message": "Aucun changement"})

    result = ComponentModel.adjust_quantity(comp_id, delta)
    if result["ok"]:
        try:
            MovementModel.record(
                comp_id,
                "in" if delta > 0 else "out",
                abs(delta),
                note=note or None
            )
        except Exception:
            pass
        return jsonify({
            "ok":      True,
            "new_qty": result["new_qty"],
            "delta":   delta,
            "is_low":  result.get("is_low", False),
        })
    return jsonify({"ok": False, "error": result.get("error", "Erreur")}), 400


# ─────────────────────────────────────────────────────────────────────
#  GET /api/categories
# ─────────────────────────────────────────────────────────────────────
@api_bp.route("/categories")
def api_categories():
    db   = get_db()
    rows = db.execute("""
        SELECT category, COUNT(*) as count
        FROM components
        WHERE category IS NOT NULL AND category != ''
        GROUP BY category
        ORDER BY count DESC, category
    """).fetchall()
    return jsonify([{"name": r["category"], "count": r["count"]} for r in rows])


# ─────────────────────────────────────────────────────────────────────
#  GET /api/rangement
# ─────────────────────────────────────────────────────────────────────
@api_bp.route("/rangement")
def api_rangement():
    ateliers = AtelierModel.get_all()
    result   = []
    for a in ateliers:
        aid    = a["id"]
        config = AtelierModel.get_rangement_config(aid)
        assign = AtelierModel.get_rangement_assign(aid)
        stats  = {}
        for p in config.get("plateaux", []):
            pid    = p["id"]
            total  = p["cols"] * p["rows"]
            filled = sum(1 for k, v in assign.items() if k.startswith(pid) and v)
            stats[pid] = {"total": total, "filled": filled}
        result.append({
            "id":       aid,
            "name":     a["name"],
            "emoji":    a.get("emoji", ""),
            "color":    a.get("color", "#7c3aed"),
            "plateaux": config.get("plateaux", []),
            "stats":    stats,
        })
    return jsonify(result)


# ─────────────────────────────────────────────────────────────────────
#  GET /api/rangement/<atelier_id>
# ─────────────────────────────────────────────────────────────────────
@api_bp.route("/rangement/<atelier_id>")
def api_rangement_atelier(atelier_id):
    atelier = AtelierModel.get(atelier_id)
    if not atelier:
        return jsonify({"error": "Atelier introuvable"}), 404

    db              = get_db()
    config          = AtelierModel.get_rangement_config(atelier_id)
    assign          = AtelierModel.get_rangement_assign(atelier_id)
    sizes           = AtelierModel.get_rangement_sizes(atelier_id)
    plateau_filter  = request.args.get("plateau", "").strip().upper()

    # Charger les composants assignés en une seule requête
    comp_ids = [v for v in assign.values() if v]
    comps    = {}
    if comp_ids:
        ph   = ",".join("?" * len(comp_ids))
        rows = db.execute(
            f"""SELECT id, description, manufacture_part_number, lcsc_part_number,
                       package, category, manufacturer, quantity, min_stock,
                       unit_price, location, image_path, notes, datasheet_url,
                       created_at, updated_at
                FROM components WHERE id IN ({ph})""",
            comp_ids
        ).fetchall()
        comps = {str(r["id"]): _comp_dict(r) for r in rows}

    plateaux_out = []
    for p in config.get("plateaux", []):
        pid = p["id"]
        if plateau_filter and pid != plateau_filter:
            continue
        cols, rows_n = p["cols"], p["rows"]

        # Cases absorbées par les grandes boîtes
        absorbed = set()
        for cell_id, size in sizes.items():
            if not cell_id.startswith(pid): continue
            suffix = cell_id[len(pid):]
            if not suffix.isdigit(): continue
            idx = int(suffix)
            if idx < 1 or idx > cols * rows_n: continue
            if "x" not in size: continue
            sw, sh = map(int, size.split("x"))
            if sw == 1 and sh == 1: continue
            col = (idx - 1) % cols
            row = (idx - 1) // cols
            for r in range(row, row + sh):
                for c in range(col, col + sw):
                    if r == row and c == col: continue
                    absorbed.add(f"{pid}{r * cols + c + 1}")

        cells = []
        for i in range(1, cols * rows_n + 1):
            cell_id = f"{pid}{i}"
            if cell_id in absorbed:
                cells.append({"cell_id": cell_id, "index": i, "size": "1x1",
                               "component": None, "stock_state": "absorbed"})
                continue
            comp_id = str(assign.get(cell_id, "") or "")
            size    = sizes.get(cell_id, "1x1")
            comp    = comps.get(comp_id) if comp_id else None
            cells.append({
                "cell_id":     cell_id,
                "index":       i,
                "size":        size,
                "component":   comp,
                "stock_state": comp["stock_state"] if comp else "empty",
            })

        plateaux_out.append({
            "id":    pid,
            "label": p.get("label", f"Plateau {pid}"),
            "cols":  cols,
            "rows":  rows_n,
            "cells": cells,
        })

    return jsonify({
        "atelier_id": atelier_id,
        "name":       atelier["name"],
        "emoji":      atelier.get("emoji", ""),
        "color":      atelier.get("color", "#7c3aed"),
        "plateaux":   plateaux_out,
    })


# ─────────────────────────────────────────────────────────────────────
#  GET /api/historique
# ─────────────────────────────────────────────────────────────────────
@api_bp.route("/historique")
def api_historique():
    page     = max(1, int(request.args.get("page", 1)))
    per_page = min(200, max(1, int(request.args.get("per_page", 50))))
    type_f   = request.args.get("type", "").strip()
    comp_f   = request.args.get("component_id", "").strip()

    db     = get_db()
    tables = {r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}

    if "stock_movements" not in tables:
        return jsonify({"page": 1, "per_page": per_page, "total": 0,
                        "pages": 0, "movements": []})

    where, params = [], []
    if type_f:
        where.append("m.type = ?")
        params.append(type_f)
    if comp_f:
        where.append("m.component_id = ?")
        params.append(int(comp_f))

    sql_w  = ("WHERE " + " AND ".join(where)) if where else ""
    total  = db.execute(f"SELECT COUNT(*) FROM stock_movements m {sql_w}", params).fetchone()[0]
    offset = (page - 1) * per_page
    rows   = db.execute(f"""
        SELECT m.id, m.component_id, m.type, m.quantity, m.note,
               m.project_id, m.created_at,
               c.description, c.manufacture_part_number, c.location,
               c.image_path, p.name AS project_name
        FROM stock_movements m
        LEFT JOIN components c ON c.id = m.component_id
        LEFT JOIN projects   p ON p.id = m.project_id
        {sql_w}
        ORDER BY m.created_at DESC
        LIMIT ? OFFSET ?
    """, params + [per_page, offset]).fetchall()

    type_labels = {
        "in": "entrée", "out": "sortie", "adjust": "ajustement",
        "init": "initialisation", "project_use": "utilisation projet",
        "project_return": "retour projet",
    }
    movements = []
    for r in rows:
        movements.append({
            "id":             r["id"],
            "component_id":   r["component_id"],
            "name":           _safe(r["manufacture_part_number"] or r["description"] or ""),
            "description":    _safe(r["description"] or ""),
            "location":       r["location"] or "",
            "type":           r["type"],
            "type_label":     type_labels.get(r["type"], r["type"]),
            "quantity":       r["quantity"],
            "note":           r["note"] or "",
            "project_id":     r["project_id"],
            "project_name":   r["project_name"] or "",
            "created_at":     r["created_at"],
        })

    return jsonify({
        "page":      page,
        "per_page":  per_page,
        "total":     total,
        "pages":     (total + per_page - 1) // per_page,
        "movements": movements,
    })


# ─────────────────────────────────────────────────────────────────────
#  GET /api/projets
# ─────────────────────────────────────────────────────────────────────
@api_bp.route("/projets")
def api_projets():
    projets = ProjectModel.get_all()
    return jsonify([{
        "id":          p.id,
        "name":        p.name,
        "description": p.description or "",
        "status":      p.status or "active",
        "created_at":  str(p.created_at) if hasattr(p, "created_at") else "",
    } for p in projets])


# ─────────────────────────────────────────────────────────────────────
#  GET /api/projets/<id>
# ─────────────────────────────────────────────────────────────────────
@api_bp.route("/projets/<int:project_id>")
def api_projet_detail(project_id):
    projet = ProjectModel.get_by_id(project_id)
    if not projet:
        return jsonify({"error": "Projet introuvable"}), 404
    components = ProjectModel.get_components(project_id)
    return jsonify({
        "id":          projet.id,
        "name":        projet.name,
        "description": projet.description or "",
        "status":      projet.status or "active",
        "components":  [{
            "component_id": c.component_id,
            "name":         _safe(c.description or ""),
            "lcsc_ref":     c.lcsc_ref or "",
            "quantity":     c.quantity,
            "quantity_used": c.quantity_used if hasattr(c, "quantity_used") else 0,
            "notes":        c.notes or "",
            "location":     c.location or "",
        } for c in components],
    })


# ─────────────────────────────────────────────────────────────────────
#  POST /api/projets — créer
# ─────────────────────────────────────────────────────────────────────
@api_bp.route("/projets", methods=["POST"])
def api_projet_create():
    data = request.get_json(force=True, silent=True) or {}
    if not data.get("name"):
        return jsonify({"ok": False, "error": "name requis"}), 400
    try:
        project_id = ProjectModel.create(data)
        return jsonify({"ok": True, "id": project_id}), 201
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ─────────────────────────────────────────────────────────────────────
#  PUT /api/projets/<id> — modifier
# ─────────────────────────────────────────────────────────────────────
@api_bp.route("/projets/<int:project_id>", methods=["PUT"])
def api_projet_update(project_id):
    data = request.get_json(force=True, silent=True) or {}
    try:
        ProjectModel.update(project_id, data)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ─────────────────────────────────────────────────────────────────────
#  DELETE /api/projets/<id>
# ─────────────────────────────────────────────────────────────────────
@api_bp.route("/projets/<int:project_id>", methods=["DELETE"])
def api_projet_delete(project_id):
    try:
        ProjectModel.delete(project_id)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ─────────────────────────────────────────────────────────────────────
#  POST /api/projets/<id>/components — ajouter composant
# ─────────────────────────────────────────────────────────────────────
@api_bp.route("/projets/<int:project_id>/components", methods=["POST"])
def api_projet_add_component(project_id):
    data     = request.get_json(force=True, silent=True) or {}
    comp_id  = data.get("component_id")
    quantity = data.get("quantity", 1)
    notes    = data.get("notes", "")
    if not comp_id:
        return jsonify({"ok": False, "error": "component_id requis"}), 400
    try:
        ProjectModel.add_component(project_id, comp_id, quantity, notes)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ─────────────────────────────────────────────────────────────────────
#  DELETE /api/projets/<id>/components/<comp_id>
# ─────────────────────────────────────────────────────────────────────
@api_bp.route("/projets/<int:project_id>/components/<int:comp_id>", methods=["DELETE"])
def api_projet_remove_component(project_id, comp_id):
    try:
        ProjectModel.remove_component(project_id, comp_id)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ─────────────────────────────────────────────────────────────────────
#  POST /api/projets/<id>/components/<comp_id>/use
# ─────────────────────────────────────────────────────────────────────
@api_bp.route("/projets/<int:project_id>/components/<int:comp_id>/use", methods=["POST"])
def api_projet_use_component(project_id, comp_id):
    data     = request.get_json(force=True, silent=True) or {}
    quantity = int(data.get("quantity", 1))
    comp     = ComponentModel.get_by_id(comp_id)
    if not comp:
        return jsonify({"ok": False, "error": "Composant introuvable"}), 404
    if comp.quantity < quantity:
        return jsonify({"ok": False, "error": "Stock insuffisant",
                        "available": comp.quantity}), 400
    result = ComponentModel.adjust_quantity(comp_id, -quantity)
    if result["ok"]:
        MovementModel.record(comp_id, "project_use", quantity,
                             note=f"Projet #{project_id}", project_id=project_id)
        return jsonify({"ok": True, "new_qty": result["new_qty"]})
    return jsonify({"ok": False, "error": result.get("error")}), 400


# ─────────────────────────────────────────────────────────────────────
#  POST /api/projets/<id>/components/<comp_id>/return
# ─────────────────────────────────────────────────────────────────────
@api_bp.route("/projets/<int:project_id>/components/<int:comp_id>/return", methods=["POST"])
def api_projet_return_component(project_id, comp_id):
    data     = request.get_json(force=True, silent=True) or {}
    quantity = int(data.get("quantity", 1))
    result   = ComponentModel.adjust_quantity(comp_id, quantity)
    if result["ok"]:
        MovementModel.record(comp_id, "project_return", quantity,
                             note=f"Retour projet #{project_id}", project_id=project_id)
        return jsonify({"ok": True, "new_qty": result["new_qty"]})
    return jsonify({"ok": False, "error": result.get("error")}), 400


# ─────────────────────────────────────────────────────────────────────
#  LEDs — proxy vers les routes LED existantes
# ─────────────────────────────────────────────────────────────────────
@api_bp.route("/led/on", methods=["POST"])
def api_led_on():
    """Allume une LED. Body JSON identique à /api/led/<cell>/on."""
    from .routes_led import led_on as _led_on
    return _led_on()


@api_bp.route("/led/off", methods=["POST"])
def api_led_off():
    from .routes_led import led_off as _led_off
    return _led_off()


@api_bp.route("/led/status")
def api_led_status():
    from .routes_led import led_status as _led_status
    return _led_status()


@api_bp.route("/led/ping")
def api_led_ping():
    from .routes_led import led_ping as _led_ping
    return _led_ping()
