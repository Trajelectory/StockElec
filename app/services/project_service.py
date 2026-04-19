"""
project_service.py — Logique métier pour les projets.

Contient :
  - Constantes de colonnes CSV reconnues (_LCSC_COLS, _MOUSER_COLS, etc.)
  - Analyse et import de BOM KiCad (_analyse_bom, _find_col)
  - Gestion des images projet (_save_project_image, _delete_project_image,
    _generate_color_banner)

Les routes Flask sont dans controllers/routes_projects.py.
"""

import os
import csv
import io
import uuid
import logging
import threading

from flask import current_app

from ..models.component import ComponentModel
from ..models.project import ProjectModel
from ..models.settings import SettingsModel
from ..models.database import get_db
from ..services import lcsc_scraper, mouser_scraper, digikey_scraper

logger = logging.getLogger(__name__)

# ── Constantes de colonnes CSV ─────────────────────────────────────────────

# Noms de colonnes LCSC reconnus (insensible à la casse)
_LCSC_COLS = [
    "lcsc part number",
    "lcsc#",
    "lcsc part #", "lcsc part", "lcsc",
    "lcsc_part_number",
    "supplier part number", "supplier part #",
    "lcsc number", "lcsc no",
]

# Noms de colonnes Mouser reconnus
_MOUSER_COLS = [
    "mouser", "mouser part number", "mouser part #",
    "mouser#", "mouser_part_number", "mouser no", "mouser number",
]

# Noms de colonnes DigiKey reconnus
_DIGIKEY_COLS = [
    "digikey", "digi-key", "digikey part number", "digikey part #",
    "digikey#", "digikey_part_number", "dk part number", "dk#",
]

# Noms de colonnes quantité reconnus
_QTY_COLS = [
    "quantity", "qty", "quantite", "quantité", "qté", "amount",
]

# Noms de colonnes désignateur (R1, C2…)
_REF_COLS = [
    "reference", "ref", "designator", "references", "designators",
    "refdes", "designation",
]

# Noms de colonnes valeur/description
_VAL_COLS = [
    "value", "comment", "description", "val", "designation", "valeur",
    "mpn",
]

# ── Extensions et magic bytes images ──────────────────────────────────────

_ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

_IMAGE_MAGIC = {
    b"\xff\xd8\xff": ".jpg",
    b"\x89PNG":      ".png",
    b"GIF8":         ".gif",
    b"RIFF":         ".webp",
}


# ══════════════════════════════════════════════════════════════════════════
#  Helpers BOM
# ══════════════════════════════════════════════════════════════════════════

def find_col(headers: list[str], candidates: list[str]) -> str | None:
    """Retourne le premier header qui matche un candidat (insensible casse)."""
    lc = {h.lower().strip(): h for h in headers}
    for c in candidates:
        if c in lc:
            return lc[c]
    return None


