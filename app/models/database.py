import sqlite3
import os
import logging
from flask import g

logger = logging.getLogger(__name__)

DATABASE = None
_wal_initialized = False  # PRAGMAs WAL/synchronous persistants — 1 seule init suffît


def get_db():
    global _wal_initialized
    db = getattr(g, "_database", None)
    if db is None:
        raw = sqlite3.connect(DATABASE, timeout=10)
        raw.row_factory = sqlite3.Row
        # foreign_keys doit être activé par connexion (non persistant)
        raw.execute("PRAGMA foreign_keys=ON")
        if not _wal_initialized:
            # WAL et synchronous sont persistants sur le fichier — 1 seule fois
            raw.execute("PRAGMA journal_mode=WAL")
            raw.execute("PRAGMA synchronous=NORMAL")
            _wal_initialized = True
        # Instrumenter si la debug toolbar est active
        try:
            from app.debugtoolbar import wrap_db, get_collector
            db = wrap_db(raw) if get_collector() is not None else raw
        except Exception:
            db = raw
        g._database = db
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
                source_url              TEXT,
                created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TRIGGER IF NOT EXISTS update_timestamp
            AFTER UPDATE ON components
            BEGIN
                UPDATE components SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
            END;

            CREATE TABLE IF NOT EXISTS categories (
                id        INTEGER PRIMARY KEY,
                parent_id INTEGER,
                name      TEXT NOT NULL,
                full_path TEXT,
                FOREIGN KEY (parent_id) REFERENCES categories(id)
            );

            CREATE TABLE IF NOT EXISTS projects (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                description TEXT,
                status      TEXT DEFAULT 'idea',
                tags        TEXT DEFAULT '[]',
                checklist   TEXT DEFAULT '[]',
                links       TEXT DEFAULT '[]',
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TRIGGER IF NOT EXISTS update_project_timestamp
            AFTER UPDATE ON projects
            BEGIN
                UPDATE projects SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
            END;

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

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            );
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS ateliers (
                id              TEXT PRIMARY KEY,
                name            TEXT NOT NULL DEFAULT 'Atelier',
                emoji           TEXT NOT NULL DEFAULT '📦',
                color           TEXT NOT NULL DEFAULT '#7c3aed',
                position        INTEGER NOT NULL DEFAULT 0,
                esp32_url       TEXT NOT NULL DEFAULT '',
                esp32_token     TEXT NOT NULL DEFAULT '',
                esp32_duration  INTEGER NOT NULL DEFAULT 5,
                esp32_offsets   TEXT NOT NULL DEFAULT '{}'
            );
        """)
        if db.execute("SELECT COUNT(*) FROM ateliers").fetchone()[0] == 0:
            _esp32_url   = db.execute("SELECT value FROM settings WHERE key='esp32_url'").fetchone()
            _esp32_token = db.execute("SELECT value FROM settings WHERE key='esp32_token'").fetchone()
            db.execute(
                "INSERT OR IGNORE INTO ateliers(id,name,emoji,color,position,esp32_url,esp32_token)"
                " VALUES(?,?,?,?,?,?,?)",
                ("principal","Atelier principal","🔧","#7c3aed",0,
                 _esp32_url[0]   if _esp32_url   else "",
                 _esp32_token[0] if _esp32_token else "")
            )

        # ── Migrations colonnes components ────────────────────────────────
        # C4 FIX : on relit les colonnes existantes AVANT chaque ALTER TABLE
        # via une fonction locale — évite le snapshot stale de l'ancienne approche.
        def _col_exists(col):
            cols = {r[1] for r in db.execute("PRAGMA table_info(components)").fetchall()}
            return col in cols

        for col, typedef in [
            ("image_path",          "TEXT"),
            ("datasheet_url",       "TEXT"),
            ("category_id",         "INTEGER"),
            ("min_stock",           "INTEGER DEFAULT 0"),
            ("attributes",          "TEXT"),
            ("description_long",    "TEXT"),
            ("mouser_part_number",  "TEXT"),
            ("digikey_part_number", "TEXT"),
            ("product_url",         "TEXT"),
            ("source_url",          "TEXT"),
            ("symbol_png",          "TEXT"),
            ("footprint_png",       "TEXT"),
        ]:
            if not _col_exists(col):
                try:
                    db.execute(f"ALTER TABLE components ADD COLUMN {col} {typedef}")
                    logger.info("[DB] Migration : ajout colonne components.%s", col)
                except sqlite3.OperationalError:
                    pass

        # ── Migrations colonnes projects ──────────────────────────────────
        def _proj_col_exists(col):
            cols = {r[1] for r in db.execute("PRAGMA table_info(projects)").fetchall()}
            return col in cols

        for col, typedef in [("image_path", "TEXT")]:
            if not _proj_col_exists(col):
                try:
                    db.execute(f"ALTER TABLE projects ADD COLUMN {col} {typedef}")
                except sqlite3.OperationalError:
                    pass

        _migrate_v2(db)

def _migrate_v2(db):
    """Migrations v2.0 — historique des mouvements."""
    # Vérifie si la table existe avec le bon schéma
    cols = {r[1] for r in db.execute("PRAGMA table_info(stock_movements)").fetchall()}

    # Migration projects : tags, checklist, links
    proj_cols = {r[1] for r in db.execute("PRAGMA table_info(projects)").fetchall()}
    for col, default in [("tags", "'[]'"), ("checklist", "'[]'"), ("links", "'[]'"),
                         ("image_path", "NULL"), ("notes", "NULL")]:
        if col not in proj_cols:
            db.execute(f"ALTER TABLE projects ADD COLUMN {col} TEXT DEFAULT {default}")
            db.commit()
    if cols and "quantity" not in cols:
        # Ancienne table sans la colonne quantity — on la recrée
        db.execute("DROP TABLE IF EXISTS stock_movements")
    db.execute("""
        CREATE TABLE IF NOT EXISTS stock_movements (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            component_id INTEGER NOT NULL,
            type         TEXT NOT NULL,
            quantity     INTEGER NOT NULL,
            note         TEXT,
            project_id   INTEGER,
            created_at   TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY(component_id) REFERENCES components(id) ON DELETE CASCADE
        )
    """)
    db.commit()

    # ── Index pour les performances ───────────────────────────────
    indexes = {r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='index'"
    ).fetchall()}

    index_defs = [
        # Index existants
        ("idx_components_category",        "CREATE INDEX idx_components_category        ON components(category)"),
        ("idx_components_location",        "CREATE INDEX idx_components_location        ON components(location)"),
        ("idx_components_lcsc",            "CREATE INDEX idx_components_lcsc            ON components(lcsc_part_number)"),
        ("idx_stock_movements_component",  "CREATE INDEX idx_stock_movements_component  ON stock_movements(component_id)"),
        ("idx_stock_movements_project",    "CREATE INDEX idx_stock_movements_project    ON stock_movements(project_id)"),
        ("idx_project_components_project", "CREATE INDEX idx_project_components_project ON project_components(project_id)"),
        # I6 FIX : index sur colonnes de recherche fulltext fréquentes
        ("idx_components_description",     "CREATE INDEX idx_components_description     ON components(description)"),
        ("idx_components_manufacturer",    "CREATE INDEX idx_components_manufacturer    ON components(manufacturer)"),
        ("idx_components_mouser",          "CREATE INDEX idx_components_mouser          ON components(mouser_part_number)"),
        ("idx_components_digikey",         "CREATE INDEX idx_components_digikey         ON components(digikey_part_number)"),
        ("idx_components_min_stock",       "CREATE INDEX idx_components_min_stock       ON components(min_stock, quantity)"),
    ]
    for idx_name, idx_sql in index_defs:
        if idx_name not in indexes:
            db.execute(idx_sql)
    db.commit()

    # ── Migration v3.2 — statuts projet FR → slugs anglais ───────
    # Idempotente : on ne migre que si des valeurs FR subsistent encore
    fr_statuts = db.execute(
        "SELECT COUNT(*) FROM projects WHERE status IN "
        "('idée','conception','commandé','en production','assemblage','terminé','archivé')"
    ).fetchone()[0]
    if fr_statuts > 0:
        db.execute("""
            UPDATE projects SET status = CASE status
                WHEN 'idée'          THEN 'idea'
                WHEN 'conception'    THEN 'design'
                WHEN 'commandé'      THEN 'ordered'
                WHEN 'en production' THEN 'production'
                WHEN 'assemblage'    THEN 'assembly'
                WHEN 'debug'         THEN 'debug'
                WHEN 'terminé'       THEN 'done'
                WHEN 'archivé'       THEN 'archived'
                ELSE status
            END
        """)
        
        db.commit()
        logger.info("[DB] Migration v3.2 : %d projet(s) migrés vers slugs anglais", fr_statuts)

    # Index sur les colonnes fréquemment filtrées (audit priorité 1)
    db.execute("CREATE INDEX IF NOT EXISTS idx_comp_category     ON components(category)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_comp_location     ON components(location)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_comp_manufacturer ON components(manufacturer)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_comp_lcsc         ON components(lcsc_part_number)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_movements_comp    ON stock_movements(component_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_movements_created ON stock_movements(created_at)")
    db.commit()