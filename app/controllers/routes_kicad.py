"""
Contrôleur KiCad — génération des fichiers KiCad via JLC2KiCadLib.
Routes :
    POST /kicad/generate          → lance le job
    GET  /kicad/status            → état du job (JSON)
    GET  /kicad/download          → télécharge le ZIP de instance/kicad/
"""

import os
import io
import zipfile
import logging

from flask import Blueprint, jsonify, request, send_file, current_app

from ..models.component import ComponentModel
from ..models.settings import SettingsModel
from ..services import kicad_jlc
from ..services.kicad_jlc import get_component_kicad_status

logger = logging.getLogger(__name__)

kicad_bp = Blueprint("kicad", __name__, url_prefix="/kicad")


def _kicad_dir() -> str:
    """Retourne le chemin absolu vers instance/kicad/."""
    return os.path.join(current_app.instance_path, "kicad")


# ------------------------------------------------------------------ #
#  Vérifier l'installation de JLC2KiCadLib
# ------------------------------------------------------------------ #

@kicad_bp.route("/check")
def check():
    ok, msg = kicad_jlc.check_jlc2kicadlib()
    return jsonify({"ok": ok, "msg": msg})


# ------------------------------------------------------------------ #
#  Lancer le job
# ------------------------------------------------------------------ #

@kicad_bp.route("/generate", methods=["POST"])
def generate():
    if kicad_jlc.is_running():
        return jsonify({"ok": False, "error": "Un job est déjà en cours."})

    ok, msg = kicad_jlc.check_jlc2kicadlib()
    if not ok:
        return jsonify({"ok": False, "error": msg}), 400

    refs = ComponentModel.get_all_lcsc_refs()
    if not refs:
        return jsonify({"ok": False, "error": "Aucune référence LCSC dans le stock."})

    try:
        delay  = float(request.json.get("delay", 2.0)) if request.is_json else 2.0
        prefix = str(request.json.get("prefix", "")).strip() if request.is_json else ""
    except (ValueError, TypeError):
        delay, prefix = 2.0, ""
    delay = max(0.5, min(delay, 10.0))

    kicad_dir = _kicad_dir()
    os.makedirs(kicad_dir, exist_ok=True)

    started = kicad_jlc.start_job(refs, kicad_dir, delay=delay, prefix=prefix)
    if not started:
        return jsonify({"ok": False, "error": "Job déjà en cours."})

    return jsonify({"ok": True, "total": len(refs), "delay": delay, "prefix": prefix})


# ------------------------------------------------------------------ #
#  Générer KiCad pour UN seul composant (depuis la fiche)
# ------------------------------------------------------------------ #

@kicad_bp.route("/generate-one", methods=["POST"])
def generate_one():
    """
    POST /kicad/generate-one
    Body JSON : {"lcsc_ref": "C12345", "prefix": "StockElec_"}
    Lance un job immédiat sur un seul composant.
    """
    if kicad_jlc.is_running():
        return jsonify({"ok": False, "error": "Un job KiCad est déjà en cours — réessaie dans un instant."})

    ok, msg = kicad_jlc.check_jlc2kicadlib()
    if not ok:
        return jsonify({"ok": False, "error": msg}), 400

    data = request.get_json(silent=True) or {}
    lcsc_ref = str(data.get("lcsc_ref", "")).strip().upper()
    prefix   = str(data.get("prefix", "")).strip()

    if not lcsc_ref:
        return jsonify({"ok": False, "error": "Référence LCSC manquante."}), 400

    kicad_dir = _kicad_dir()
    os.makedirs(kicad_dir, exist_ok=True)

    # Lancer avec délai minimal (1 seul composant, pas besoin d'attendre)
    started = kicad_jlc.start_job([lcsc_ref], kicad_dir, delay=0.5, prefix=prefix)
    if not started:
        return jsonify({"ok": False, "error": "Job déjà en cours."})

    logger.info("[KiCad] Génération unitaire lancée : %s", lcsc_ref)
    return jsonify({"ok": True, "lcsc_ref": lcsc_ref, "total": 1})


# ------------------------------------------------------------------ #
#  Statut du job
# ------------------------------------------------------------------ #

@kicad_bp.route("/status")
def status():
    state = kicad_jlc.get_state()
    stats = kicad_jlc.get_library_stats(_kicad_dir())
    return jsonify({
        "running":  state["running"],
        "done":     state["done"],
        "total":    state["total"],
        "current":  state["current"],
        "ref":      state["ref"],
        "log":      state["log"][-100:],  # 100 dernières entrées
        "stats":    stats,
    })


