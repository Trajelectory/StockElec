import os
import uuid
from flask import Blueprint, request, redirect, url_for, flash, jsonify, render_template, current_app

from ..models.project import ProjectModel, STATUS_OPTIONS
from ..models.component import ComponentModel

project_bp = Blueprint("projects", __name__, url_prefix="/projects")


# ------------------------------------------------------------------ #
#  Liste des projets
# ------------------------------------------------------------------ #

@project_bp.route("/")
def index():
    projects = ProjectModel.get_all()
    return render_template("projects/index.html", projects=projects)


# ------------------------------------------------------------------ #
#  Création
# ------------------------------------------------------------------ #

@project_bp.route("/new", methods=["GET", "POST"])
def new():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Le nom du projet est obligatoire.", "danger")
            return render_template("projects/form.html", project=None, status_options=STATUS_OPTIONS)
        image_path = _save_project_image(request.files.get("image"))
        project_id = ProjectModel.create({
            "name":        name,
            "description": request.form.get("description"),
            "status":      request.form.get("status", "en cours"),
            "image_path":  image_path,
        })
        flash(f"Projet « {name} » créé.", "success")
        return redirect(url_for("projects.detail", project_id=project_id))
    return render_template("projects/form.html", project=None, status_options=STATUS_OPTIONS)


# ------------------------------------------------------------------ #
#  Détail
# ------------------------------------------------------------------ #

@project_bp.route("/<int:project_id>")
def detail(project_id):
    project    = ProjectModel.get_by_id(project_id)
    if not project:
        flash("Projet introuvable.", "danger")
        return redirect(url_for("projects.index"))
    components = ProjectModel.get_components(project_id)
    # Tous les composants du stock pour le sélecteur d'ajout
    all_components = ComponentModel.get_all()
    return render_template(
        "projects/detail.html",
        project=project,
        components=components,
        all_components=all_components,
    )


# ------------------------------------------------------------------ #
#  Édition
# ------------------------------------------------------------------ #

@project_bp.route("/<int:project_id>/edit", methods=["GET", "POST"])
def edit(project_id):
    project = ProjectModel.get_by_id(project_id)
    if not project:
        flash("Projet introuvable.", "danger")
        return redirect(url_for("projects.index"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Le nom est obligatoire.", "danger")
            return render_template("projects/form.html", project=project, status_options=STATUS_OPTIONS)
        # Image : nouvelle upload ou conservation de l'existante
        new_image = _save_project_image(request.files.get("image"))
        image_path = new_image if new_image else project.image_path
        # Option suppression
        if request.form.get("delete_image") == "1":
            _delete_project_image(project.image_path)
            image_path = None
        ProjectModel.update(project_id, {
            "name":        name,
            "description": request.form.get("description"),
            "status":      request.form.get("status", "en cours"),
            "image_path":  image_path,
        })
        flash("Projet mis à jour.", "success")
        return redirect(url_for("projects.detail", project_id=project_id))
    return render_template("projects/form.html", project=project, status_options=STATUS_OPTIONS)


# ------------------------------------------------------------------ #
#  Suppression
# ------------------------------------------------------------------ #

@project_bp.route("/<int:project_id>/delete", methods=["POST"])
def delete(project_id):
    project = ProjectModel.get_by_id(project_id)
    if project and project.image_path:
        _delete_project_image(project.image_path)
    ProjectModel.delete(project_id)
    flash("Projet supprimé.", "success")
    return redirect(url_for("projects.index"))


@project_bp.route("/project-images/<path:filename>")
def project_image(filename):
    from flask import send_from_directory
    images_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "instance", "project_images")
    )
    return send_from_directory(images_dir, filename)


# ------------------------------------------------------------------ #
#  Gestion des composants du projet
# ------------------------------------------------------------------ #

