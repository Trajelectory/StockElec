from .database import get_db

ITEMS_PER_PAGE_DEFAULT = 25


class Component:
    """Représente un composant électronique dans le stock."""

    def __init__(self, row):
        d = dict(row)
        self.id                      = d["id"]
        self.lcsc_part_number        = d["lcsc_part_number"]
        self.manufacture_part_number = d["manufacture_part_number"]
        self.manufacturer            = d["manufacturer"]
        self.customer_no             = d["customer_no"]
        self.package                 = d["package"]
        self.description             = d["description"]
        self.rohs                    = d["rohs"]
        self.quantity                = d["quantity"]
        self.min_stock               = d.get("min_stock", 0)
        self.unit_price              = d["unit_price"]
        self.ext_price               = d["ext_price"]
        self.category                = d["category"]
        self.category_id             = d.get("category_id")
        self.location                = d["location"]
        self.notes                   = d["notes"]
        self.image_path              = d.get("image_path")
        self.datasheet_url           = d.get("datasheet_url")
        self.symbol_png              = d.get("symbol_png")
        self.footprint_png           = d.get("footprint_png")
        self.attributes              = d.get("attributes")
        self.description_long        = d.get("description_long")
        self.mouser_part_number      = d.get("mouser_part_number")
        self.digikey_part_number     = d.get("digikey_part_number")
        self.product_url             = d.get("product_url")
        self.source_url              = d.get("source_url")
        self.created_at              = d.get("created_at")
        self.updated_at              = d.get("updated_at")

    @property
    def is_low_stock(self):
        """True si la quantité est sous le seuil d'alerte."""
        return self.min_stock > 0 and self.quantity <= self.min_stock

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items()}