# ------------------------------------------------------------------ #
#  Fusionner les symboles par catégorie
# ------------------------------------------------------------------ #

@kicad_bp.route("/merge", methods=["POST"])
def merge():
    prefix        = SettingsModel.get("kicad_prefix", "").strip()
    data          = request.get_json(silent=True) or {}
    skip_existing = bool(data.get("skip_existing", False))
    kicad_dir     = _kicad_dir()

    # Fusion symboles
    stats = kicad_jlc.merge_symbols(kicad_dir, prefix=prefix, skip_existing=skip_existing)
    if not stats:
        return jsonify({"ok": False, "error": "Aucun fichier .kicad_sym trouvé dans instance/kicad/."})

    # Fusion footprints
    fp_stats = kicad_jlc.merge_footprints(kicad_dir, prefix=prefix, skip_existing=skip_existing)

    total   = sum(n for n in stats.values() if n > 0)
    skipped = sum(1 for n in stats.values() if n == -1)
    added   = sum(n for n in stats.values() if n > 0)  # nouveaux symboles ajoutés
    detail  = [{"category": cat, "n": n} for cat, n in sorted(stats.items()) if n >= 0]

    # Enregistrement automatique symboles + footprints dans KiCad
    reg    = kicad_jlc.register_in_kicad(kicad_dir, prefix=prefix)
    reg_fp = kicad_jlc.register_footprints_in_kicad(kicad_dir, prefix=prefix)
    logger.info("[KiCad] Enregistrement auto sym: %s  fp: %s", reg, reg_fp)

    return jsonify({
        "ok":              True,
        "total_symbols":   total,
        "skipped":         skipped,
        "added":           added,
        "skip_existing":   skip_existing,
        "categories":      detail,
        "fp_stats":        fp_stats,
        "kicad_registered":    reg,
        "kicad_registered_fp": reg_fp,
    })


# ------------------------------------------------------------------ #
#  Enregistrer manuellement les librairies dans KiCad
# ------------------------------------------------------------------ #

@kicad_bp.route("/register", methods=["POST"])
def register():
    """Ajoute symboles ET footprints dans KiCad (sym-lib-table + fp-lib-table)."""
    prefix    = SettingsModel.get("kicad_prefix", "").strip()
    kicad_dir = _kicad_dir()

    # Fusion footprints si pas encore fait (pour avoir les .pretty)
    kicad_jlc.merge_footprints(kicad_dir, prefix=prefix)

    reg    = kicad_jlc.register_in_kicad(kicad_dir, prefix=prefix)
    reg_fp = kicad_jlc.register_footprints_in_kicad(kicad_dir, prefix=prefix)

    ok     = reg.get("ok") or reg_fp.get("ok")
    return jsonify({
        "ok":         ok,
        "symbols":    reg,
        "footprints": reg_fp,
    }), 200 if ok else 500


# ------------------------------------------------------------------ #
#  Télécharger le ZIP
# ------------------------------------------------------------------ #

@kicad_bp.route("/download")
def download():
    kicad_dir = _kicad_dir()
    if not os.path.isdir(kicad_dir):
        return jsonify({"error": "Aucune librairie générée."}), 404

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(kicad_dir):
            for fname in files:
                full = os.path.join(root, fname)
                arcname = os.path.relpath(full, kicad_dir)
                zf.write(full, arcname)
    buf.seek(0)

    return send_file(
        buf,
        as_attachment=True,
        download_name="stockelec_kicad.zip",
        mimetype="application/zip",
    )


# ------------------------------------------------------------------ #
#  Télécharger un fichier KiCad individuel pour un composant
#  GET /kicad/file/<lcsc_ref>/<type>
#  type : symbol | footprint | model3d
# ------------------------------------------------------------------ #

@kicad_bp.route("/file/<lcsc_ref>/<file_type>")
def download_file(lcsc_ref, file_type):
    kicad_dir = _kicad_dir()
    lcsc_ref  = lcsc_ref.strip().upper()

    if file_type not in ("symbol", "footprint", "model3d"):
        return jsonify({"error": "Type invalide"}), 400

    status = get_component_kicad_status(lcsc_ref, kicad_dir)
    filepath = status["paths"].get(file_type)

    if not filepath or not os.path.isfile(filepath):
        return jsonify({"error": f"Fichier {file_type} introuvable pour {lcsc_ref}"}), 404

    filename = os.path.basename(filepath)
    logger.info("[KICAD] Téléchargement %s → %s", file_type, filename)
    return send_file(filepath, as_attachment=True, download_name=filename)
