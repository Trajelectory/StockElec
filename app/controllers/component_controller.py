import io
import csv
import os
import math
import threading

from flask import Blueprint, request, redirect, url_for, flash, jsonify, send_from_directory, render_template

from ..models.component import ComponentModel, ITEMS_PER_PAGE_DEFAULT
from ..models.category import CategoryModel
from ..models.settings import SettingsModel
from ..views.component_view import ComponentView
from ..services import lcsc_scraper

component_bp = Blueprint("components", __name__)


# ------------------------------------------------------------------ #
#  Dashboard / liste paginée
# ------------------------------------------------------------------ #

@component_bp.route("/")
def index():
    search   = request.args.get("search", "").strip()
    category = request.args.get("category", "").strip()
    sort_by  = request.args.get("sort_by", "description")
    order    = request.args.get("order", "asc")
    page     = max(int(request.args.get("page", 1) or 1), 1)
    per_page = int(request.args.get("per_page", ITEMS_PER_PAGE_DEFAULT) or ITEMS_PER_PAGE_DEFAULT)
    if per_page not in (25, 50, 100):
        per_page = ITEMS_PER_PAGE_DEFAULT

    # Filtre "alertes seulement"
    low_only = request.args.get("low_stock") == "1"

    components, total = ComponentModel.get_page(
        search=search or None,
        category=category or None,
        sort_by=sort_by,
        order=order,
        page=page,
        per_page=per_page,
        low_only=low_only,
    )
    total_pages  = max(math.ceil(total / per_page), 1)
    stats        = ComponentModel.get_stats()
    low_count    = ComponentModel.count_low_stock()
    from ..models.category import CategoryModel
    category_groups = CategoryModel.get_grouped_for_stock()

    return ComponentView.render_index(
        components=components,
        category_groups=category_groups,
        stats=stats,
        search=search,
        selected_category=category,
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
def adjust(component_id):
    delta = request.json.get("delta", 0) if request.is_json else request.form.get("delta", 0, type=int)
    delta = int(delta)
    if delta == 0:
        return jsonify({"ok": False, "error": "Delta nul"}), 400

    result = ComponentModel.adjust_quantity(component_id, delta)
    if result["ok"]:
        comp = ComponentModel.get_by_id(component_id)
        return jsonify({
            "ok":       True,
            "new_qty":  result["new_qty"],
            "is_low":   comp.is_low_stock,
            "min_stock": comp.min_stock,
        })
    return jsonify({"ok": False, "error": result["error"]}), 400


# ------------------------------------------------------------------ #
#  Ajout manuel
# ------------------------------------------------------------------ #

@component_bp.route("/add", methods=["GET", "POST"])
def add():
    if request.method == "POST":
        data    = _form_to_dict(request.form)
        comp_id = ComponentModel.create(data)

        lcsc_num = data.get("lcsc_part_number")
        if lcsc_num:
            flash("Récupération des données LCSC en arrière-plan…", "info")
            _enrich_async([(comp_id, lcsc_num)])

        # Mode série : reste sur la page d'ajout avec confirmation
        desc = data.get("description") or data.get("lcsc_part_number") or "Composant"
        return redirect(url_for("components.add", added=desc[:60]))

    from ..models.category import CategoryModel
    return ComponentView.render_add(category_groups=CategoryModel.get_grouped_for_stock())


# ------------------------------------------------------------------ #
#  Import CSV
# ------------------------------------------------------------------ #

@component_bp.route("/import", methods=["GET", "POST"])
def import_csv():
    if request.method == "POST":
        file = request.files.get("csv_file")
        if not file or file.filename == "":
            flash("Aucun fichier sélectionné.", "danger")
            return redirect(url_for("components.import_csv"))
        if not file.filename.lower().endswith(".csv"):
            flash("Veuillez fournir un fichier CSV.", "danger")
            return redirect(url_for("components.import_csv"))

        stream = io.StringIO(file.stream.read().decode("utf-8-sig"), newline=None)
        rows   = list(csv.DictReader(stream))
        result = ComponentModel.import_from_csv_rows(rows)

        inserted      = result["inserted"]
        skipped       = result["skipped"]
        duplicates    = result["duplicates"]
        errors        = result["errors"]
        component_ids = result["component_ids"]

        for e in errors[:5]:
            flash(e, "warning")

        parts = [f"{inserted} composant(s) importé(s)"]
        if skipped:
            parts.append(f"{skipped} ligne(s) ignorée(s)")
        flash(", ".join(parts) + ".", "success" if inserted > 0 else "info")

        if duplicates:
            refs   = ", ".join(duplicates[:10])
            suffix = f" (et {len(duplicates)-10} autres)" if len(duplicates) > 10 else ""
            flash(f"⚠️ Déjà en stock, non importés : {refs}{suffix}", "warning")

        if component_ids:
            flash(f"🔍 Récupération LCSC en cours pour {len(component_ids)} composant(s)…", "info")
            _enrich_async(component_ids)

        return redirect(url_for("components.index"))

    return ComponentView.render_import()


# ------------------------------------------------------------------ #
#  Enrichissement LCSC (AJAX)
# ------------------------------------------------------------------ #

@component_bp.route("/enrich/<int:component_id>", methods=["POST"])
def enrich(component_id):
    comp = ComponentModel.get_by_id(component_id)
    if not comp:
        return jsonify({"ok": False, "error": "Composant introuvable"}), 404
    if not comp.lcsc_part_number:
        return jsonify({"ok": False, "error": "Pas de référence LCSC"}), 400

    info = lcsc_scraper.enrich_component(comp.lcsc_part_number)
    if info:
        ComponentModel.apply_enrichment(component_id, info)
        return jsonify({"ok": True, "fields": list(info.keys())})
    return jsonify({"ok": False, "error": "Aucune donnée retournée par LCSC"})


# ------------------------------------------------------------------ #
#  Prévisualisation LCSC (AJAX — ne crée rien, juste scrape)
# ------------------------------------------------------------------ #

@component_bp.route("/api/lcsc-preview")
def lcsc_preview():
    """
    GET /api/lcsc-preview?ref=C149504
    Retourne les infos LCSC pour pré-remplir le formulaire d'ajout.
    Ne touche pas à la base de données.
    """
    ref = request.args.get("ref", "").strip().upper()
    if not ref:
        return jsonify({"ok": False, "error": "Référence manquante"}), 400

    # Vérifie si déjà en stock
    from ..models.database import get_db
    existing = get_db().execute(
        "SELECT id, description FROM components WHERE lcsc_part_number = ?", (ref,)
    ).fetchone()
    if existing:
        return jsonify({
            "ok": False,
            "duplicate": True,
            "error": f"Ce composant est déjà dans votre stock (#{existing['id']} — {existing['description']})"
        })

    raw = lcsc_scraper.fetch_product(ref)
    if raw is None:
        return jsonify({"ok": False, "error": f"Référence « {ref} » introuvable sur LCSC"}), 404

    info = lcsc_scraper.extract_info(raw)

    # Champs du formulaire
    preview = {
        "ok":                       True,
        "lcsc_part_number":         raw.get("productCode", ref),
        "manufacture_part_number":  raw.get("productModel", ""),
        "manufacturer":             raw.get("brandNameEn", ""),
        "description":              raw.get("productIntroEn") or raw.get("productNameEn") or raw.get("productDescEn", ""),
        "package":                  raw.get("encapStandard", ""),
        "rohs":                     "YES" if raw.get("isEnvironment") else "",
        "category":                 "",
        "image_url":                info.get("image_url", ""),
        "datasheet_url":            info.get("datasheet_url", ""),
        # Prix : on prend le premier palier
        "unit_price":               "",
    }

    # Catégorie full_path
    cat  = info.get("category_name", "")
    pcat = info.get("parent_category_name", "")
    if pcat and cat and pcat != cat:
        preview["category"] = f"{pcat} / {cat}"
    elif cat:
        preview["category"] = cat

    # Prix premier palier
    prices = raw.get("productPriceList") or []
    if prices:
        preview["unit_price"] = prices[0].get("usdPrice") or prices[0].get("productPrice") or ""

    return jsonify(preview)


# ------------------------------------------------------------------ #
#  Étiquettes imprimables
# ------------------------------------------------------------------ #

@component_bp.route("/component/<int:component_id>/label")
def label(component_id):
    """Étiquette pour un seul composant — redirige vers la page multi."""
    return redirect(url_for("components.labels_print", ids=str(component_id)))


@component_bp.route("/labels")
def labels_print():
    """
    Page d'impression multi-étiquettes.
    Paramètres GET :
      ids=1,2,3        → liste d'IDs séparés par virgule
    """
    from ..services.qr_generator import qr_svg_data_url

    raw_ids = request.args.get("ids", "")
    try:
        ids = [int(x.strip()) for x in raw_ids.split(",") if x.strip().isdigit()]
    except ValueError:
        ids = []

    if not ids:
        flash("Aucun composant sélectionné.", "warning")
        return redirect(url_for("components.index"))

    from ..models.settings import SettingsModel as _SM
    _configured = _SM.get("base_url", "").strip().rstrip("/")
    base_url = _configured if _configured else request.host_url.rstrip("/")

    components_data = []
    for cid in ids:
        comp = ComponentModel.get_by_id(cid)
        if comp is None:
            continue
        fiche_url = f"{base_url}{url_for('components.detail', component_id=cid)}"
        qr_data_url = qr_svg_data_url(fiche_url)
        components_data.append({
            "comp":        comp,
            "fiche_url":   fiche_url,
            "qr_data_url": qr_data_url,
        })

    if not components_data:
        flash("Aucun composant trouvé.", "warning")
        return redirect(url_for("components.index"))

    # Charge la config étiquette
    from ..models.settings import SettingsModel
    lbl_config = {k: SettingsModel.get(k, v) for k, v in LABEL_DEFAULTS.items()}

    return render_template(
        "components/labels_print.html",
        components_data=components_data,
        lbl=lbl_config,
    )


# ------------------------------------------------------------------ #
#  Détail
# ------------------------------------------------------------------ #

@component_bp.route("/component/<int:component_id>")
def detail(component_id):
    comp = ComponentModel.get_by_id(component_id)
    if comp is None:
        flash("Composant introuvable.", "danger")
        return redirect(url_for("components.index"))
    from ..models.project import ProjectModel
    projects_using = ProjectModel.get_projects_for_component(component_id)
    return ComponentView.render_detail(comp, projects_using=projects_using)


# ------------------------------------------------------------------ #
#  Édition / Suppression
# ------------------------------------------------------------------ #

@component_bp.route("/component/<int:component_id>/edit", methods=["GET", "POST"])
def edit(component_id):
    comp = ComponentModel.get_by_id(component_id)
    if comp is None:
        flash("Composant introuvable.", "danger")
        return redirect(url_for("components.index"))

    if request.method == "POST":
        data = _form_to_dict(request.form)
        if not data.get("image_path"):
            data["image_path"] = comp.image_path
        if not data.get("datasheet_url"):
            data["datasheet_url"] = comp.datasheet_url
        ComponentModel.update(component_id, data)
        flash("Composant mis à jour.", "success")
        return redirect(url_for("components.detail", component_id=component_id))

    from ..models.category import CategoryModel
    return ComponentView.render_edit(comp, category_groups=CategoryModel.get_grouped_for_stock())


@component_bp.route("/component/<int:component_id>/delete", methods=["POST"])
def delete(component_id):
    ComponentModel.delete(component_id)
    flash("Composant supprimé.", "success")
    return redirect(url_for("components.index"))


# ------------------------------------------------------------------ #
#  Symbole & Footprint EasyEDA (proxy + cache)
# ------------------------------------------------------------------ #

@component_bp.route("/api/easyeda-pngs/<lcsc_ref>")
def easyeda_pngs(lcsc_ref):
    """
    Télécharge et sauvegarde les PNGs EasyEDA (symbole + footprint).
    Met en cache dans la base et dans instance/easyeda_pngs/.
    Paramètre GET ?force=1 pour forcer le rechargement.
    """
    from ..services.easyeda import fetch_and_save
    from ..models.database import get_db
    import os

    lcsc_ref = lcsc_ref.strip().upper()
    if not lcsc_ref:
        return jsonify({"ok": False, "error": "Référence manquante"}), 400

    force = request.args.get("force") == "1"
    db    = get_db()

    # Cherche le composant en base
    row = db.execute(
        "SELECT id, symbol_png, footprint_png FROM components WHERE lcsc_part_number = ?",
        (lcsc_ref,),
    ).fetchone()

    # Cache valide ?
    if not force and row and (row["symbol_png"] or row["footprint_png"]):
        # Vérifie que les fichiers existent encore
        instance_path = os.path.join(component_bp.root_path, "..", "..", "instance")
        sym_ok = row["symbol_png"] and os.path.exists(
            os.path.join(os.path.abspath(instance_path), row["symbol_png"])
        )
        fp_ok  = row["footprint_png"] and os.path.exists(
            os.path.join(os.path.abspath(instance_path), row["footprint_png"])
        )
        if sym_ok or fp_ok:
            return jsonify({
                "ok":           True,
                "symbol_png":   row["symbol_png"],
                "footprint_png": row["footprint_png"],
                "cached":       True,
            })

    # Téléchargement + conversion
    instance_path = os.path.abspath(
        os.path.join(component_bp.root_path, "..", "..", "instance")
    )
    result = fetch_and_save(lcsc_ref, instance_path)
    sym = result.get("symbol_png")
    fp  = result.get("footprint_png")

    if not sym and not fp:
        return jsonify({"ok": False, "error": f"Aucune image disponible pour {lcsc_ref}"}), 404

    # Sauvegarde les chemins en base
    if row:
        ComponentModel.save_easyeda_pngs(row["id"], sym, fp)

    return jsonify({
        "ok":           True,
        "symbol_png":   sym,
        "footprint_png": fp,
        "cached":       False,
    })


@component_bp.route("/easyeda-pngs/<path:filename>")
def easyeda_png_file(filename):
    """Sert les fichiers PNG EasyEDA depuis instance/easyeda_pngs/."""
    import os
    pngs_dir = os.path.abspath(
        os.path.join(component_bp.root_path, "..", "..", "instance", "easyeda_pngs")
    )
    return send_from_directory(pngs_dir, filename)



# ------------------------------------------------------------------ #
#  Configuration des étiquettes
# ------------------------------------------------------------------ #

# Valeurs par défaut de la config étiquette
LABEL_DEFAULTS = {
    "lbl_width_mm":       "60",
    "lbl_height_mm":      "30",
    "lbl_bg_color":       "#ffffff",
    "lbl_text_color":     "#111111",
    "lbl_show_image":     "1",
    "lbl_show_qr":        "1",
    "lbl_show_lcsc":      "1",
    "lbl_show_mfr_part":  "1",
    "lbl_show_mfg":       "1",
    "lbl_show_package":   "1",
    "lbl_show_rohs":      "1",
    "lbl_show_qty":       "1",
    "lbl_show_location":  "1",
    "lbl_show_category":  "1",
    "lbl_show_price":     "1",
    "lbl_desc_size_mm":   "2.1",
    "lbl_ref_size_mm":    "1.7",
    "lbl_badge_size_mm":  "1.4",
    "lbl_color_pkg":      "#ebebeb",
    "lbl_color_rohs":     "#d4f0dd",
    "lbl_color_qty":      "#d0e8ff",
    "lbl_color_loc":      "#fff3cc",
    "lbl_color_cat":      "#efe8ff",
}


@component_bp.route("/label-settings", methods=["GET", "POST"])
def label_settings():
    """Page de configuration visuelle des étiquettes."""
    from ..models.settings import SettingsModel

    if request.method == "POST":
        for key in LABEL_DEFAULTS:
            # Les checkboxes non cochées ne sont pas envoyées → valeur "0"
            if key.startswith("lbl_show_"):
                val = "1" if request.form.get(key) else "0"
            else:
                val = request.form.get(key, LABEL_DEFAULTS[key]).strip()
            SettingsModel.set(key, val)
        flash("Configuration des étiquettes sauvegardée.", "success")
        return redirect(url_for("components.label_settings"))

    # Charge la config courante (avec fallback sur les défauts)
    from ..models.settings import SettingsModel
    config = {k: SettingsModel.get(k, v) for k, v in LABEL_DEFAULTS.items()}

    # Prend un composant du stock pour l'aperçu (préfère un avec image)
    all_comps = ComponentModel.get_all()
    preview_comp = next((c for c in all_comps if c.image_path), None) or (all_comps[0] if all_comps else None)

    return render_template(
        "components/label_settings.html",
        config=config,
        preview_comp=preview_comp,
    )

# ------------------------------------------------------------------ #
#  Page alertes stock bas
# ------------------------------------------------------------------ #

@component_bp.route("/alerts")
def alerts():
    low = ComponentModel.get_low_stock()
    return render_template("components/alerts.html", components=low)



# ------------------------------------------------------------------ #
#  Paramètres
# ------------------------------------------------------------------ #

@component_bp.route("/settings", methods=["GET", "POST"])
def settings():
    from ..models.settings import SettingsModel
    from ..models.database import get_db
    import os, shutil

    if request.method == "POST":
        action = request.form.get("action")

        # ── Paramètres généraux ──────────────────────────────────────
        if action == "save_general":
            for key in ("app_name", "base_url", "default_min_stock"):
                val = request.form.get(key, "").strip()
                SettingsModel.set(key, val)
            flash("Paramètres généraux sauvegardés.", "success")

        # ── Enrichissement en masse ──────────────────────────────────
        elif action == "enrich_all":
            db = get_db()
            rows = db.execute(
                """SELECT id, lcsc_part_number FROM components
                   WHERE lcsc_part_number IS NOT NULL AND lcsc_part_number != ''
                     AND (image_path IS NULL OR image_path = ''
                          OR category IS NULL OR category = '')"""
            ).fetchall()
            ids = [(r["id"], r["lcsc_part_number"]) for r in rows]
            if ids:
                _enrich_async(ids)
                flash(f"🔍 Enrichissement lancé pour {len(ids)} composant(s).", "info")
            else:
                flash("✅ Tous les composants sont déjà enrichis.", "success")

        # ── Nettoyage images orphelines ──────────────────────────────
        elif action == "clean_images":
            instance_path = os.path.abspath(
                os.path.join(component_bp.root_path, "..", "..", "instance")
            )
            db = get_db()
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
            flash(f"🧹 {deleted} image(s) orpheline(s) supprimée(s).", "success")

        # ── Réconciliation EasyEDA (fichiers présents mais pas en base) ─
        elif action == "reconcile_easyeda":
            instance_path = os.path.abspath(
                os.path.join(component_bp.root_path, "..", "..", "instance")
            )
            pngs_dir = os.path.join(instance_path, "easyeda_pngs")
            db = get_db()
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
                flash(f"🔗 {updated} composant(s) mis à jour — chemins EasyEDA réconciliés.", "success")
            else:
                flash("✅ Aucun écart trouvé entre les fichiers et la base.", "info")

        # ── Téléchargement EasyEDA en masse ─────────────────────────
        elif action == "easyeda_all":
            from ..services.easyeda import fetch_and_save
            import threading
            db = get_db()
            # Composants avec ref LCSC mais sans symbol ou footprint
            rows = db.execute(
                """SELECT id, lcsc_part_number FROM components
                   WHERE lcsc_part_number IS NOT NULL AND lcsc_part_number != ''
                     AND (symbol_png IS NULL OR symbol_png = ''
                          OR footprint_png IS NULL OR footprint_png = '')"""
            ).fetchall()
            if not rows:
                flash("✅ Tous les symboles et footprints sont déjà téléchargés.", "success")
            else:
                instance_path = os.path.abspath(
                    os.path.join(component_bp.root_path, "..", "..", "instance")
                )
                def _fetch_all_easyeda(items, inst_path):
                    import time
                    _db_app = component_bp.wsgi_app if hasattr(component_bp, 'wsgi_app') else None
                    for comp_id, lcsc_ref in items:
                        try:
                            result = fetch_and_save(lcsc_ref, inst_path)
                            sym = result.get("symbol_png")
                            fp  = result.get("footprint_png")
                            if sym or fp:
                                ComponentModel.save_easyeda_pngs(comp_id, sym, fp)
                            time.sleep(0.5)
                        except Exception:
                            pass

                items = [(r["id"], r["lcsc_part_number"]) for r in rows]
                t = threading.Thread(
                    target=_fetch_all_easyeda,
                    args=(items, instance_path),
                    daemon=True
                )
                t.start()
                flash(f"🖼️ Téléchargement lancé pour {len(items)} composant(s). Reviens dans quelques minutes.", "info")

        # ── Sauvegarde ────────────────────────────────────────────────
        elif action == "backup":
            import zipfile, tempfile
            from flask import send_file
            instance_path = os.path.abspath(
                os.path.join(component_bp.root_path, "..", "..", "instance")
            )
            tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
            with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(instance_path):
                    for f in files:
                        fp = os.path.join(root, f)
                        zf.write(fp, os.path.relpath(fp, instance_path))
            from datetime import datetime
            fname = f"stockelec_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            return send_file(tmp.name, as_attachment=True, download_name=fname,
                             mimetype="application/zip")

        return redirect(url_for("components.settings"))

    # ── GET : collecte les stats ─────────────────────────────────────
    from ..models.database import get_db
    db = get_db()

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

    # Taille des fichiers
    instance_path = os.path.abspath(
        os.path.join(component_bp.root_path, "..", "..", "instance")
    )
    def dir_size(path):
        total = 0
        if os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                total += sum(os.path.getsize(os.path.join(root, f)) for f in files)
        return total

    db_size  = os.path.getsize(os.path.join(instance_path, "stock.db"))                if os.path.exists(os.path.join(instance_path, "stock.db")) else 0
    img_size = dir_size(os.path.join(instance_path, "images"))
    prj_size = dir_size(os.path.join(instance_path, "project_images"))

    def fmt_size(b):
        if b < 1024: return f"{b} o"
        if b < 1024**2: return f"{b/1024:.1f} Ko"
        return f"{b/1024**2:.1f} Mo"

    # Paramètres courants
    current = {
        "app_name":          SettingsModel.get("app_name", "StockElec"),
        "base_url":          SettingsModel.get("base_url", ""),
        "default_min_stock": SettingsModel.get("default_min_stock", "0"),
    }

    stats = {
        "n_components": n_components,
        "n_projects":   n_projects,
        "n_no_image":   n_no_image,
        "n_no_cat":     n_no_cat,
        "n_to_enrich":  n_to_enrich,
        "n_no_easyeda": n_no_easyeda,
        "db_size":      fmt_size(db_size),
        "img_size":     fmt_size(img_size),
        "prj_size":     fmt_size(prj_size),
        "total_size":   fmt_size(db_size + img_size + prj_size),
    }

    return ComponentView.render_settings(current, stats)