@project_bp.route("/<int:project_id>/components/add", methods=["POST"])
def add_component(project_id):
    project = ProjectModel.get_by_id(project_id)
    if not project:
        return jsonify({"ok": False, "error": "Projet introuvable"}), 404

    component_id = request.form.get("component_id", type=int)
    quantity     = request.form.get("quantity", 1, type=int)
    notes        = request.form.get("notes", "").strip() or None

    if not component_id or quantity < 1:
        flash("Composant ou quantité invalide.", "danger")
        return redirect(url_for("projects.detail", project_id=project_id))

    ProjectModel.add_component(project_id, component_id, quantity, notes)
    flash("Composant ajouté au projet.", "success")
    return redirect(url_for("projects.detail", project_id=project_id))


@project_bp.route("/<int:project_id>/components/<int:component_id>/remove", methods=["POST"])
def remove_component(project_id, component_id):
    ProjectModel.remove_component(project_id, component_id)
    flash("Composant retiré du projet.", "success")
    return redirect(url_for("projects.detail", project_id=project_id))


@project_bp.route("/<int:project_id>/components/<int:component_id>/use", methods=["POST"])
def use_component(project_id, component_id):
    """Débite le stock et enregistre un mouvement 'project_use'."""
    quantity = request.form.get("quantity", 1, type=int)
    result   = ComponentModel.adjust_quantity(component_id, -quantity)
    if result["ok"]:
        return jsonify({"ok": True, "new_qty": result["new_qty"]})
    return jsonify({"ok": False, "error": result["error"]}), 400


@project_bp.route("/<int:project_id>/components/<int:component_id>/return", methods=["POST"])
def return_component(project_id, component_id):
    """Recrédite le stock et enregistre un mouvement 'project_return'."""
    quantity = request.form.get("quantity", 1, type=int)
    result   = ComponentModel.adjust_quantity(component_id, +quantity)
    if result["ok"]:
        return jsonify({"ok": True, "new_qty": result["new_qty"]})
    return jsonify({"ok": False, "error": result["error"]}), 400


# ------------------------------------------------------------------ #
#  Import BOM KiCad
# ------------------------------------------------------------------ #

@project_bp.route("/<int:project_id>/import-bom", methods=["GET", "POST"])
def import_bom(project_id):
    project = ProjectModel.get_by_id(project_id)
    if not project:
        flash("Projet introuvable.", "danger")
        return redirect(url_for("projects.index"))

    if request.method == "POST":
        file = request.files.get("bom_file")
        if not file or file.filename == "":
            flash("Aucun fichier sélectionné.", "danger")
            return redirect(url_for("projects.import_bom", project_id=project_id))

        if not file.filename.lower().endswith(".csv"):
            flash("Veuillez fournir un fichier CSV.", "danger")
            return redirect(url_for("projects.import_bom", project_id=project_id))

        import io, csv as csvmod
        # KiCad peut utiliser , ou ; comme séparateur
        raw = file.stream.read().decode("utf-8-sig")
        # Détecte le séparateur
        sep = ";" if raw.count(";") > raw.count(",") else ","
        reader = csvmod.DictReader(io.StringIO(raw, newline=None), delimiter=sep)
        rows = list(reader)

        if not rows:
            flash("Le fichier est vide ou illisible.", "danger")
            return redirect(url_for("projects.import_bom", project_id=project_id))

        report = _analyse_bom(rows, project_id)
        if report is None:
            flash(
                "Impossible de trouver une colonne LCSC ou Mouser dans ce fichier. "
                "Colonnes attendues : 'LCSC', 'Mouser', 'LCSC Part Number', etc."
                "Colonnes détectées : " + ", ".join(rows[0].keys()),
                "danger",
            )
            return redirect(url_for("projects.import_bom", project_id=project_id))

        return render_template(
            "projects/bom_report.html",
            project=project,
            report=report,
            filename=file.filename,
        )

    return render_template("projects/import_bom.html", project=project)


