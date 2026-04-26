import os
import shutil
import json
import threading
import logging
import datetime
import tempfile
import zipfile
import time
import re as _re

logger = logging.getLogger(__name__)

from flask import (
    request,
    redirect,
    url_for,
    flash,
    send_file,
    render_template,
    Response,
    current_app,
)


from ..models.component import ComponentModel
from ..models.settings import SettingsModel
from ..models.database import get_db
from ..views.component_view import ComponentView
from ..services.easyeda import fetch_and_save
from .utils import _t
from . import component_bp
from .routes_misc import _enrich_async




def _settings_get_context(db):
    """Collecte les stats et paramètres pour la page settings (section GET)."""
    n_components = db.execute("SELECT COUNT(*) FROM components").fetchone()[0]
    n_projects   = db.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    n_no_image   = db.execute(
        "SELECT COUNT(*) FROM components WHERE image_path IS NULL OR image_path = ''"
    ).fetchone()[0]
    n_no_cat     = db.execute(
        "SELECT COUNT(*) FROM components WHERE category IS NULL OR category = ''"
    ).fetchone()[0]
    n_to_enrich  = db.execute(
        """SELECT COUNT(*) FROM components
           WHERE lcsc_part_number IS NOT NULL AND lcsc_part_number != ''
             AND (image_path IS NULL OR image_path = ''
                  OR category IS NULL OR category = '')"""
    ).fetchone()[0]
    n_no_easyeda = db.execute(
        """SELECT COUNT(*) FROM components
           WHERE lcsc_part_number IS NOT NULL AND lcsc_part_number != ''
             AND (symbol_png IS NULL OR symbol_png = ''
                  OR footprint_png IS NULL OR footprint_png = '')"""
    ).fetchone()[0]
    no_easyeda_list = db.execute(
        """SELECT id, description, lcsc_part_number, symbol_png, footprint_png
           FROM components
           WHERE lcsc_part_number IS NOT NULL AND lcsc_part_number != ''
             AND (symbol_png IS NULL OR symbol_png = ''
                  OR footprint_png IS NULL OR footprint_png = '')
           ORDER BY description"""
    ).fetchall()

    instance_path = os.path.abspath(current_app.instance_path)

    def dir_size(path):
        total = 0
        if os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                total += sum(os.path.getsize(os.path.join(root, f)) for f in files)
        return total

    db_size  = (os.path.getsize(os.path.join(instance_path, "stock.db"))
                if os.path.exists(os.path.join(instance_path, "stock.db")) else 0)
    img_size = dir_size(os.path.join(instance_path, "images"))
    prj_size = dir_size(os.path.join(instance_path, "project_images"))

    def fmt_size(b):
        if b < 1024:    return f"{b} o"
        if b < 1024**2: return f"{b/1024:.1f} Ko"
        return f"{b/1024**2:.1f} Mo"

    current = {
        "app_name":               SettingsModel.get("app_name", "StockElec"),
        "base_url":               SettingsModel.get("base_url", ""),
        "default_min_stock":      SettingsModel.get("default_min_stock", "0"),
        "home_recent_limit":      SettingsModel.get("home_recent_limit", "5"),
        "lang":                   SettingsModel.get("lang", "fr"),
        "mouser_api_key":         SettingsModel.get("mouser_api_key", ""),
        "digikey_client_id":      SettingsModel.get("digikey_client_id", ""),
        "digikey_client_secret":  SettingsModel.get("digikey_client_secret", ""),
        "esp32_url":              SettingsModel.get("esp32_url",      ""),
        "esp32_color":            SettingsModel.get("esp32_color",    "purple"),
        "esp32_duration":         SettingsModel.get("esp32_duration", "5"),
        "esp32_offsets":          SettingsModel.get("esp32_offsets",  "{}"),
        "esp32_token":            SettingsModel.get("esp32_token",    ""),
        "debug_toolbar":          SettingsModel.get("debug_toolbar",  "0"),
        "kicad_prefix":           SettingsModel.get("kicad_prefix",   "StockElec_"),
    }

    stats = {
        "n_components":    n_components,
        "n_projects":      n_projects,
        "n_no_image":      n_no_image,
        "n_no_cat":        n_no_cat,
        "n_to_enrich":     n_to_enrich,
        "n_no_easyeda":    n_no_easyeda,
        "no_easyeda_list": [dict(r) for r in no_easyeda_list],
        "db_size":         fmt_size(db_size),
        "img_size":        fmt_size(img_size),
        "prj_size":        fmt_size(prj_size),
        "total_size":      fmt_size(db_size + img_size + prj_size),
    }

    raw_rang = SettingsModel.get("rangement_config", "")
    try:
        config_plateaux = json.loads(raw_rang).get("plateaux", []) if raw_rang else []
    except Exception:
        config_plateaux = []

    return current, stats, config_plateaux