# ------------------------------------------------------------------ #
#  Serving images
# ------------------------------------------------------------------ #

@component_bp.route("/images/<path:filename>")
def component_image(filename):
    images_dir = os.path.abspath(
        os.path.join(component_bp.root_path, "..", "..", "instance", "images")
    )
    return send_from_directory(images_dir, filename)


# ------------------------------------------------------------------ #
#  API JSON
# ------------------------------------------------------------------ #

@component_bp.route("/api/components")
def api_list():
    search = request.args.get("search")
    return jsonify([c.to_dict() for c in ComponentModel.get_all(search=search)])


# ------------------------------------------------------------------ #
#  Helpers
# ------------------------------------------------------------------ #

def _form_to_dict(form):
    return {
        "lcsc_part_number":        form.get("lcsc_part_number"),
        "manufacture_part_number": form.get("manufacture_part_number"),
        "manufacturer":            form.get("manufacturer"),
        "customer_no":             form.get("customer_no"),
        "package":                 form.get("package"),
        "description":             form.get("description"),
        "rohs":                    form.get("rohs"),
        "quantity":                form.get("quantity"),
        "min_stock":               form.get("min_stock"),
        "unit_price":              form.get("unit_price"),
        "ext_price":               form.get("ext_price"),
        "category":                form.get("category"),
        "location":                form.get("location"),
        "notes":                   form.get("notes"),
        "datasheet_url":           form.get("datasheet_url"),
    }


def _enrich_async(component_ids):
    from flask import current_app
    app = current_app._get_current_object()

    def worker():
        with app.app_context():
            lcsc_scraper.enrich_batch(
                component_ids,
                apply_fn=ComponentModel.apply_enrichment,
                delay=0.5,
            )
    threading.Thread(target=worker, daemon=True).start()