@project_bp.route("/<int:project_id>/import-bom/create-missing", methods=["POST"])
def create_missing(project_id):
    """Crée un composant manquant dans le stock et lance l'enrichissement LCSC."""
    from ..models.component import ComponentModel as CM
    from ..models.database import get_db
    from ..services import lcsc_scraper
    import threading

    lcsc    = request.form.get("lcsc", "").strip().upper()
    desc    = request.form.get("description", lcsc)
    qty     = request.form.get("quantity", 0, type=int)

    if not lcsc:
        flash("Référence LCSC manquante.", "danger")
        return redirect(url_for("projects.detail", project_id=project_id))

    db = get_db()
    # Vérifie si déjà existant
    existing = db.execute(
        "SELECT id FROM components WHERE lcsc_part_number=?", (lcsc,)
    ).fetchone()

    if existing:
        comp_id = existing["id"]
        flash(f"⚠️ {lcsc} existe déjà dans le stock.", "info")
    else:
        comp_id = CM.create({
            "lcsc_part_number": lcsc,
            "description":      "",
            "description_long": desc or "",
            "quantity":         qty,
            "min_stock":        0,
        })
        flash(f"✅ {lcsc} créé dans le stock — enrichissement en cours…", "success")
        # Enrichissement en arrière-plan
        def _enrich():
            try:
                info = lcsc_scraper.enrich_component(lcsc)
                if info:
                    CM.apply_enrichment(comp_id, info)
            except Exception:
                pass
        threading.Thread(target=_enrich, daemon=True).start()

    # Ajoute au projet
    try:
        ProjectModel.add_component(project_id, comp_id, max(1, qty))
    except Exception:
        pass

    return redirect(url_for("projects.detail", project_id=project_id))


