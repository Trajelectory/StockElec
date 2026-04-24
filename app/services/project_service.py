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
            # Composant manquant — PAS de création en DB ici (side effect évité)
            # La création se fait dans apply_bom_result() après confirmation utilisateur
            entry.update({
                "component_id": None,
                "description":  val or lcsc_ref or mouser_ref or digikey_ref,
                "stock_qty":    0,
                "unit_price":   None,
                "image_path":   None,
            })
            missing.append(entry)

    # Note : plus d'enrichissement ici — analyse_bom() est purement lecture seule.
    # L'enrichissement se déclenche dans apply_bom_result() après confirmation.

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

MAX_PROJECT_IMAGE_SIZE = 3 * 1024 * 1024  # 3 Mo — limite pour les images de couverture


def save_project_image(file_storage) -> str | None:
    """
    Sauvegarde l'image uploadée dans instance/project_images/.
    Vérifie les magic bytes et la taille avant d'accepter le fichier.
    Retourne le nom de fichier (relatif) ou None si échec.
    """
    if not file_storage or not file_storage.filename:
        return None

    # Vérification magic bytes — ne pas se fier au Content-Type déclaré
    header = file_storage.read(12)
    rest   = file_storage.read()
    file_storage.seek(0)

    # Vérification taille — 3Mo max pour une image de couverture
    if len(header) + len(rest) > MAX_PROJECT_IMAGE_SIZE:
        logger.warning("[image] Fichier trop volumineux (%d Ko > 3 Mo)", (len(header)+len(rest))//1024)
        return None

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



def enrich_single_lcsc(comp_id: int, lcsc_ref: str, app) -> None:
    """Lance l'enrichissement LCSC d'un composant en arrière-plan."""
    def _run():
        with app.app_context():
            try:
                info = lcsc_scraper.enrich_component(lcsc_ref)
                if info:
                    ComponentModel.apply_enrichment(comp_id, info)
            except Exception as e:
                logger.debug("Ignored: %s", e)
    threading.Thread(target=_run, daemon=True).start()


# ══════════════════════════════════════════════════════════════════════════
#  apply_bom_result — Applique les résultats du rapport BOM
# ══════════════════════════════════════════════════════════════════════════

def apply_bom_result(project_id: int, form) -> dict:
    """
    Applique les composants sélectionnés dans le rapport BOM vers le projet.
    Crée les composants manquants en base et lance l'enrichissement en arrière-plan.

    Séparé de analyse_bom() pour éviter les side effects lors de l'analyse :
    les composants ne sont créés qu'après confirmation explicite de l'utilisateur.

    Retourne : {"added": int, "enrich_lcsc": int, "enrich_mouser": int, "enrich_digikey": int}
    """
    from flask import current_app
    from ..models.component import ComponentModel
    from ..models.project import ProjectModel
    from ..models.database import get_db
    from ..models.settings import SettingsModel

    db    = get_db()
    added = 0

    # ── 1. Composants existants cochés ──────────────────────────────
    component_ids = form.getlist("component_id")
    quantities    = form.getlist("quantity")
    for comp_id, qty in zip(component_ids, quantities):
        try:
            ProjectModel.add_component(project_id, int(comp_id), int(qty))
            added += 1
        except Exception as e:
            logger.debug("Ignored: %s", e)

    # ── 2. Composants manquants cochés → créer en base ───────────────
    missing_ids       = form.getlist("missing_id")
    to_enrich         = []
    to_enrich_mouser  = []
    to_enrich_digikey = []

    # Index en mémoire pour éviter N+1 queries
    all_rows    = db.execute(
        "SELECT id, lcsc_part_number, mouser_part_number, digikey_part_number FROM components"
    ).fetchall()
    idx_lcsc    = {r["lcsc_part_number"]:    r for r in all_rows if r["lcsc_part_number"]}
    idx_mouser  = {r["mouser_part_number"]:  r for r in all_rows if r["mouser_part_number"]}
    idx_digikey = {r["digikey_part_number"]: r for r in all_rows if r["digikey_part_number"]}

    for idx in missing_ids:
        qty         = form.get(f"missing_qty_{idx}",     0,  type=int)
        desc        = form.get(f"missing_desc_{idx}",    "")
        lcsc        = form.get(f"missing_lcsc_{idx}",    "").strip().upper()
        mouser_ref  = form.get(f"missing_mouser_{idx}",  "").strip()
        digikey_ref = form.get(f"missing_digikey_{idx}", "").strip()

        if not lcsc and not mouser_ref and not digikey_ref:
            continue

        existing = (idx_lcsc.get(lcsc) or idx_mouser.get(mouser_ref)
                    or idx_digikey.get(digikey_ref))

        if existing:
            comp_id = existing["id"]
            updates = {}
            if lcsc        and not existing["lcsc_part_number"]:    updates["lcsc_part_number"]    = lcsc
            if mouser_ref  and not existing["mouser_part_number"]:  updates["mouser_part_number"]  = mouser_ref
            if digikey_ref and not existing["digikey_part_number"]: updates["digikey_part_number"] = digikey_ref
            if updates:
                fields = ", ".join(f"{k} = ?" for k in updates)
                try:
                    db.execute(f"UPDATE components SET {fields} WHERE id = ?",
                               list(updates.values()) + [comp_id])
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
        else:
            comp_data = {"description": "", "description_long": desc or "",
                         "quantity": 0, "min_stock": 0}
            if lcsc:        comp_data["lcsc_part_number"]    = lcsc
            if mouser_ref:  comp_data["mouser_part_number"]  = mouser_ref
            if digikey_ref: comp_data["digikey_part_number"] = digikey_ref
            comp_id = ComponentModel.create(comp_data)
            if lcsc:        to_enrich.append((comp_id, lcsc))
            if mouser_ref:  to_enrich_mouser.append((comp_id, mouser_ref))
            if digikey_ref: to_enrich_digikey.append((comp_id, digikey_ref))

        try:
            ProjectModel.add_component(project_id, comp_id, max(1, qty))
            added += 1
        except Exception as e:
            logger.debug("Ignored: %s", e)

    # ── Enrichissement en arrière-plan ──────────────────────────────
    _app = current_app._get_current_object()

    if to_enrich:
        def _enrich_lcsc():
            with _app.app_context():
                for cid, ref in to_enrich:
                    try:
                        info = lcsc_scraper.enrich_component(ref)
                        if info: ComponentModel.apply_enrichment(cid, info)
                    except Exception as e:
                        logger.debug("Ignored: %s", e)
        threading.Thread(target=_enrich_lcsc, daemon=True).start()

    if to_enrich_mouser:
        def _enrich_mouser():
            with _app.app_context():
                api_key = SettingsModel.get("mouser_api_key", "")
                if not api_key: return
                from ..services import mouser_scraper as _ms
                for cid, ref in to_enrich_mouser:
                    try:
                        info = _ms.enrich_component(ref, api_key)
                        if info: ComponentModel.apply_enrichment(cid, info)
                    except Exception as e:
                        logger.debug("Ignored: %s", e)
        threading.Thread(target=_enrich_mouser, daemon=True).start()

    if to_enrich_digikey:
        def _enrich_digikey():
            with _app.app_context():
                client_id     = SettingsModel.get("digikey_client_id", "")
                client_secret = SettingsModel.get("digikey_client_secret", "")
                if not client_id or not client_secret: return
                from ..services import digikey_scraper as _dk
                for cid, ref in to_enrich_digikey:
                    try:
                        info = _dk.enrich_component(ref, client_id, client_secret)
                        if info: ComponentModel.apply_enrichment(cid, info)
                    except Exception as e:
                        logger.debug("Ignored: %s", e)
        threading.Thread(target=_enrich_digikey, daemon=True).start()

    return {
        "added":          added,
        "enrich_lcsc":    len(to_enrich),
        "enrich_mouser":  len(to_enrich_mouser),
        "enrich_digikey": len(to_enrich_digikey),
    }
