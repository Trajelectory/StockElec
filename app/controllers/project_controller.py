import os
import uuid
from flask import Blueprint, request, redirect, url_for, flash, jsonify, render_template, current_app
from werkzeug.utils import secure_filename

from ..models.project import ProjectModel, STATUS_OPTIONS
from ..models.component import ComponentModel
from ..models.movement import MovementModel, TYPE_PROJECT_USE, TYPE_PROJECT_RETURN

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
    result   = ComponentModel.adjust_quantity(
        component_id, -quantity,
        movement_type=TYPE_PROJECT_USE,
        project_id=project_id,
        note=f"Utilisé pour le projet #{project_id}",
    )
    if result["ok"]:
        return jsonify({"ok": True, "new_qty": result["new_qty"]})
    return jsonify({"ok": False, "error": result["error"]}), 400


@project_bp.route("/<int:project_id>/components/<int:component_id>/return", methods=["POST"])
def return_component(project_id, component_id):
    """Recrédite le stock et enregistre un mouvement 'project_return'."""
    quantity = request.form.get("quantity", 1, type=int)
    result   = ComponentModel.adjust_quantity(
        component_id, +quantity,
        movement_type=TYPE_PROJECT_RETURN,
        project_id=project_id,
        note=f"Retour depuis le projet #{project_id}",
    )
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
                "Impossible de trouver une colonne LCSC dans ce fichier. "
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


@project_bp.route("/<int:project_id>/import-bom/apply", methods=["POST"])
def apply_bom(project_id):
    """
    Reçoit la liste des composants validés depuis le rapport BOM
    et les ajoute au projet (uniquement ceux qui sont en stock).
    """
    project = ProjectModel.get_by_id(project_id)
    if not project:
        flash("Projet introuvable.", "danger")
        return redirect(url_for("projects.index"))

    added = 0
    # Le formulaire envoie des paires component_id[N] / quantity[N]
    component_ids = request.form.getlist("component_id")
    quantities    = request.form.getlist("quantity")

    for comp_id, qty in zip(component_ids, quantities):
        try:
            ProjectModel.add_component(project_id, int(comp_id), int(qty))
            added += 1
        except Exception:
            pass

    flash(f"{added} composant(s) ajouté(s) au projet depuis la BOM.", "success")
    return redirect(url_for("projects.detail", project_id=project_id))


# ------------------------------------------------------------------ #
#  Analyse BOM (logique métier)
# ------------------------------------------------------------------ #

# Noms de colonnes LCSC reconnus (insensible à la casse)
_LCSC_COLS = [
    "lcsc part number", "lcsc part #", "lcsc part", "lcsc",
    "lcsc_part_number", "lcsc#", "supplier part number",
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

    Retourne un dict avec :
      lcsc_col, qty_col, ref_col, val_col  — noms de colonnes détectés
      ok       — liste de composants en stock avec quantité suffisante
      low      — liste en stock mais quantité insuffisante
      missing  — liste absente du stock
      no_lcsc  — lignes sans référence LCSC
    """
    from ..models.database import get_db

    headers = list(rows[0].keys())
    lcsc_col = _find_col(headers, _LCSC_COLS)
    if not lcsc_col:
        return None  # Impossible d'analyser sans colonne LCSC

    qty_col  = _find_col(headers, _QTY_COLS)
    ref_col  = _find_col(headers, _REF_COLS)
    val_col  = _find_col(headers, _VAL_COLS)

    db = get_db()

    ok      = []   # en stock, quantité suffisante
    low     = []   # en stock, mais pas assez
    missing = []   # absent du stock
    no_lcsc = []   # ligne sans ref LCSC

    # Récupère les composants déjà dans le projet (pour pré-cocher)
    already = {
        pc.component_id
        for pc in ProjectModel.get_components(project_id)
    }

    for row in rows:
        lcsc_ref = row.get(lcsc_col, "").strip().upper()
        qty_raw  = row.get(qty_col, "1").strip() if qty_col else "1"
        ref      = row.get(ref_col, "").strip()  if ref_col  else ""
        val      = row.get(val_col, "").strip()  if val_col  else ""

        # Quantité : si format "R1, R2, R3" dans le champ qty → compter les virgules
        try:
            bom_qty = int(qty_raw)
        except ValueError:
            # KiCad peut mettre les refs dans la colonne qty style "R1, R2"
            bom_qty = max(1, qty_raw.count(",") + 1) if qty_raw else 1

        if not lcsc_ref or lcsc_ref in ("", "~", "NA", "N/A", "-"):
            no_lcsc.append({
                "ref": ref, "value": val, "qty": bom_qty,
                "lcsc": lcsc_ref or "—",
            })
            continue

        # Cherche dans le stock
        stock_row = db.execute(
            "SELECT id, description, quantity, unit_price, image_path "
            "FROM components WHERE lcsc_part_number = ?",
            (lcsc_ref,),
        ).fetchone()

        entry = {
            "lcsc":       lcsc_ref,
            "ref":        ref,
            "value":      val,
            "bom_qty":    bom_qty,
            "already":    False,
        }

        if stock_row:
            entry.update({
                "component_id":  stock_row["id"],
                "description":   stock_row["description"],
                "stock_qty":     stock_row["quantity"],
                "unit_price":    stock_row["unit_price"],
                "image_path":    stock_row["image_path"],
                "already":       stock_row["id"] in already,
            })
            if stock_row["quantity"] >= bom_qty:
                ok.append(entry)
            else:
                low.append(entry)
        else:
            entry.update({
                "component_id": None,
                "description":  val or lcsc_ref,
                "stock_qty":    0,
                "unit_price":   None,
                "image_path":   None,
            })
            missing.append(entry)

    return {
        "lcsc_col": lcsc_col,
        "qty_col":  qty_col,
        "ref_col":  ref_col,
        "val_col":  val_col,
        "ok":       ok,
        "low":      low,
        "missing":  missing,
        "no_lcsc":  no_lcsc,
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