def analyse_bom(rows: list[dict], project_id: int) -> dict | None:
    """
    Analyse les lignes CSV et compare avec le stock.
    Supporte les colonnes LCSC, Mouser et/ou DigiKey.
    Retourne None si aucune colonne de référence n'est détectée.
    """
    headers     = list(rows[0].keys())
    lcsc_col    = find_col(headers, _LCSC_COLS)
    mouser_col  = find_col(headers, _MOUSER_COLS)
    digikey_col = find_col(headers, _DIGIKEY_COLS)

    if not lcsc_col and not mouser_col and not digikey_col:
        return None

    qty_col = find_col(headers, _QTY_COLS)
    ref_col = find_col(headers, _REF_COLS)
    val_col = find_col(headers, _VAL_COLS)

    db = get_db()

    ok_list  = []
    low      = []
    missing  = []
    no_lcsc  = []
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
            # Complète les refs manquantes si nécessaire
            existing_refs = db.execute(
                "SELECT lcsc_part_number, mouser_part_number, digikey_part_number "
                "FROM components WHERE id=?", (comp_id,)
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
                    db.execute(
                        f"UPDATE components SET {fields} WHERE id = ?",
                        list(updates.values()) + [comp_id]
                    )
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
                ok_list.append(entry)
            else:
                low.append(entry)
        else:
            comp_data = {
                "description":      "",
                "description_long": val or "",
                "quantity":         0,
                "min_stock":        0,
            }
            if has_lcsc:    comp_data["lcsc_part_number"]    = lcsc_ref
            if has_mouser:  comp_data["mouser_part_number"]  = mouser_ref
            if has_digikey: comp_data["digikey_part_number"] = digikey_ref
            comp_id = ComponentModel.create(comp_data)

            if has_lcsc:    new_ids.append((comp_id, lcsc_ref))
            if has_mouser:  new_mouser_ids.append((comp_id, mouser_ref))
            if has_digikey: new_digikey_ids.append((comp_id, digikey_ref))

            entry.update({
                "component_id": comp_id,
                "description":  val or lcsc_ref or mouser_ref or digikey_ref,
                "stock_qty":    0,
                "unit_price":   None,
                "image_path":   None,
                "created":      True,
            })
            missing.append(entry)

    # ── Enrichissement en arrière-plan ─────────────────────────────────
    _app = current_app._get_current_object()

    if new_ids:
        def _enrich_lcsc():
            with _app.app_context():
                for cid, ref in new_ids:
                    try:
                        info = lcsc_scraper.enrich_component(ref)
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
                for cid, ref in new_mouser_ids:
                    try:
                        info = mouser_scraper.enrich_component(ref, api_key)
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
                for cid, ref in new_digikey_ids:
                    try:
                        info = digikey_scraper.enrich_component(ref, client_id, client_secret)
                        if info:
                            ComponentModel.apply_enrichment(cid, info)
                    except Exception as e:
                        logger.debug("Ignored: %s", e)
        threading.Thread(target=_enrich_digikey, daemon=True).start()

    return {
        "lcsc_col":    lcsc_col,
        "mouser_col":  mouser_col,
        "digikey_col": digikey_col,
        "qty_col":     qty_col,
        "ref_col":     ref_col,
        "val_col":     val_col,
        "ok":          ok_list,
        "low":         low,
        "missing":     missing,
        "no_lcsc":     no_lcsc,
        "new_count":   len(new_ids) + len(new_mouser_ids) + len(new_digikey_ids),
    }


# ══════════════════════════════════════════════════════════════════════════
#  Helpers images projet
# ══════════════════════════════════════════════════════════════════════════

def save_project_image(file_storage) -> str | None:
    """
    Sauvegarde l'image uploadée dans instance/project_images/.
    Vérifie les magic bytes avant d'accepter le fichier.
    Retourne le nom de fichier (relatif) ou None si échec.
    """
    if not file_storage or not file_storage.filename:
        return None

    # Vérification magic bytes — ne pas se fier au Content-Type déclaré
    header = file_storage.read(12)
    file_storage.seek(0)

    ext = ""
    for magic, candidate_ext in _IMAGE_MAGIC.items():
        if header.startswith(magic):
            ext = candidate_ext
            break

    # Fallback sur l'extension déclarée si magic bytes inconnus
    if not ext:
        ext = os.path.splitext(file_storage.filename)[-1].lower()

    if ext not in _ALLOWED_EXTS:
        return None

    images_dir = os.path.join(current_app.instance_path, "project_images")
    os.makedirs(images_dir, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ext}"
    file_storage.save(os.path.join(images_dir, filename))
    return filename


def generate_color_banner(hex_color: str) -> str | None:
    """
    Génère une image PNG de bannière 800×200 avec la couleur choisie.
    Retourne le nom de fichier ou None si PIL n'est pas disponible.
    """
    try:
        from PIL import Image as PilImage
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        img = PilImage.new("RGB", (800, 200), (r, g, b))
        images_dir = os.path.join(current_app.instance_path, "project_images")
        os.makedirs(images_dir, exist_ok=True)
        filename = f"banner_{uuid.uuid4().hex}.png"
        img.save(os.path.join(images_dir, filename))
        return filename
    except Exception as e:
        logger.debug("Ignored: %s", e)
        return None


def delete_project_image(image_path: str | None) -> None:
    """Supprime le fichier image projet si il existe sur le disque."""
    if not image_path:
        return
    images_dir = os.path.join(current_app.instance_path, "project_images")
    filepath = os.path.join(images_dir, image_path)
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
    except OSError as e:
        logger.debug("Ignored: %s", e)
