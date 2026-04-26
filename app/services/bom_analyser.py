"""
bom_analyser.py — Analyse de BOM CSV pour les projets StockEleK
Extrait de project_controller.py (audit P2)
"""
import re
import threading
from ..models.component import ComponentModel
from ..models.settings import SettingsModel
from ..services import lcsc_scraper, mouser_scraper, digikey_scraper

def _find_col(headers: list[str], candidates: list[str]) -> str | None:
    """Retourne le premier header (original) qui matche un candidat (insensible casse)."""
    lc = {h.lower().strip(): h for h in headers}
    for c in candidates:
        if c in lc:
            return lc[c]
    return None


def _analyse_bom(rows: list[dict], project_id: int) -> dict | None:
    """
    Analyse les lignes CSV et compare avec le stock.
    Supporte les colonnes LCSC, Mouser et/ou DigiKey.
    """

    headers    = list(rows[0].keys())
    lcsc_col   = _find_col(headers, _LCSC_COLS)
    mouser_col = _find_col(headers, _MOUSER_COLS)
    digikey_col = _find_col(headers, _DIGIKEY_COLS)

    if not lcsc_col and not mouser_col and not digikey_col:
        return None

    qty_col = _find_col(headers, _QTY_COLS)
    ref_col = _find_col(headers, _REF_COLS)
    val_col = _find_col(headers, _VAL_COLS)

    db = get_db()

    ok      = []
    low     = []
    missing = []
    no_lcsc = []
    new_ids        = []
    new_mouser_ids  = []
    new_digikey_ids = []

    already = {
        pc.component_id
        for pc in ProjectModel.get_components(project_id)
    }

    for row in rows:
        lcsc_ref    = " ".join(row.get(lcsc_col,    "").split()).upper() if lcsc_col    else ""
        mouser_ref  = " ".join(row.get(mouser_col,  "").split())        if mouser_col  else ""
        digikey_ref = " ".join(row.get(digikey_col, "").split())        if digikey_col else ""
        qty_raw     = row.get(qty_col, "1").strip() if qty_col else "1"
        ref         = row.get(ref_col, "").strip()  if ref_col else ""
        val         = row.get(val_col, "").strip()  if val_col else ""

        try:
            bom_qty = int(qty_raw)
        except ValueError:
            bom_qty = max(1, qty_raw.count(",") + 1) if qty_raw else 1

        _empty = ("", "~", "na", "n/a", "-")
        has_lcsc    = lcsc_ref.lower()    not in _empty and bool(lcsc_ref)
        has_mouser  = mouser_ref.lower()  not in _empty and bool(mouser_ref)
        has_digikey = digikey_ref.lower() not in _empty and bool(digikey_ref)

        if not has_lcsc and not has_mouser and not has_digikey:
            no_lcsc.append({"ref": ref, "value": val, "qty": bom_qty, "lcsc": "—"})
            continue

        # Cherche dans le stock — LCSC > Mouser > DigiKey
        stock_row = None
        if has_lcsc:
            stock_row = db.execute(
                "SELECT id, description, quantity, unit_price, image_path "
                "FROM components WHERE lcsc_part_number = ?", (lcsc_ref,)
            ).fetchone()
        if not stock_row and has_mouser:
            stock_row = db.execute(
                "SELECT id, description, quantity, unit_price, image_path "
                "FROM components WHERE mouser_part_number = ?", (mouser_ref,)
            ).fetchone()
        if not stock_row and has_digikey:
            stock_row = db.execute(
                "SELECT id, description, quantity, unit_price, image_path "
                "FROM components WHERE digikey_part_number = ?", (digikey_ref,)
            ).fetchone()

        entry = {
            "lcsc":    lcsc_ref or mouser_ref or digikey_ref,
            "mouser":  mouser_ref,
            "digikey": digikey_ref,
            "ref":     ref,
            "value":   val,
            "bom_qty": bom_qty,
            "already": False,
            "source":  "lcsc" if has_lcsc else ("mouser" if has_mouser else "digikey"),
        }

        if stock_row:
            comp_id = stock_row["id"]
            # Met à jour les refs manquantes sur le composant existant (1 seul SELECT)
            existing_refs = db.execute(
                "SELECT lcsc_part_number, mouser_part_number, digikey_part_number FROM components WHERE id=?",
                (comp_id,)
            ).fetchone()
            updates = {}
            if has_mouser  and not existing_refs["mouser_part_number"]:
                updates["mouser_part_number"]  = mouser_ref
            if has_digikey and not existing_refs["digikey_part_number"]:
                updates["digikey_part_number"] = digikey_ref
            if has_lcsc    and not existing_refs["lcsc_part_number"]:
                updates["lcsc_part_number"]    = lcsc_ref
            if updates:
                fields = ", ".join(f"{k} = ?" for k in updates)
                try:
                    db.execute(f"UPDATE components SET {fields} WHERE id = ?",
                               list(updates.values()) + [comp_id])
                    db.commit()
                except Exception:
                    db.rollback()
                    raise

            entry.update({
                "component_id": comp_id,
                "description":  stock_row["description"],
                "stock_qty":    stock_row["quantity"],
                "unit_price":   stock_row["unit_price"],
                "image_path":   stock_row["image_path"],
                "already":      comp_id in already,
            })
            if stock_row["quantity"] >= bom_qty:
                ok.append(entry)
            else:
                low.append(entry)
        else:
            comp_data = {
                # description laissé vide : l'enrich API le remplira avec le vrai nom
                # val (valeur KiCad ex: "10K", "100nF") va en description_long comme fallback
                "description":      "",
                "description_long": val or "",
                "quantity":         0,
                "min_stock":        0,
            }
            if has_lcsc:
                comp_data["lcsc_part_number"]    = lcsc_ref
            if has_mouser:
                comp_data["mouser_part_number"]  = mouser_ref
            if has_digikey:
                comp_data["digikey_part_number"] = digikey_ref
            comp_id = ComponentModel.create(comp_data)

            # Enrichissement : toutes les sources disponibles
            if has_lcsc:
                new_ids.append((comp_id, lcsc_ref))
            if has_mouser:
                new_mouser_ids.append((comp_id, mouser_ref))
            if has_digikey:
                new_digikey_ids.append((comp_id, digikey_ref))

            entry.update({
                "component_id": comp_id,
                "description":  val or lcsc_ref or mouser_ref or digikey_ref,  # pour le rapport BOM
                "stock_qty":    0,
                "unit_price":   None,
                "image_path":   None,
                "created":      True,
            })
            missing.append(entry)

    # Enrichissement en arrière-plan — tous avec app_context pour accès SQLite
    from flask import current_app as _ca
    _app = _ca._get_current_object()

    if new_ids:
    
        def _enrich_lcsc():
            with _app.app_context():
                for cid, lcsc_ref in new_ids:
                    try:
                        info = lcsc_scraper.enrich_component(lcsc_ref)
                        if info:
                            ComponentModel.apply_enrichment(cid, info)
                    except Exception as e:
                        logger.debug("Ignored: %s", e)

        threading.Thread(target=_enrich_lcsc, daemon=True).start()

    if new_mouser_ids:

        def _enrich_mouser():
            with _app.app_context():
                api_key = SettingsModel.get("mouser_api_key", "")
                if not api_key:
                    return
                for cid, mref in new_mouser_ids:
                    try:
                        info = mouser_scraper.enrich_component(mref, api_key)
                        if info:
                            ComponentModel.apply_enrichment(cid, info)
                    except Exception as e:
                        logger.debug("Ignored: %s", e)

        threading.Thread(target=_enrich_mouser, daemon=True).start()

    if new_digikey_ids:

        def _enrich_digikey():
            with _app.app_context():
                client_id     = SettingsModel.get("digikey_client_id", "")
                client_secret = SettingsModel.get("digikey_client_secret", "")
                if not client_id or not client_secret:
                    return
                for cid, dref in new_digikey_ids:
                    try:
                        info = digikey_scraper.enrich_component(dref, client_id, client_secret)
                        if info:
                            ComponentModel.apply_enrichment(cid, info)
                    except Exception as e:
                        logger.debug("Ignored: %s", e)

        threading.Thread(target=_enrich_digikey, daemon=True).start()

    return {
        "lcsc_col":     lcsc_col,
        "mouser_col":   mouser_col,
        "digikey_col":  digikey_col,
        "qty_col":      qty_col,
        "ref_col":      ref_col,
        "val_col":      val_col,
        "ok":           ok,
        "low":          low,
        "missing":      missing,
        "no_lcsc":      no_lcsc,
        "new_count":    len(new_ids) + len(new_mouser_ids) + len(new_digikey_ids),
    }