class ComponentModel:
    """Couche d'accès aux données pour les composants."""

    # ------------------------------------------------------------------ #
    #  READ — avec pagination
    # ------------------------------------------------------------------ #

    @staticmethod
    def get_page(search=None, category=None, sort_by="description", order="asc", location=None,
                 page=1, per_page=ITEMS_PER_PAGE_DEFAULT, low_only=False):
        """
        Retourne (components, total_count) pour la page demandée.
        """
        db = get_db()
        where, params = _build_where(search, category, low_only=low_only, location=location)

        # Compte total
        total = db.execute(
            f"SELECT COUNT(*) FROM components {where}", params
        ).fetchone()[0]

        # Tri sécurisé
        sort_by = sort_by if sort_by in _ALLOWED_SORTS else "description"
        direction = "DESC" if order == "desc" else "ASC"

        offset = (max(page, 1) - 1) * per_page
        rows = db.execute(
            f"SELECT * FROM components {where} ORDER BY {sort_by} {direction} LIMIT ? OFFSET ?",
            params + [per_page, offset],
        ).fetchall()

        return [Component(r) for r in rows], total

    @staticmethod
    def get_all(search=None, category=None, sort_by="description", order="asc"):
        """Retourne tous les composants sans pagination (pour l'API JSON)."""
        db = get_db()
        where, params = _build_where(search, category)
        sort_by = sort_by if sort_by in _ALLOWED_SORTS else "description"
        direction = "DESC" if order == "desc" else "ASC"
        rows = db.execute(
            f"SELECT * FROM components {where} ORDER BY {sort_by} {direction}",
            params,
        ).fetchall()
        return [Component(r) for r in rows]

    @staticmethod
    def get_by_id(component_id):
        db = get_db()
        row = db.execute(
            "SELECT * FROM components WHERE id = ?", (component_id,)
        ).fetchone()
        return Component(row) if row else None

    @staticmethod
    def get_stats():
        db = get_db()
        row = db.execute(
            """
            SELECT
                COUNT(*)                     AS total_references,
                COALESCE(SUM(quantity), 0)   AS total_quantity,
                COALESCE(SUM(ext_price), 0)  AS total_value,
                COUNT(DISTINCT manufacturer) AS total_manufacturers
            FROM components
            """
        ).fetchone()
        return dict(row) if row else {}

    # ------------------------------------------------------------------ #
    #  WRITE
    # ------------------------------------------------------------------ #

    @staticmethod
    def create(data):
        db = get_db()
        qty = int(data.get("quantity") or 0)
        try:
            cursor = db.execute(
                """
                INSERT INTO components (
                    lcsc_part_number, mouser_part_number, digikey_part_number,
                    manufacture_part_number, manufacturer,
                    customer_no, package, description, description_long, rohs,
                    quantity, min_stock, unit_price, ext_price,
                    category, category_id, location, notes,
                    image_path, datasheet_url, product_url, source_url, attributes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _to_none(data.get("lcsc_part_number")),
                    _to_none(data.get("mouser_part_number")),
                    _to_none(data.get("digikey_part_number")),
                    _to_none(data.get("manufacture_part_number")),
                    data.get("manufacturer"),
                    data.get("customer_no"),
                    data.get("package"),
                    data.get("description"),
                    data.get("description_long"),
                    data.get("rohs"),
                    qty,
                    int(data.get("min_stock") or 0),
                    _to_float(data.get("unit_price")),
                    _to_float(data.get("ext_price")),
                    data.get("category"),
                    data.get("category_id"),
                    data.get("location"),
                    data.get("notes"),
                    data.get("image_path"),
                    data.get("datasheet_url"),
                    data.get("product_url"),
                    _to_none(data.get("source_url")),
                    _to_none(data.get("attributes")),
                ),
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        return cursor.lastrowid

    @staticmethod
    def update(component_id, data):
        db = get_db()
        try:
            db.execute(
                """
                UPDATE components SET
                    lcsc_part_number        = ?,
                    mouser_part_number      = ?,
                    digikey_part_number     = ?,
                    manufacture_part_number = ?,
                    manufacturer            = ?,
                    customer_no             = ?,
                    package                 = ?,
                    description             = ?,
                    description_long        = ?,
                    rohs                    = ?,
                    quantity                = ?,
                    min_stock               = ?,
                    unit_price              = ?,
                    ext_price               = ?,
                    category                = ?,
                    category_id             = ?,
                    location                = ?,
                    notes                   = ?,
                    image_path              = ?,
                    datasheet_url           = ?,
                    product_url             = ?,
                    source_url              = ?,
                    attributes              = ?
                WHERE id = ?
                """,
                (
                    _to_none(data.get("lcsc_part_number")),
                    _to_none(data.get("mouser_part_number")),
                    _to_none(data.get("digikey_part_number")),
                    _to_none(data.get("manufacture_part_number")),
                    data.get("manufacturer"),
                    data.get("customer_no"),
                    data.get("package"),
                    data.get("description"),
                    data.get("description_long"),
                    data.get("rohs"),
                    int(data.get("quantity") or 0),
                    int(data.get("min_stock") or 0),
                    _to_float(data.get("unit_price")),
                    _to_float(data.get("ext_price")),
                    data.get("category"),
                    data.get("category_id"),
                    data.get("location"),
                    data.get("notes"),
                    data.get("image_path"),
                    data.get("datasheet_url"),
                    data.get("product_url"),
                    _to_none(data.get("source_url")),
                    _to_none(data.get("attributes")),
                    component_id,
                ),
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def apply_enrichment(component_id: int, enrichment: dict, force_attributes: bool = False):
        """
        Applique les données du scraper LCSC/Mouser/DigiKey.
        Ne remplace que les champs encore vides, sauf si force_attributes=True
        (ré-enrichissement explicite : attributes et image_path sont toujours mis à jour).
        """
        if not enrichment:
            return

        db = get_db()
        row = db.execute(
            "SELECT * FROM components WHERE id = ?", (component_id,)
        ).fetchone()
        if not row:
            return

        # --- Catégorie ---
        cat_name    = enrichment.get("category_name")
        cat_id      = enrichment.get("category_id")
        parent_name = enrichment.get("parent_category_name")
        parent_id   = enrichment.get("parent_category_id")

        # Calcul du full_path pour la colonne category du composant
        full_path = None
        if parent_name and cat_name and parent_name != cat_name:
            full_path = f"{parent_name} / {cat_name}"
        elif cat_name:
            full_path = cat_name

        # Upsert dans la table categories
        if cat_id and cat_name:
            from .category import CategoryModel
            # Insertion du breadcrumb complet ex: [Passives(30) → Resistors(501)]
            breadcrumb = enrichment.get("breadcrumb") or []
            prev_id = None
            for crumb in breadcrumb:
                if crumb.get("id") and crumb.get("name"):
                    CategoryModel.upsert(
                        category_id=crumb["id"],
                        name=crumb["name"],
                        parent_id=prev_id,
                        parent_name=None,
                    )
                    prev_id = crumb["id"]
            # Catégorie feuille (ex: "Chip Resistor - Surface Mount")
            CategoryModel.upsert(cat_id, cat_name, parent_id, parent_name)

        # Mise à jour des champs vides du composant
        fields, values = [], []
        d = dict(row)

        def _maybe(col, new_val):
            if not new_val:
                return
            if col not in d:
                return
            if not d[col]:
                fields.append(f"{col} = ?")
                values.append(new_val)

        # description et description_long : toujours écrasés par l'API distributeur
        # (la valeur KiCad "0R 0402" est moins précise que "RES 100Ω ±1% 62.5mW 0402")
        for col in ("description", "description_long"):
            new_val = enrichment.get(col)
            if new_val and col in d:
                fields.append(f"{col} = ?")
                values.append(new_val)

        _maybe("product_url",             enrichment.get("product_url"))
        _maybe("mouser_part_number",      enrichment.get("mouser_part_number"))
        _maybe("digikey_part_number",     enrichment.get("digikey_part_number"))
        _maybe("manufacture_part_number", enrichment.get("manufacture_part_number"))
        _maybe("manufacturer",            enrichment.get("manufacturer"))
        _maybe("package",                 enrichment.get("package"))
        _maybe("rohs",                    enrichment.get("rohs"))
        _maybe("category",                full_path)
        _maybe("datasheet_url",           enrichment.get("datasheet_url"))

        # image_path : toujours écrit si on en a une nouvelle (quelle que soit la source)
        # En mode force, on écrase même si déjà présent (ré-enrichissement explicite)
        new_image = enrichment.get("image_path")
        if new_image and "image_path" in d:
            if not d["image_path"] or force_attributes:
                fields.append("image_path = ?")
                values.append(new_image)

        # Attributs techniques — toujours écrasés si on en a de nouveaux
        attrs = enrichment.get("attributes")
        if attrs and "attributes" in d:
            import json
            fields.append("attributes = ?")
            values.append(json.dumps(attrs, ensure_ascii=False))

        # Prix — cas particulier : on met à jour même si déjà présent si la valeur est 0 ou None
        unit_price = enrichment.get("unit_price")
        if unit_price and "unit_price" in d and not d["unit_price"]:
            fields.append("unit_price = ?")
            values.append(unit_price)

        # category_id : pas dans row.keys() si migration ancienne DB
        try:
            if cat_id and not d.get("category_id"):
                fields.append("category_id = ?")
                values.append(cat_id)
        except (IndexError, KeyError) as e:
            logger.debug("Ignored: %s", e)

        if fields:
            values.append(component_id)
            try:
                db.execute(
                    f"UPDATE components SET {', '.join(fields)} WHERE id = ?",
                    values,
                )
                db.commit()
            except Exception:
                db.rollback()
                raise

    @staticmethod
    def save_easyeda_pngs(component_id: int, symbol_png: str | None, footprint_png: str | None):
        """Sauvegarde les chemins des PNGs EasyEDA en base."""
        db = get_db()
        fields, values = [], []
        if symbol_png is not None:
            fields.append("symbol_png = ?")
            values.append(symbol_png)
        if footprint_png is not None:
            fields.append("footprint_png = ?")
            values.append(footprint_png)
        # Whitelist des colonnes autorisées pour le UPDATE dynamique
        _ALLOWED_ENRICH_COLS = {
            "image_path", "symbol_png", "footprint_png", "description_long",
            "manufacturer", "manufacture_part_number", "package", "rohs",
            "datasheet_url", "lcsc_part_number", "mouser_part_number",
            "digikey_part_number", "source_url", "unit_price",
        }
        fields = [f for f in fields if f.split(" = ?")[0].strip() in _ALLOWED_ENRICH_COLS]
        if fields:
            values = values[:len(fields)] + [component_id]
            try:
                db.execute(f"UPDATE components SET {', '.join(fields)} WHERE id = ?", values)
                db.commit()
            except Exception:
                db.rollback()
                raise

    @staticmethod
    def delete(component_id):
        import os
        from flask import current_app
        db = get_db()

        # I4 FIX : supprimer le fichier image avant la suppression en base
        row = db.execute(
            "SELECT image_path FROM components WHERE id = ?", (component_id,)
        ).fetchone()
        if row and row["image_path"]:
            try:
                img_path = os.path.join(
                    current_app.instance_path, "images",
                    os.path.basename(row["image_path"])
                )
                if os.path.isfile(img_path):
                    os.remove(img_path)
            except OSError:
                pass  # fichier déjà absent, pas bloquant

        try:
            db.execute("DELETE FROM components WHERE id = ?", (component_id,))
            db.commit()
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def adjust_quantity(component_id: int, delta: int) -> dict:
        """
        Ajuste la quantité du composant de +/- delta.
        Retourne {"ok": bool, "new_qty": int, "error": str|None}
        """
        db = get_db()
        row = db.execute(
            "SELECT quantity, min_stock FROM components WHERE id=?", (component_id,)
        ).fetchone()
        if not row:
            return {"ok": False, "error": "msg.err_not_found", "i18n": True}

        new_qty = row["quantity"] + delta
        if new_qty < 0:
            return {"ok": False, "error": "msg.err_stock_insufficient", "i18n": True, "qty": row["quantity"]}

        try:
            db.execute("UPDATE components SET quantity=? WHERE id=?", (new_qty, component_id))
            db.commit()
        except Exception:
            db.rollback()
            raise
        return {
            "ok":      True,
            "new_qty": new_qty,
            "is_low":  bool(row["min_stock"] and new_qty <= row["min_stock"]),
        }


    @staticmethod
    def get_dashboard_stats() -> dict:
        """Stats globales pour le dashboard (n_components, n_total_qty, n_alerts, n_zero, total_value)."""
        db = get_db()
        row = db.execute("""
            SELECT COUNT(*) AS n_components,
                   SUM(quantity) AS n_total_qty,
                   SUM(CASE WHEN min_stock > 0 AND quantity <= min_stock THEN 1 ELSE 0 END) AS n_alerts,
                   SUM(CASE WHEN quantity = 0 THEN 1 ELSE 0 END) AS n_zero,
                   ROUND(SUM(quantity * COALESCE(unit_price,0)),2) AS total_value
            FROM components
        """).fetchone()
        return row

    @staticmethod
    def get_recent(limit: int = 6) -> list:
        """Derniers composants ajoutés pour le dashboard."""
        db = get_db()
        return db.execute("""
            SELECT id, description, manufacture_part_number, lcsc_part_number,
                   mouser_part_number, digikey_part_number, product_url,
                   package, quantity, min_stock, unit_price, image_path
            FROM components ORDER BY created_at DESC LIMIT ?
        """, (limit,)).fetchall()

    @staticmethod
    def get_alerts_summary(limit: int = 6) -> list:
        """Composants en alerte pour le dashboard (les plus critiques en premier)."""
        db = get_db()
        return db.execute("""
            SELECT id, description, lcsc_part_number, mouser_part_number,
                   quantity, min_stock, image_path
            FROM components
            WHERE min_stock > 0 AND quantity <= min_stock
            ORDER BY quantity ASC LIMIT ?
        """, (limit,)).fetchall()

    @staticmethod
    def get_low_stock() -> list:
        """Retourne les composants sous leur seuil d'alerte (min_stock > 0)."""
        db = get_db()
        rows = db.execute(
            """
            SELECT * FROM components
            WHERE min_stock > 0 AND quantity <= min_stock
            ORDER BY (quantity * 1.0 / min_stock) ASC
            """
        ).fetchall()
        return [Component(r) for r in rows]

    @staticmethod
    def get_all_lcsc_refs() -> list:
        """
        Retourne les références LCSC générables dans KiCad.
        Filtre sur category_id IS NOT NULL : seuls les composants enrichis
        depuis LCSC ont un category_id, ce qui garantit que JLC2KiCadLib
        pourra trouver leur schéma EasyEDA.
        Les composants sans category_id (mécaniques, fils, ajouts manuels)
        sont exclus — ils n'ont pas de symbol/footprint EasyEDA.
        """
        db = get_db()
        rows = db.execute(
            "SELECT DISTINCT lcsc_part_number FROM components "
            "WHERE lcsc_part_number IS NOT NULL AND lcsc_part_number != '' "
            "AND category_id IS NOT NULL "
            "ORDER BY lcsc_part_number"
        ).fetchall()
        return [r["lcsc_part_number"] for r in rows]

    @staticmethod
    def get_lcsc_refs_by_category() -> dict:
        """Retourne un dict {categorie_slug: [lcsc_refs]} groupé par catégorie parente."""
        import re
        db = get_db()
        rows = db.execute(
            "SELECT lcsc_part_number, category FROM components "
            "WHERE lcsc_part_number IS NOT NULL AND lcsc_part_number != ''"
        ).fetchall()

        result = {}
        for row in rows:
            ref = row["lcsc_part_number"]
            cat = row["category"] or "Autres"
            # Prendre seulement la catégorie parente (avant le /)
            parent = cat.split("/")[0].strip() if "/" in cat else cat.strip()
            if not parent:
                parent = "Autres"
            # Slug : minuscules, espaces → underscores, sans accents ni caract. spéciaux
            slug = re.sub(r"[^a-z0-9_]", "", parent.lower().replace(" ", "_").replace("-", "_"))
            if not slug:
                slug = "autres"
            if slug not in result:
                result[slug] = {"name": parent, "refs": []}
            if ref not in result[slug]["refs"]:
                result[slug]["refs"].append(ref)

        return result

    @staticmethod
    def count_low_stock() -> int:
        db = get_db()
        return db.execute(
            "SELECT COUNT(*) FROM components WHERE min_stock > 0 AND quantity <= min_stock"
        ).fetchone()[0]

    # ------------------------------------------------------------------ #
    #  Import CSV avec déduplication
    # ------------------------------------------------------------------ #


    @staticmethod
    def analyse_csv_rows(rows: list[dict]) -> dict:
        """
        Analyse les lignes CSV et retourne un rapport de prévisualisation.
        Ne modifie PAS la base de données — lecture seule.

        Retourne :
          - to_import  : lignes nouvelles (avec infos détectées)
          - duplicates : lignes déjà en stock
          - skipped    : lignes sans référence fournisseur
          - errors     : lignes illisibles
          - columns    : colonnes détectées
        """
        db = get_db()

        if not rows:
            return {"to_import": [], "duplicates": [], "skipped": [], "errors": [], "columns": {}}

        headers   = list(rows[0].keys())
        lc_headers = {h.lower().strip(): h for h in headers}

        def _col(*candidates):
            for c in candidates:
                if c in lc_headers:
                    return lc_headers[c]
            return None

        lcsc_col    = _col("lcsc part number", "lcsc#", "lcsc part #", "lcsc", "lcsc_part_number")
        mouser_col  = _col("mouser", "mouser part number", "mouser part #", "mouser#", "mouser_part_number")
        digikey_col = _col("digikey", "digi-key", "digikey part number", "digikey part #", "digikey#", "digikey_part_number")
        qty_col     = _col("quantity", "qty", "quantité", "qté")
        desc_col    = _col("description", "value", "comment", "val")
        mfr_col     = _col("manufacture part number", "mpn", "manufacturer part number")
        mfr_name_col = _col("manufacturer")
        pkg_col     = _col("package")
        price_col   = _col("unit price(€)", "unit price", "prix unitaire")
        min_stock_col = _col("min_stock", "min stock", "seuil alerte", "seuil")
        cat_col     = _col("category", "catégorie", "categorie")
        loc_col     = _col("location", "emplacement")
        notes_col   = _col("notes", "remarques")
        source_url_col = _col("source / url achat", "source_url", "fournisseur", "url achat", "url")

        to_import  = []
        duplicates = []
        skipped    = []
        errors     = []

        for i, row in enumerate(rows, start=1):
            try:
                lcsc        = _clean(row.get(lcsc_col,    "") if lcsc_col    else "")
                mouser_ref  = _clean(row.get(mouser_col,  "") if mouser_col  else "")
                digikey_ref = _clean(row.get(digikey_col, "") if digikey_col else "")

                if lcsc:        lcsc        = lcsc.upper()
                if mouser_ref:  mouser_ref  = " ".join(mouser_ref.split())
                if digikey_ref: digikey_ref = " ".join(digikey_ref.split())

                desc       = _clean(row.get(desc_col,     "") if desc_col     else "")
                mfr_part   = _clean(row.get(mfr_col,      "") if mfr_col      else "")
                mfr_name   = _clean(row.get(mfr_name_col, "") if mfr_name_col else "")
                pkg        = _clean(row.get(pkg_col,       "") if pkg_col      else "")
                source_url = _clean(row.get(source_url_col,"") if source_url_col else "")

                try:
                    qty = int(float(row.get(qty_col, 0) if qty_col else 0))
                except (ValueError, TypeError):
                    qty = 0

                try:
                    price = _to_float(row.get(price_col) if price_col else None)
                except Exception:
                    price = None

                try:
                    min_stock_v = max(0, int(_clean(row.get(min_stock_col, "") if min_stock_col else "") or 0))
                except (ValueError, TypeError):
                    min_stock_v = 0

                if not any([lcsc, mouser_ref, digikey_ref]):
                    skipped.append({"row": i, "desc": desc or "—"})
                    continue

                # Cherche si déjà en stock
                existing = None
                if lcsc:
                    existing = db.execute(
                        "SELECT id, description, quantity FROM components WHERE lcsc_part_number = ?",
                        (lcsc,)
                    ).fetchone()
                if not existing and mouser_ref:
                    existing = db.execute(
                        "SELECT id, description, quantity FROM components WHERE mouser_part_number = ?",
                        (mouser_ref,)
                    ).fetchone()
                if not existing and digikey_ref:
                    existing = db.execute(
                        "SELECT id, description, quantity FROM components WHERE digikey_part_number = ?",
                        (digikey_ref,)
                    ).fetchone()

                entry = {
                    "row":         i,
                    "lcsc":        lcsc or "",
                    "mouser":      mouser_ref or "",
                    "digikey":     digikey_ref or "",
                    "description": desc or mfr_part or lcsc or mouser_ref or digikey_ref or "—",
                    "manufacturer":mfr_name or "",
                    "mfr_part":    mfr_part or "",
                    "package":     pkg or "",
                    "quantity":    qty,
                    "min_stock":   min_stock_v,
                    "unit_price":  price,
                    "source_url":  source_url or "",
                    "source":      "lcsc" if lcsc else ("mouser" if mouser_ref else "digikey"),
                }

                if existing:
                    entry["existing_id"]  = existing["id"]
                    entry["existing_desc"]= existing["description"]
                    entry["existing_qty"] = existing["quantity"]
                    duplicates.append(entry)
                else:
                    to_import.append(entry)

            except Exception as exc:
                errors.append({"row": i, "error": str(exc)})

        return {
            "to_import":  to_import,
            "duplicates": duplicates,
            "skipped":    skipped,
            "errors":     errors,
            "columns": {
                "lcsc":       bool(lcsc_col),
                "mouser":     bool(mouser_col),
                "digikey":    bool(digikey_col),
                "qty":        bool(qty_col),
                "price":      bool(price_col),
                "desc":       bool(desc_col),
                "source_url": bool(source_url_col),
            },
        }

    @staticmethod
    def import_from_csv_rows(rows):
        """
        rows : liste de dicts CSV.
        Supporte les colonnes LCSC, Mouser et DigiKey.
        """
        db = get_db()
        inserted = 0
        skipped = 0
        duplicates = []
        errors = []
        component_ids = []
        mouser_ids    = []
        digikey_ids   = []

        # Détecte les colonnes disponibles
        if not rows:
            return {"inserted": 0, "skipped": 0, "duplicates": [], "errors": [], "component_ids": []}

        headers = list(rows[0].keys())
        lc_headers = {h.lower().strip(): h for h in headers}

        def _col(*candidates):
            for c in candidates:
                if c in lc_headers:
                    return lc_headers[c]
            return None

        lcsc_col    = _col("lcsc part number", "lcsc#", "lcsc part #", "lcsc")
        mouser_col  = _col("mouser", "mouser part number", "mouser part #", "mouser#")
        digikey_col = _col("digikey", "digi-key", "digikey part number", "digikey part #", "digikey#")
        qty_col     = _col("quantity", "qty", "quantité", "qté")
        desc_col    = _col("description", "value", "comment", "val")
        mfr_col     = _col("manufacture part number", "mpn", "manufacturer part number")
        mfr_name_col = _col("manufacturer")
        pkg_col     = _col("package")
        price_col   = _col("unit price(€)", "unit price", "prix unitaire")
        ext_col     = _col("ext.price(€)", "extended price(€)", "ext price")
        rohs_col    = _col("rohs")
        cust_col    = _col("customer no.", "customer #", "customer_no")
        min_stock_col = _col("min_stock", "min stock", "seuil alerte", "seuil")
        cat_col        = _col("category", "catégorie", "categorie")
        loc_col        = _col("location", "emplacement", "location")
        notes_col      = _col("notes", "remarques")
        source_url_col = _col("source / url achat", "source_url", "fournisseur", "url achat", "url")

        for i, row in enumerate(rows, start=1):
            try:
                _lcsc_raw   = _clean(row.get(lcsc_col,    "") if lcsc_col    else "")
                lcsc        = _lcsc_raw.upper().strip() if _lcsc_raw else None
                mouser_ref  = _clean(row.get(mouser_col,  "") if mouser_col  else "")
                digikey_ref = _clean(row.get(digikey_col, "") if digikey_col else "")
                # Normalisation : espaces internes, tirets, casse
                if mouser_ref:
                    mouser_ref  = " ".join(mouser_ref.split())  # espaces multiples → 1
                if digikey_ref:
                    digikey_ref = " ".join(digikey_ref.split())
                desc        = _clean(row.get(desc_col,    "") if desc_col    else "")
                mfr_part    = _clean(row.get(mfr_col,     "") if mfr_col     else "")
                min_stock_v = max(0, int(_clean(row.get(min_stock_col, "") if min_stock_col else "") or 0))
                category_v  = _clean(row.get(cat_col,   "") if cat_col   else "")
                location_v  = _clean(row.get(loc_col,   "") if loc_col   else "")
                notes_v      = _clean(row.get(notes_col,      "") if notes_col      else "")
                source_url_v = _clean(row.get(source_url_col, "") if source_url_col else "")

                # Ignore les lignes sans aucune ref fournisseur
                if not any([lcsc, mouser_ref, digikey_ref]):
                    skipped += 1
                    continue

                # Déduplication
                if lcsc:
                    existing = db.execute(
                        "SELECT id FROM components WHERE lcsc_part_number = ?", (lcsc,)
                    ).fetchone()
                    if existing:
                        duplicates.append(lcsc)
                        continue
                if not lcsc and mouser_ref:
                    existing = db.execute(
                        "SELECT id FROM components WHERE mouser_part_number = ?", (mouser_ref,)
                    ).fetchone()
                    if existing:
                        duplicates.append(mouser_ref)
                        continue
                if not lcsc and not mouser_ref and digikey_ref:
                    existing = db.execute(
                        "SELECT id FROM components WHERE digikey_part_number = ?", (digikey_ref,)
                    ).fetchone()
                    if existing:
                        duplicates.append(digikey_ref)
                        continue

                qty  = int(float(row.get(qty_col, 0) if qty_col else 0))
                unit = _to_float(row.get(price_col) if price_col else None)
                ext  = _to_float(row.get(ext_col)   if ext_col   else None)
                if ext is None and unit is not None:
                    ext = round(unit * qty, 4)
                rohs_raw = _clean(row.get(rohs_col, "") if rohs_col else "")
                rohs = rohs_raw.upper() if rohs_raw else None
                customer = _clean(row.get(cust_col, "") if cust_col else "")

                cursor = db.execute(
                    """
                    INSERT INTO components (
                        lcsc_part_number, mouser_part_number, digikey_part_number,
                        manufacture_part_number, manufacturer,
                        customer_no, package, description, description_long, rohs,
                        quantity, min_stock, unit_price, ext_price,
                        category, location, notes, source_url
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _to_none(lcsc),
                        _to_none(mouser_ref),
                        _to_none(digikey_ref),
                        _to_none(mfr_part),
                        _clean(row.get(mfr_name_col, "") if mfr_name_col else ""),
                        _to_none(customer),
                        _clean(row.get(pkg_col, "") if pkg_col else ""),
                        desc,
                        None,  # description_long — sera rempli par l'enrich API
                        rohs,
                        qty,
                        min_stock_v,
                        unit,
                        ext,
                        _to_none(category_v),
                        _to_none(location_v),
                        _to_none(notes_v),
                        _to_none(source_url_v),
                    ),
                )
                new_id = cursor.lastrowid
                if lcsc:
                    component_ids.append((new_id, lcsc))
                elif mouser_ref:
                    mouser_ids.append((new_id, mouser_ref))
                elif digikey_ref:
                    digikey_ids.append((new_id, digikey_ref))
                inserted += 1

            except Exception as exc:
                errors.append(f"Ligne {i} : {exc}")

        try:
            db.commit()
        except Exception:
            db.rollback()
            raise
        return {
            "inserted":      inserted,
            "skipped":       skipped,
            "duplicates":    duplicates,
            "errors":        errors,
            "component_ids": component_ids,
            "mouser_ids":    mouser_ids,
            "digikey_ids":   digikey_ids,
        }


# ------------------------------------------------------------------ #
#  Helpers privés
# ------------------------------------------------------------------ #

_ALLOWED_SORTS = {
    "description", "manufacturer", "package",
    "quantity", "unit_price", "created_at", "category",
    # "created_at" est le tri par défaut dans routes_stock.py — doit rester dans la whitelist
}


def _build_where(search, category, low_only=False, location=None):
    where = "WHERE 1=1"
    params = []

    if search:
        where += """
            AND (
                description             LIKE ?
                OR description_long     LIKE ?
                OR manufacture_part_number LIKE ?
                OR lcsc_part_number        LIKE ?
                OR mouser_part_number      LIKE ?
                OR digikey_part_number     LIKE ?
                OR manufacturer            LIKE ?
                OR package                 LIKE ?
                OR notes                   LIKE ?
            )
        """
        like = f"%{search}%"
        params.extend([like, like, like, like, like, like, like, like, like])

    if category:
        where += " AND category = ?"
        params.append(category)

    if low_only:
        where += " AND min_stock > 0 AND quantity <= min_stock"

    if location:
        where += " AND location LIKE ?"
        params.append(f"{location}%")

    return where, params


def _clean(value):
    if value is None:
        return None
    s = str(value).strip()
    return s if s not in ("", "nan", "NaN", "None") else None


def _to_float(value):
    if value is None:
        return None
    try:
        return float(str(value).replace(",", ".").strip())
    except (ValueError, TypeError):
        return None


def _to_none(value):
    """Convertit une chaîne vide en None (NULL en SQLite) — évite les violations UNIQUE."""
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None
