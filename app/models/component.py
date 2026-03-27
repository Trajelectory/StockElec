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
        self.symbol_svg              = row["symbol_svg"]    if "symbol_svg"    in keys else None
        self.footprint_svg           = row["footprint_svg"] if "footprint_svg" in keys else None
        self.symbol_png              = row["symbol_png"]    if "symbol_png"    in keys else None
        self.footprint_png           = row["footprint_png"] if "footprint_png" in keys else None
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
    def get_categories():
        """Catégories présentes dans le stock (pour le filtre déroulant)."""
        db = get_db()
        rows = db.execute(
            """
            SELECT DISTINCT category FROM components
            WHERE category IS NOT NULL AND category != ''
            ORDER BY category
            """
        ).fetchall()
        return [r["category"] for r in rows]

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
                lcsc_part_number, manufacture_part_number, manufacturer,
                customer_no, package, description, rohs,
                quantity, min_stock, unit_price, ext_price,
                category, category_id, location, notes,
                image_path, datasheet_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("lcsc_part_number"),
                data.get("manufacture_part_number"),
                data.get("manufacturer"),
                data.get("customer_no"),
                data.get("package"),
                data.get("description"),
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
        comp_id = cursor.lastrowid
        if qty > 0:
            from .movement import MovementModel, TYPE_MANUAL_ADD
            MovementModel.record(comp_id, TYPE_MANUAL_ADD, 0, qty, note="Création")
        return comp_id

    @staticmethod
    def update(component_id, data):
        db = get_db()
        # Enregistre un mouvement si la quantité a changé
        row = db.execute("SELECT quantity FROM components WHERE id=?", (component_id,)).fetchone()
        new_qty = int(data.get("quantity") or 0)
        if row and row["quantity"] != new_qty:
            from .movement import MovementModel, TYPE_ADJUSTMENT
            MovementModel.record(
                component_id, TYPE_ADJUSTMENT,
                qty_before=row["quantity"],
                qty_change=new_qty - row["quantity"],
                note="Modification via formulaire",
            )
        db.execute(
            """
            UPDATE components SET
                lcsc_part_number        = ?,
                manufacture_part_number = ?,
                manufacturer            = ?,
                customer_no             = ?,
                package                 = ?,
                description             = ?,
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
                data.get("lcsc_part_number"),
                data.get("manufacture_part_number"),
                data.get("manufacturer"),
                data.get("customer_no"),
                data.get("package"),
                data.get("description"),
                data.get("rohs"),
                new_qty,
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
    def apply_enrichment(component_id: int, enrichment: dict):
        """
        Applique les données du scraper LCSC.
        Ne remplace que les champs encore vides.
        Met aussi à jour la table categories si les infos sont présentes.
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

        _maybe("category",      full_path)
        _maybe("image_path",    enrichment.get("image_path"))
        _maybe("datasheet_url", enrichment.get("datasheet_url"))

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
    def save_easyeda_svgs(component_id: int, symbol_svg: str | None, footprint_svg: str | None):
        """Sauvegarde le symbole et/ou le footprint EasyEDA (SVG) en base."""
        db = get_db()
        fields, values = [], []
        if symbol_svg is not None:
            fields.append("symbol_svg = ?")
            values.append(symbol_svg)
        if footprint_svg is not None:
            fields.append("footprint_svg = ?")
            values.append(footprint_svg)
        if fields:
            values.append(component_id)
            db.execute(f"UPDATE components SET {', '.join(fields)} WHERE id = ?", values)
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
    def adjust_quantity(component_id: int, delta: int, movement_type: str,
                        project_id: int = None, note: str = None) -> dict:
        """
        Ajuste la quantité du composant de +/- delta.
        Retourne {"ok": bool, "new_qty": int, "error": str|None}
        """
        from .movement import MovementModel
        db = get_db()
        row = db.execute(
            "SELECT quantity FROM components WHERE id=?", (component_id,)
        ).fetchone()
        if not row:
            return {"ok": False, "error": "Composant introuvable"}

        qty_before = row["quantity"]
        new_qty    = qty_before + delta
        if new_qty < 0:
            return {"ok": False, "error": f"Stock insuffisant (disponible : {qty_before})"}

        db.execute(
            "UPDATE components SET quantity=? WHERE id=?", (new_qty, component_id)
        )
        db.commit()

        MovementModel.record(
            component_id, movement_type,
            qty_before=qty_before,
            qty_change=delta,
            project_id=project_id,
            note=note,
        )
        return {"ok": True, "new_qty": new_qty}

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
        rows : liste de dicts CSV LCSC.

        Retourne un dict :
          {
            "inserted":      int,
            "skipped":       int,          # lignes vides / sans ref
            "duplicates":    [str, ...],   # refs LCSC déjà en stock
            "errors":        [str, ...],
            "component_ids": [(id, lcsc_ref), ...]   # pour enrichissement
          }
        """
        db = get_db()
        inserted = 0
        skipped = 0
        duplicates = []
        errors = []
        component_ids = []

        for i, row in enumerate(rows, start=1):
            try:
                lcsc     = _clean(row.get("LCSC Part Number"))
                mfr_part = _clean(row.get("Manufacture Part Number"))
                desc     = _clean(row.get("Description"))

                if not any([lcsc, mfr_part, desc]):
                    skipped += 1
                    continue

                # --- Déduplication ---
                if lcsc:
                    existing = db.execute(
                        "SELECT id FROM components WHERE lcsc_part_number = ?", (lcsc,)
                    ).fetchone()
                    if existing:
                        duplicates.append(lcsc)
                        continue

                qty  = int(float(row.get("Quantity") or 0))
                unit = _to_float(row.get("Unit Price(€)"))
                ext  = _to_float(row.get("Ext.Price(€)"))
                if ext is None and unit is not None:
                    ext = round(unit * qty, 4)

                cursor = db.execute(
                    """
                    INSERT INTO components (
                        lcsc_part_number, manufacture_part_number, manufacturer,
                        customer_no, package, description, rohs,
                        quantity, unit_price, ext_price
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        lcsc,
                        mfr_part,
                        _clean(row.get("Manufacturer")),
                        _clean(row.get("Customer NO.")),
                        _clean(row.get("Package")),
                        desc,
                        _clean(row.get("RoHS")),
                        qty,
                        unit,
                        ext,
                    ),
                )
                new_id = cursor.lastrowid
                component_ids.append((new_id, lcsc))
                inserted += 1
                # Mouvement d'import
                if qty > 0:
                    from .movement import MovementModel, TYPE_IMPORT
                    MovementModel.record(new_id, TYPE_IMPORT, 0, qty, note="Import CSV")

            except Exception as exc:
                errors.append(f"Ligne {i} : {exc}")

        db.commit()
        return {
            "inserted":      inserted,
            "skipped":       skipped,
            "duplicates":    duplicates,
            "errors":        errors,
            "component_ids": component_ids,
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