@project_bp.route("/<int:project_id>/import-bom/apply", methods=["POST"])
def apply_bom(project_id):
    from ..models.component import ComponentModel as CM
    from ..models.database import get_db
    from ..services import lcsc_scraper
    import threading

    project = ProjectModel.get_by_id(project_id)
    if not project:
        flash("Projet introuvable.", "danger")
        return redirect(url_for("projects.index"))

    db = get_db()
    added = 0

    # ── 1. Composants existants cochés ──────────────────────────────
    component_ids = request.form.getlist("component_id")
    quantities    = request.form.getlist("quantity")
    for comp_id, qty in zip(component_ids, quantities):
        try:
            ProjectModel.add_component(project_id, int(comp_id), int(qty))
            added += 1
        except Exception:
            pass

    # ── 2. Composants manquants cochés → créer + enrichir ───────────
    missing_ids = request.form.getlist("missing_id")
    to_enrich = []
    to_enrich_mouser  = []
    to_enrich_digikey = []

    for idx in missing_ids:
        qty         = request.form.get(f"missing_qty_{idx}",     0,   type=int)
        desc        = request.form.get(f"missing_desc_{idx}",    "")
        lcsc        = request.form.get(f"missing_lcsc_{idx}",    "").strip().upper()
        mouser_ref  = request.form.get(f"missing_mouser_{idx}",  "").strip()
        digikey_ref = request.form.get(f"missing_digikey_{idx}", "").strip()

        if not lcsc and not mouser_ref and not digikey_ref:
            continue

        # Cherche si déjà en stock
        existing = None
        if lcsc:
            existing = db.execute(
                "SELECT id FROM components WHERE lcsc_part_number=?", (lcsc,)
            ).fetchone()
        if not existing and mouser_ref:
            existing = db.execute(
                "SELECT id FROM components WHERE mouser_part_number=?", (mouser_ref,)
            ).fetchone()
        if not existing and digikey_ref:
            existing = db.execute(
                "SELECT id FROM components WHERE digikey_part_number=?", (digikey_ref,)
            ).fetchone()

        if existing:
            comp_id = existing["id"]
            # Complète les refs manquantes
            updates = {}
            row = db.execute(
                "SELECT lcsc_part_number, mouser_part_number, digikey_part_number FROM components WHERE id=?",
                (comp_id,)
            ).fetchone()
            if lcsc       and not row["lcsc_part_number"]:    updates["lcsc_part_number"]    = lcsc
            if mouser_ref and not row["mouser_part_number"]:  updates["mouser_part_number"]  = mouser_ref
            if digikey_ref and not row["digikey_part_number"]: updates["digikey_part_number"] = digikey_ref
            if updates:
                fields = ", ".join(f"{k} = ?" for k in updates)
                db.execute(f"UPDATE components SET {fields} WHERE id = ?",
                           list(updates.values()) + [comp_id])
                db.commit()
        else:
            comp_data = {
                "description":      "",
                "description_long": desc or "",
                "quantity":         0,
                "min_stock":        0,
            }
            if lcsc:        comp_data["lcsc_part_number"]    = lcsc
            if mouser_ref:  comp_data["mouser_part_number"]  = mouser_ref
            if digikey_ref: comp_data["digikey_part_number"] = digikey_ref
            comp_id = CM.create(comp_data)
            if lcsc:
                to_enrich.append((comp_id, lcsc))
            elif mouser_ref:
                to_enrich_mouser.append((comp_id, mouser_ref))
            elif digikey_ref:
                to_enrich_digikey.append((comp_id, digikey_ref))

        try:
            ProjectModel.add_component(project_id, comp_id, max(1, qty))
            added += 1
        except Exception:
            pass

    # Enrichissement en arrière-plan — LCSC
    if to_enrich:
        from flask import current_app as _ca2
        _app2 = _ca2._get_current_object()
        def _enrich_missing():
            with _app2.app_context():
                for cid, lcsc_ref in to_enrich:
                    try:
                        info = lcsc_scraper.enrich_component(lcsc_ref)
                        if info:
                            CM.apply_enrichment(cid, info)
                    except Exception:
                        pass
        threading.Thread(target=_enrich_missing, daemon=True).start()
        flash(f"🔍 Enrichissement LCSC en cours pour {len(to_enrich)} nouveau(x) composant(s)…", "info")

    # Enrichissement en arrière-plan — Mouser
    if to_enrich_mouser:
        from flask import current_app as _app
        _app_obj = _app._get_current_object()
        def _enrich_mouser():
            with _app_obj.app_context():
                from .component_controller import _enrich_async_source
                for cid, mref in to_enrich_mouser:
                    _enrich_async_source(cid, mref, "mouser")
        threading.Thread(target=_enrich_mouser, daemon=True).start()

    # Enrichissement en arrière-plan — DigiKey
    if to_enrich_digikey:
        from flask import current_app as _app
        _app_obj = _app._get_current_object()
        def _enrich_digikey():
            with _app_obj.app_context():
                from .component_controller import _enrich_async_source
                for cid, dref in to_enrich_digikey:
                    _enrich_async_source(cid, dref, "digikey")
        threading.Thread(target=_enrich_digikey, daemon=True).start()

    flash(f"✅ {added} composant(s) ajouté(s) au projet.", "success")
    return redirect(url_for("projects.detail", project_id=project_id))


# ------------------------------------------------------------------ #
#  Analyse BOM (logique métier)
# ------------------------------------------------------------------ #

# Noms de colonnes LCSC reconnus (insensible à la casse)
# Couvre : export commande LCSC, export panier LCSC, BOM KiCad JLCPCB, etc.
_LCSC_COLS = [
    # Format export commande LCSC classique
    "lcsc part number",
    # Format export panier LCSC (export_cart_*.csv)
    "lcsc#",
    # Variantes KiCad/JLCPCB
    "lcsc part #", "lcsc part", "lcsc",
    "lcsc_part_number",
    # Autres variantes
    "supplier part number", "supplier part #",
    "lcsc number", "lcsc no",
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
    "mpn",  # export panier LCSC : MPN contient la référence fabricant
]


