from .database import get_db

ITEMS_PER_PAGE_DEFAULT = 25


class Component:
    """Représente un composant électronique dans le stock."""

    def __init__(self, row):
        keys = row.keys()
        self.id                      = row["id"]
        self.lcsc_part_number        = row["lcsc_part_number"]
        self.manufacture_part_number = row["manufacture_part_number"]
        self.manufacturer            = row["manufacturer"]
        self.customer_no             = row["customer_no"]
        self.package                 = row["package"]
        self.description             = row["description"]
        self.rohs                    = row["rohs"]
        self.quantity                = row["quantity"]
        self.min_stock               = row["min_stock"] if "min_stock" in keys else 0
        self.unit_price              = row["unit_price"]
        self.ext_price               = row["ext_price"]
        self.category                = row["category"]
        self.category_id             = row["category_id"] if "category_id" in keys else None
        self.location                = row["location"]
        self.notes                   = row["notes"]
        self.image_path              = row["image_path"]    if "image_path"    in keys else None
        self.datasheet_url           = row["datasheet_url"] if "datasheet_url" in keys else None
        self.symbol_png              = row["symbol_png"]    if "symbol_png"    in keys else None
        self.footprint_png           = row["footprint_png"] if "footprint_png" in keys else None
        self.attributes              = row["attributes"]          if "attributes"          in keys else None
        self.description_long        = row["description_long"]    if "description_long"    in keys else None
        self.mouser_part_number      = row["mouser_part_number"]  if "mouser_part_number"  in keys else None
        self.digikey_part_number     = row["digikey_part_number"] if "digikey_part_number" in keys else None
        self.product_url             = row["product_url"]         if "product_url"         in keys else None
        self.created_at              = row["created_at"]
        self.updated_at              = row["updated_at"]

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
    def get_page(search=None, category=None, sort_by="description", order="asc",
                 page=1, per_page=ITEMS_PER_PAGE_DEFAULT, low_only=False):
        """
        Retourne (components, total_count) pour la page demandée.
        """
        db = get_db()
        where, params = _build_where(search, category, low_only=low_only)

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
        cursor = db.execute(
            """
            INSERT INTO components (
                lcsc_part_number, mouser_part_number, digikey_part_number,
                manufacture_part_number, manufacturer,
                customer_no, package, description, description_long, rohs,
                quantity, min_stock, unit_price, ext_price,
                category, category_id, location, notes,
                image_path, datasheet_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ),
        )
        db.commit()
        return cursor.lastrowid

    @staticmethod
    def update(component_id, data):
        db = get_db()
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
                datasheet_url           = ?
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
                component_id,
            ),
        )
        db.commit()

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
        row_keys = row.keys()

        def _maybe(col, new_val):
            if not new_val:
                return
            if col not in row_keys:
                return
            if not row[col]:
                fields.append(f"{col} = ?")
                values.append(new_val)

        # description et description_long : toujours écrasés par l'API distributeur
        # (la valeur KiCad "0R 0402" est moins précise que "RES 100Ω ±1% 62.5mW 0402")
        for col in ("description", "description_long"):
            new_val = enrichment.get(col)
            if new_val and col in row_keys:
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
        if new_image and "image_path" in row_keys:
            if not row["image_path"] or force_attributes:
                fields.append("image_path = ?")
                values.append(new_image)

        # Attributs techniques — toujours écrasés si on en a de nouveaux
        attrs = enrichment.get("attributes")
        if attrs and "attributes" in row_keys:
            import json as _json
            fields.append("attributes = ?")
            values.append(_json.dumps(attrs, ensure_ascii=False))

        # Prix — cas particulier : on met à jour même si déjà présent si la valeur est 0 ou None
        unit_price = enrichment.get("unit_price")
        if unit_price and "unit_price" in row_keys and not row["unit_price"]:
            fields.append("unit_price = ?")
            values.append(unit_price)

        # category_id : pas dans row.keys() si migration ancienne DB
        try:
            if cat_id and not row["category_id"]:
                fields.append("category_id = ?")
                values.append(cat_id)
        except (IndexError, KeyError):
            pass

        if fields:
            values.append(component_id)
            db.execute(
                f"UPDATE components SET {', '.join(fields)} WHERE id = ?",
                values,
            )
            db.commit()

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
        if fields:
            values.append(component_id)
            db.execute(f"UPDATE components SET {', '.join(fields)} WHERE id = ?", values)
            db.commit()

    @staticmethod
    def delete(component_id):
        db = get_db()
        db.execute("DELETE FROM components WHERE id = ?", (component_id,))
        db.commit()

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
            return {"ok": False, "error": "Composant introuvable"}

        new_qty = row["quantity"] + delta
        if new_qty < 0:
            return {"ok": False, "error": f"Stock insuffisant (disponible : {row['quantity']})"}

        db.execute("UPDATE components SET quantity=? WHERE id=?", (new_qty, component_id))
        db.commit()
        return {
            "ok":      True,
            "new_qty": new_qty,
            "is_low":  bool(row["min_stock"] and new_qty <= row["min_stock"]),
        }

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
    def count_low_stock() -> int:
        db = get_db()
        return db.execute(
            "SELECT COUNT(*) FROM components WHERE min_stock > 0 AND quantity <= min_stock"
        ).fetchone()[0]

    # ------------------------------------------------------------------ #
    #  Import CSV avec déduplication
    # ------------------------------------------------------------------ #

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
        cat_col       = _col("category", "catégorie", "categorie")
        loc_col       = _col("location", "emplacement", "location")
        notes_col     = _col("notes", "remarques", "comment")

        for i, row in enumerate(rows, start=1):
            try:
                lcsc        = _clean(row.get(lcsc_col,    "") if lcsc_col    else "")
                mouser_ref  = _clean(row.get(mouser_col,  "") if mouser_col  else "")
                digikey_ref = _clean(row.get(digikey_col, "") if digikey_col else "")
                desc        = _clean(row.get(desc_col,    "") if desc_col    else "")
                mfr_part    = _clean(row.get(mfr_col,     "") if mfr_col     else "")
                min_stock_v = int(_clean(row.get(min_stock_col, "") if min_stock_col else "") or 0)
                category_v  = _clean(row.get(cat_col,   "") if cat_col   else "")
                location_v  = _clean(row.get(loc_col,   "") if loc_col   else "")
                notes_v     = _clean(row.get(notes_col, "") if notes_col else "")

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
                        customer_no, package, description, rohs,
                        quantity, min_stock, unit_price, ext_price,
                        category, location, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        rohs,
                        qty,
                        min_stock_v,
                        unit,
                        ext,
                        _to_none(category_v),
                        _to_none(location_v),
                        _to_none(notes_v),
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

        db.commit()
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
}


def _build_where(search, category, low_only=False):
    where = "WHERE 1=1"
    params = []

    if search:
        where += """
            AND (
                description             LIKE ?
                OR manufacture_part_number LIKE ?
                OR lcsc_part_number        LIKE ?
                OR manufacturer            LIKE ?
                OR package                 LIKE ?
            )
        """
        like = f"%{search}%"
        params.extend([like, like, like, like, like])

    if category:
        where += " AND category = ?"
        params.append(category)

    if low_only:
        where += " AND min_stock > 0 AND quantity <= min_stock"

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