@component_bp.route("/alerts")
def alerts():
    low = ComponentModel.get_low_stock()
    return render_template("components/alerts.html", components=low)



# ------------------------------------------------------------------ #
#  Paramètres
# ------------------------------------------------------------------ #

@component_bp.route("/settings", methods=["GET", "POST"])
def settings():
    import os, shutil
    db = get_db()  # I1 FIX : une seule connexion pour toute la requête

    if request.method == "POST":
        action = request.form.get("action")
        logger.info("[Settings] POST action=%r fields=%r", action, list(request.form.keys()))

        # ── Paramètres généraux ──────────────────────────────────────
        if action == "save_general":
            # On ne sauvegarde QUE les clés réellement présentes dans le formulaire
            # pour éviter d'écraser les clés absentes (ex: clé API Mouser quand
            # on sauvegarde le formulaire DigiKey)
            ALL_KEYS = (
                "app_name", "base_url", "default_min_stock", "lang",
                "mouser_api_key", "digikey_client_id", "digikey_client_secret",
                "esp32_url", "esp32_color", "esp32_duration", "esp32_offsets",
                "esp32_token",
                "kicad_prefix",
                # Couleurs LED par catégorie
                "led_color_resistor", "led_color_capacitor", "led_color_inductor",
                "led_color_transistor", "led_color_diode", "led_color_led",
                "led_color_optoelectronic", "led_color_amplifier", "led_color_ic",
                "led_color_connector", "led_color_switch", "led_color_crystal",
                "led_color_fuse", "led_color_sensor", "led_color_power",
                "led_color_relay", "led_color_motor", "led_color_rf",
            )
            for key in ALL_KEYS:
                if key in request.form:
                    SettingsModel.set(key, request.form[key].strip())
            # Invalider le cache locale si la langue a changé
            import app as _app_module
            _app_module._locale_cache.clear()
            # Invalider le cache de détection P4 si l'URL ESP32 a changé
            if "esp32_url" in request.form:
                from .routes_led import clear_p4_cache
                clear_p4_cache()
            flash(_t("msg.settings_saved"), "success")

        # ── Debug toolbar ─────────────────────────────────────────────
        elif action == "save_debug":
            # hidden value="0" + checkbox value="1" → getlist retourne ["0","1"] si coché
            # ou ["0"] si décoché — on cherche si "1" est présent
            vals      = request.form.getlist("debug_toolbar")
            debug_val = "1" if "1" in vals else "0"
            SettingsModel.set("debug_toolbar", debug_val)
            flash(_t("msg.settings_saved"), "success")

        # ── Enrichissement en masse ──────────────────────────────────
        elif action == "enrich_all":
            rows = db.execute(
                """SELECT id, lcsc_part_number FROM components
                   WHERE lcsc_part_number IS NOT NULL AND lcsc_part_number != ''
                     AND (image_path IS NULL OR image_path = ''
                          OR category IS NULL OR category = '')"""
            ).fetchall()
            ids = [(r["id"], r["lcsc_part_number"]) for r in rows]
            if ids:
                _enrich_async(ids)
                flash(_t("msg.enrich_launched", n=len(ids)), "info")
            else:
                flash(_t("msg.all_enriched"), "success")

        # ── Vider l'historique des mouvements ───────────────────────
        elif action == "clear_history":
            count = db.execute("SELECT COUNT(*) FROM stock_movements").fetchone()[0]
            try:
                db.execute("DELETE FROM stock_movements")
                db.commit()
            except Exception:
                db.rollback()
                raise
            flash(_t("msg.history_cleared", n=count), "success")

        # ── Nettoyage images orphelines ──────────────────────────────
        elif action == "clean_images":
            instance_path = os.path.abspath(
                current_app.instance_path
            )
            used = {r["image_path"] for r in db.execute(
                "SELECT image_path FROM components WHERE image_path IS NOT NULL"
            ).fetchall()}
            img_dir = os.path.join(instance_path, "images")
            deleted = 0
            if os.path.isdir(img_dir):
                for fname in os.listdir(img_dir):
                    fpath = f"images/{fname}"
                    if fpath not in used:
                        os.remove(os.path.join(img_dir, fname))
                        deleted += 1
            flash(_t("msg.images_cleaned", n=deleted), "success")

        # ── Réconciliation EasyEDA (fichiers présents mais pas en base) ─
        elif action == "reconcile_easyeda":
            instance_path = os.path.abspath(
                current_app.instance_path
            )
            pngs_dir = os.path.join(instance_path, "easyeda_pngs")
            updated = 0
            if os.path.isdir(pngs_dir):
                # Groupe les fichiers par référence LCSC
                files = os.listdir(pngs_dir)
                refs = {}
                for f in files:
                    if not f.endswith(".png"): continue
                    # Format attendu : C149504_symbol.png ou C149504_footprint.png
                    if "_symbol." in f:
                        ref = f.split("_symbol.")[0].upper()
                        refs.setdefault(ref, {})["symbol"] = f"easyeda_pngs/{f}"
                    elif "_footprint." in f:
                        ref = f.split("_footprint.")[0].upper()
                        refs.setdefault(ref, {})["footprint"] = f"easyeda_pngs/{f}"

                for ref, paths in refs.items():
                    row = db.execute(
                        "SELECT id, symbol_png, footprint_png FROM components WHERE lcsc_part_number = ?",
                        (ref,)
                    ).fetchone()
                    if not row: continue
                    sym = paths.get("symbol")
                    fp  = paths.get("footprint")
                    # Met à jour seulement les colonnes vides
                    if (sym and not row["symbol_png"]) or (fp and not row["footprint_png"]):
                        ComponentModel.save_easyeda_pngs(
                            row["id"],
                            sym if not row["symbol_png"] else None,
                            fp  if not row["footprint_png"] else None,
                        )
                        updated += 1

            if updated:
                flash(_t("msg.easyeda_reconciled", n=updated), "success")
            else:
                flash(_t("msg.easyeda_ok"), "info")

        # ── Téléchargement EasyEDA en masse ─────────────────────────
        elif action == "easyeda_all":
            from ..services.easyeda import fetch_and_save
            import threading
            # Composants avec ref LCSC mais sans symbol ou footprint
            rows = db.execute(
                """SELECT id, lcsc_part_number FROM components
                   WHERE lcsc_part_number IS NOT NULL AND lcsc_part_number != ''
                     AND (symbol_png IS NULL OR symbol_png = ''
                          OR footprint_png IS NULL OR footprint_png = '')"""
            ).fetchall()
            if not rows:
                flash(_t("msg.easyeda_all_done"), "success")
            else:
                instance_path = os.path.abspath(
                    current_app.instance_path
                )
                app = current_app._get_current_object()

                def _fetch_all_easyeda(items, inst_path, _app):
                    import time
                    with _app.app_context():
                        for comp_id, lcsc_ref in items:
                            try:
                                result = fetch_and_save(lcsc_ref, inst_path)
                                sym = result.get("symbol_png")
                                fp  = result.get("footprint_png")
                                if sym or fp:
                                    ComponentModel.save_easyeda_pngs(comp_id, sym, fp)
                                time.sleep(0.5)
                            except Exception as e:
                                logger.debug("Ignored: %s", e)

                items = [(r["id"], r["lcsc_part_number"]) for r in rows]
                t = threading.Thread(
                    target=_fetch_all_easyeda,
                    args=(items, instance_path, app),
                    daemon=True
                )
                t.start()
                flash(_t("msg.easyeda_launched", n=len(items)), "info")

        # ── Sauvegarde ────────────────────────────────────────────────
        elif action == "backup":
            instance_path = os.path.abspath(
                current_app.instance_path
            )
            tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
            try:
                with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as zf:
                    for root, dirs, files in os.walk(instance_path):
                        for f in files:
                            fp = os.path.join(root, f)
                            zf.write(fp, os.path.relpath(fp, instance_path))
                fname = f"stockelec_backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
                response = send_file(tmp.name, as_attachment=True, download_name=fname,
                                     mimetype="application/zip")
            finally:
                # Nettoyage du fichier temporaire après envoi
                try:
                    os.unlink(tmp.name)
                except Exception as e:
                    logger.debug("Ignored: %s", e)
            return response

        # ── Reset complet BDD (garde settings) ──────────────────────
        elif action == "reset_db":
            confirm = request.form.get("confirm_reset", "").strip()
            if confirm != "RESET":
                flash(_t("msg.reset_wrong"), "danger")
            else:
                # Supprime toutes les données sauf settings
                try:
                    db.execute("DELETE FROM stock_movements")
                    db.execute("DELETE FROM project_components")
                    db.execute("DELETE FROM projects")
                    db.execute("DELETE FROM components")
                    db.execute("DELETE FROM categories")
                    # Remet les séquences autoincrement à zéro
                    db.execute("DELETE FROM sqlite_sequence WHERE name != 'settings'")
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
                # Supprime aussi les images et PNGs EasyEDA
                instance_path = os.path.abspath(
                    current_app.instance_path
                )
                for folder in ("images", "easyeda_pngs", "project_images"):
                    folder_path = os.path.join(instance_path, folder)
                    if os.path.isdir(folder_path):
                        shutil.rmtree(folder_path)
                        os.makedirs(folder_path, exist_ok=True)
                flash(_t("msg.reset_done"), "success")

        # Préserver l'onglet actif via un champ hidden "_section"
        section = request.form.get("_section", "")
        anchor  = f"#{section}" if section else ""
        return redirect(url_for("components.settings") + anchor)

    current, stats, config_plateaux = _settings_get_context(db)
    return ComponentView.render_settings(current, stats, config_plateaux=config_plateaux)