# Noms de colonnes DigiKey reconnus
_DIGIKEY_COLS = [
    "digikey", "digi-key", "digikey part number", "digikey part #",
    "digikey#", "digikey_part_number", "dk part number", "dk#",
]
_MOUSER_COLS = [
    "mouser", "mouser part number", "mouser part #",
    "mouser#", "mouser_part_number", "mouser no", "mouser number",
]


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
    from ..models.database import get_db
    from ..models.component import ComponentModel as CM

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
        lcsc_ref    = row.get(lcsc_col,    "").strip().upper() if lcsc_col    else ""
        mouser_ref  = row.get(mouser_col,  "").strip()         if mouser_col  else ""
        digikey_ref = row.get(digikey_col, "").strip()         if digikey_col else ""
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
            # Met à jour les refs manquantes sur le composant existant
            updates = {}
            if has_mouser  and not db.execute("SELECT mouser_part_number  FROM components WHERE id=?", (comp_id,)).fetchone()["mouser_part_number"]:
                updates["mouser_part_number"]  = mouser_ref
            if has_digikey and not db.execute("SELECT digikey_part_number FROM components WHERE id=?", (comp_id,)).fetchone()["digikey_part_number"]:
                updates["digikey_part_number"] = digikey_ref
            if has_lcsc    and not db.execute("SELECT lcsc_part_number    FROM components WHERE id=?", (comp_id,)).fetchone()["lcsc_part_number"]:
                updates["lcsc_part_number"]    = lcsc_ref
            if updates:
                fields = ", ".join(f"{k} = ?" for k in updates)
                db.execute(f"UPDATE components SET {fields} WHERE id = ?",
                           list(updates.values()) + [comp_id])
                db.commit()

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
            comp_id = CM.create(comp_data)

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
        import threading
        from ..services import lcsc_scraper

        def _enrich_lcsc():
            with _app.app_context():
                for cid, lcsc_ref in new_ids:
                    try:
                        info = lcsc_scraper.enrich_component(lcsc_ref)
                        if info:
                            CM.apply_enrichment(cid, info)
                    except Exception:
                        pass

        threading.Thread(target=_enrich_lcsc, daemon=True).start()

    if new_mouser_ids:
        import threading
        from ..services import mouser_scraper
        from ..models.settings import SettingsModel

        def _enrich_mouser():
            with _app.app_context():
                api_key = SettingsModel.get("mouser_api_key", "")
                if not api_key:
                    return
                for cid, mref in new_mouser_ids:
                    try:
                        info = mouser_scraper.enrich_component(mref, api_key)
                        if info:
                            CM.apply_enrichment(cid, info)
                    except Exception:
                        pass

        threading.Thread(target=_enrich_mouser, daemon=True).start()

    if new_digikey_ids:
        import threading
        from ..services import digikey_scraper
        from ..models.settings import SettingsModel

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
                            CM.apply_enrichment(cid, info)
                    except Exception:
                        pass

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


# ------------------------------------------------------------------ #
#  Helpers image projet
# ------------------------------------------------------------------ #

_ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

def _save_project_image(file_storage) -> str | None:
    """Sauvegarde l'image uploadée, retourne le chemin relatif ou None."""
    if not file_storage or file_storage.filename == "":
        return None
    ext = os.path.splitext(file_storage.filename)[-1].lower()
    if ext not in _ALLOWED_EXTS:
        return None
    images_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "instance", "project_images")
    )
    os.makedirs(images_dir, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ext}"
    file_storage.save(os.path.join(images_dir, filename))
    return filename


def _delete_project_image(image_path: str | None):
    """Supprime le fichier image si il existe."""
    if not image_path:
        return
    images_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "instance", "project_images")
    )
    filepath = os.path.join(images_dir, image_path)
    if os.path.exists(filepath):
        os.remove(filepath)
