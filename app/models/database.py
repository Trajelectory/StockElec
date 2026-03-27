import sqlite3
import os
from flask import g

DATABASE = None


def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


def init_db(app):
    global DATABASE
    DATABASE = os.path.join(app.instance_path, "stock.db")
    os.makedirs(app.instance_path, exist_ok=True)

    @app.teardown_appcontext
    def close_connection(exception):
        db = getattr(g, "_database", None)
        if db is not None:
            db.close()

    with app.app_context():
        db = get_db()
        db.executescript("""
            CREATE TABLE IF NOT EXISTS components (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                lcsc_part_number        TEXT UNIQUE,
                manufacture_part_number TEXT,
                manufacturer            TEXT,
                customer_no             TEXT,
                package                 TEXT,
                description             TEXT,
                rohs                    TEXT,
                quantity                INTEGER DEFAULT 0,
                min_stock               INTEGER DEFAULT 0,
                unit_price              REAL,
                ext_price               REAL,
                category                TEXT,
                category_id             INTEGER,
                location                TEXT,
                notes                   TEXT,
                image_path              TEXT,
                datasheet_url           TEXT,
                created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TRIGGER IF NOT EXISTS update_timestamp
            AFTER UPDATE ON components
            BEGIN
                UPDATE components SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
            END;

            -- Catégories LCSC
            CREATE TABLE IF NOT EXISTS categories (
                id        INTEGER PRIMARY KEY,
                parent_id INTEGER,
                name      TEXT NOT NULL,
                full_path TEXT,
                FOREIGN KEY (parent_id) REFERENCES categories(id)
            );

            -- Projets
            CREATE TABLE IF NOT EXISTS projects (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                description TEXT,
                status      TEXT DEFAULT 'en cours',
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TRIGGER IF NOT EXISTS update_project_timestamp
            AFTER UPDATE ON projects
            BEGIN
                UPDATE projects SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
            END;

            -- Liaison composants <-> projets (avec quantité utilisée)
            CREATE TABLE IF NOT EXISTS project_components (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id   INTEGER NOT NULL,
                component_id INTEGER NOT NULL,
                quantity     INTEGER DEFAULT 1,
                notes        TEXT,
                FOREIGN KEY (project_id)   REFERENCES projects(id)   ON DELETE CASCADE,
                FOREIGN KEY (component_id) REFERENCES components(id) ON DELETE CASCADE,
                UNIQUE (project_id, component_id)
            );

            -- Historique des mouvements de stock
            CREATE TABLE IF NOT EXISTS stock_movements (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                component_id INTEGER NOT NULL,
                type         TEXT NOT NULL,  -- 'import', 'manual_add', 'manual_remove', 'project_use', 'project_return', 'adjustment'
                qty_before   INTEGER NOT NULL,
                qty_change   INTEGER NOT NULL,  -- positif = entrée, négatif = sortie
                qty_after    INTEGER NOT NULL,
                project_id   INTEGER,
                note         TEXT,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (component_id) REFERENCES components(id) ON DELETE CASCADE,
                FOREIGN KEY (project_id)   REFERENCES projects(id)   ON DELETE SET NULL
            );

            -- Config clé/valeur
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            );
        """)

        # Migrations à chaud pour DB existantes
        existing_cols = {r[1] for r in db.execute("PRAGMA table_info(components)").fetchall()}
        for col, typedef in [
            ("image_path",    "TEXT"),
            ("datasheet_url", "TEXT"),
            ("category_id",   "INTEGER"),
            ("min_stock",     "INTEGER DEFAULT 0"),
        ]:
            if col not in existing_cols:
                db.execute(f"ALTER TABLE components ADD COLUMN {col} {typedef}")

        # Migration projects : ajout image_path
        proj_cols = {r[1] for r in db.execute("PRAGMA table_info(projects)").fetchall()}
        if "image_path" not in proj_cols:
            db.execute("ALTER TABLE projects ADD COLUMN image_path TEXT")

        # Migration components : symbole et footprint EasyEDA (chemins PNG)
        for col in ("symbol_svg", "footprint_svg", "symbol_png", "footprint_png"):
            if col not in existing_cols:
                db.execute(f"ALTER TABLE components ADD COLUMN {col} TEXT")

        db.commit()
