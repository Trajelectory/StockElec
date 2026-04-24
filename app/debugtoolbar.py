"""
debugtoolbar.py — Debug toolbar style CakePHP pour StockEleK.

Collecte par requête HTTP :
  - Toutes les requêtes SQL avec durée et nombre de résultats
  - Temps total de la requête HTTP
  - Informations sur la requête (route, méthode, args, form)
  - Logs générés pendant le traitement
  - Variables de session

Activation : Settings → Mode debug (stocké en base via SettingsModel).
N'est JAMAIS injecté sur les routes /api/* et /kicad/* (réponses JSON).
"""

import time
import threading
import logging
import sqlite3
from flask import g, request

logger = logging.getLogger(__name__)

# ── Stockage thread-local des données de la requête courante ─────────
_local = threading.local()


def get_collector():
    """Retourne le collecteur de la requête courante (thread-safe)."""
    if not hasattr(_local, "collector"):
        _local.collector = None
    return _local.collector


def start_collection():
    """Démarre la collecte pour la requête courante."""
    _local.collector = {
        "start":   time.perf_counter(),
        "queries": [],
        "logs":    [],
    }


def stop_collection() -> dict | None:
    """Arrête la collecte et retourne les données."""
    c = get_collector()
    if c is None:
        return None
    c["duration_ms"] = round((time.perf_counter() - c["start"]) * 1000, 2)
    _local.collector = None
    return c


def record_query(sql: str, params, duration_ms: float, rowcount: int):
    """Enregistre une requête SQL dans le collecteur courant."""
    c = get_collector()
    if c is None:
        return
    # Nettoyer le SQL — supprimer indentations excessives
    sql_clean = " ".join(sql.split())
    c["queries"].append({
        "sql":         sql_clean,
        "params":      str(params)[:200] if params else "",
        "duration_ms": round(duration_ms, 3),
        "rowcount":    rowcount,
        "slow":        duration_ms > 50,  # > 50ms = lent
    })


# ── Handler de log pour capturer les messages pendant la requête ─────

class _RequestLogHandler(logging.Handler):
    """Handler qui copie les logs dans le collecteur de la requête courante."""

    def emit(self, record):
        c = get_collector()
        if c is None:
            return
        c["logs"].append({
            "level":   record.levelname,
            "name":    record.name.replace("app.", ""),
            "message": self.format(record)[:300],
            "slow":    record.levelname in ("WARNING", "ERROR", "CRITICAL"),
        })


_log_handler = _RequestLogHandler()
_log_handler.setLevel(logging.DEBUG)
_log_handler.setFormatter(logging.Formatter("%(message)s"))


# ── Instrumentation de sqlite3 ───────────────────────────────────────

class _InstrumentedConnection:
    """Wrapper autour de sqlite3.Connection qui enregistre les requêtes."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def execute(self, sql: str, params=None):
        t0 = time.perf_counter()
        try:
            if params is not None:
                cursor = self._conn.execute(sql, params)
            else:
                cursor = self._conn.execute(sql)
            duration = (time.perf_counter() - t0) * 1000
            record_query(sql, params, duration, cursor.rowcount)
            return cursor
        except Exception:
            duration = (time.perf_counter() - t0) * 1000
            record_query(sql, params, duration, -1)
            raise

    def executescript(self, sql: str):
        return self._conn.executescript(sql)

    def executemany(self, sql: str, params):
        t0 = time.perf_counter()
        cursor = self._conn.executemany(sql, params)
        duration = (time.perf_counter() - t0) * 1000
        record_query(sql, params, duration, cursor.rowcount)
        return cursor

    def commit(self):   return self._conn.commit()
    def rollback(self): return self._conn.rollback()
    def close(self):    return self._conn.close()

    # Déléguer tous les autres attributs à la connexion réelle
    def __getattr__(self, name):
        return getattr(self._conn, name)


def wrap_db(conn: sqlite3.Connection) -> _InstrumentedConnection:
    """Enveloppe une connexion SQLite pour instrumenter les requêtes."""
    return _InstrumentedConnection(conn)


# ── Rendu HTML de la toolbar ─────────────────────────────────────────

def render_toolbar(data: dict) -> str:
    """Génère le HTML de la toolbar à injecter en bas de page."""
    from flask import request as req

    queries    = data.get("queries", [])
    logs       = data.get("logs", [])
    n_queries  = len(queries)
    total_sql  = round(sum(q["duration_ms"] for q in queries), 2)
    n_slow     = sum(1 for q in queries if q["slow"])
    n_warnings = sum(1 for l in logs if l["slow"])
    page_ms    = data.get("duration_ms", 0)

    # Couleurs selon performance
    sql_color  = "#ef4444" if n_slow else ("#f59e0b" if total_sql > 100 else "#22c55e")
    time_color = "#ef4444" if page_ms > 500 else ("#f59e0b" if page_ms > 200 else "#22c55e")
    log_color  = "#ef4444" if n_warnings else ("#f59e0b" if logs else "#94a3b8")

    # ── Panneau requêtes SQL ─────────────────────────────────────────
    queries_html = ""
    for i, q in enumerate(queries):
        row_bg  = "#0f172a" if i % 2 == 0 else "#1e293b"
        slow_badge = '<span style="background:#7f1d1d;color:#fca5a5;font-size:10px;padding:1px 5px;border-radius:3px;margin-left:6px">SLOW</span>' if q["slow"] else ""
        queries_html += f"""
        <tr style="background:{row_bg}">
            <td style="padding:5px 8px;color:#94a3b8;font-size:11px;white-space:nowrap">{q['duration_ms']:.1f} ms</td>
            <td style="padding:5px 8px;font-family:monospace;font-size:11px;color:#e2e8f0;word-break:break-all">
                {_escape(q['sql'])}{slow_badge}
                {'<div style="color:#64748b;font-size:10px;margin-top:2px">' + _escape(q['params']) + '</div>' if q['params'] else ''}
            </td>
        </tr>"""

    # ── Panneau logs ─────────────────────────────────────────────────
    logs_html = ""
    level_colors = {
        "DEBUG":    "#64748b",
        "INFO":     "#38bdf8",
        "WARNING":  "#fbbf24",
        "ERROR":    "#f87171",
        "CRITICAL": "#ef4444",
    }
    for l in logs:
        lc = level_colors.get(l["level"], "#94a3b8")
        logs_html += f"""
        <div style="padding:4px 8px;border-bottom:1px solid #1e293b;font-size:11px">
            <span style="color:{lc};font-weight:600;margin-right:6px">{l['level']}</span>
            <span style="color:#64748b;margin-right:6px">{_escape(l['name'])}</span>
            <span style="color:#cbd5e1">{_escape(l['message'])}</span>
        </div>"""

    # ── Panneau request ──────────────────────────────────────────────
    def _kv(items):
        if not items:
            return '<div style="color:#475569;font-size:11px">—</div>'
        return "".join(
            f'<div style="padding:2px 0;border-bottom:1px solid #1a2030">'
            f'<span style="color:#64748b">{_escape(str(k))}</span>'
            f'<span style="color:#475569"> : </span>'
            f'<span style="color:#e2e8f0">{_escape(str(v)[:200])}</span></div>'
            for k, v in items
        )

    args_html  = _kv(list(req.args.items()))
    form_html  = _kv(list(req.form.items()))

    # Headers HTTP utiles
    useful_headers = ["Content-Type", "Accept", "Referer", "X-Requested-With",
                      "User-Agent", "Accept-Language", "Origin"]
    headers_html = _kv([
        (k, req.headers.get(k))
        for k in useful_headers
        if req.headers.get(k)
    ])

    session_html = '<div style="color:#475569;font-size:11px">—</div>'
    try:
        from flask import session
        items = [(k, v) for k, v in session.items() if not str(k).startswith("_")]
        if items:
            session_html = _kv(items)
    except Exception:
        pass

    toolbar = f"""
<div id="sk-debugbar" style="
    position:fixed;bottom:0;left:0;right:0;z-index:99999;
    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',monospace;
    font-size:12px;line-height:1.4;
    box-shadow:0 -2px 12px rgba(0,0,0,.5)">

    <!-- ── Barre principale ── -->
    <div id="sk-debugbar-bar" style="
        background:#0f172a;border-top:2px solid #7c3aed;
        display:flex;align-items:center;gap:0;height:32px;
        user-select:none">

        <!-- Logo -->
        <div style="padding:0 10px;color:#7c3aed;font-weight:700;font-size:13px;
                    border-right:1px solid #1e293b;height:100%;display:flex;align-items:center">
            ⚡ Debug
        </div>

        <!-- Onglets -->
        {_tab("sql",     f"🗃 SQL ({n_queries})", sql_color,  n_slow,     True)}
        {_tab("logs",    f"📋 Logs ({len(logs)})", log_color, n_warnings, False)}
        {_tab("request", f"🌐 Requête",            "#94a3b8",  False,      False)}

        <!-- Métriques rapides -->
        <div style="margin-left:auto;display:flex;align-items:center;gap:12px;padding:0 12px">
            <span style="color:{time_color};font-weight:600">{page_ms} ms</span>
            <span style="color:{sql_color}">{n_queries} SQL / {total_sql} ms</span>
            <span style="color:#4ade80;font-size:11px">{req.method} {_escape(req.path)}</span>
            <!-- Bouton fermer -->
            <button onclick="document.getElementById('sk-debugbar').style.display='none'"
                    style="background:none;border:none;color:#64748b;cursor:pointer;font-size:16px;
                           padding:0 4px;line-height:1" title="Fermer">×</button>
        </div>
    </div>

    <!-- ── Panneau SQL ── -->
    <div id="sk-panel-sql" class="sk-panel" style="
        background:#0a0f1e;border-top:1px solid #1e293b;
        max-height:320px;overflow-y:auto;display:none">
        {'<table style="width:100%;border-collapse:collapse"><tbody>' + queries_html + '</tbody></table>' if queries else '<div style="padding:12px;color:#475569">Aucune requête SQL enregistrée.</div>'}
    </div>

    <!-- ── Panneau Logs ── -->
    <div id="sk-panel-logs" class="sk-panel" style="
        background:#0a0f1e;border-top:1px solid #1e293b;
        max-height:320px;overflow-y:auto;display:none">
        {logs_html if logs_html else '<div style="padding:12px;color:#475569">Aucun log enregistré.</div>'}
    </div>

    <!-- ── Panneau Requête ── -->
    <div id="sk-panel-request" class="sk-panel" style="
        background:#0a0f1e;border-top:1px solid #1e293b;
        max-height:320px;overflow-y:auto;display:none">
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:0">
            <div style="padding:10px;border-right:1px solid #1e293b;font-size:11px">
                <div style="color:#7c3aed;font-weight:600;margin-bottom:6px;font-size:10px;text-transform:uppercase;letter-spacing:.05em">Méthode / Route</div>
                <div style="color:#4ade80;font-weight:700;margin-bottom:4px">{req.method}</div>
                <div style="color:#e2e8f0;word-break:break-all">{_escape(req.path)}</div>
                <div style="color:#475569;margin-top:6px;font-size:10px">{_escape(req.remote_addr or '')}</div>
            </div>
            <div style="padding:10px;border-right:1px solid #1e293b;font-size:11px">
                <div style="color:#7c3aed;font-weight:600;margin-bottom:6px;font-size:10px;text-transform:uppercase;letter-spacing:.05em">Query Params</div>
                {args_html}
            </div>
            <div style="padding:10px;border-right:1px solid #1e293b;font-size:11px">
                <div style="color:#7c3aed;font-weight:600;margin-bottom:6px;font-size:10px;text-transform:uppercase;letter-spacing:.05em">Form Data</div>
                {form_html}
            </div>
            <div style="padding:10px;font-size:11px">
                <div style="color:#7c3aed;font-weight:600;margin-bottom:6px;font-size:10px;text-transform:uppercase;letter-spacing:.05em">Headers</div>
                {headers_html}
            </div>
        </div>
        {('<div style="padding:10px;border-top:1px solid #1e293b;font-size:11px"><div style="color:#7c3aed;font-weight:600;margin-bottom:6px;font-size:10px;text-transform:uppercase;letter-spacing:.05em">Session</div>' + session_html + '</div>') if session_html != '<div style="color:#475569;font-size:11px">—</div>' else ''}
    </div>

</div>

<script>
(function() {{
    var _open = null;
    function openPanel(name) {{
        document.querySelectorAll('.sk-panel').forEach(function(p) {{
            p.style.display = 'none';
        }});
        document.querySelectorAll('.sk-tab').forEach(function(t) {{
            t.style.borderBottom = '2px solid transparent';
            t.style.color = t.dataset.color || '#94a3b8';
        }});
        if (_open === name) {{ _open = null; return; }}
        var panel = document.getElementById('sk-panel-' + name);
        var tab   = document.getElementById('sk-tab-' + name);
        if (panel) panel.style.display = 'block';
        if (tab) {{ tab.style.borderBottom = '2px solid #7c3aed'; tab.style.color = '#e2e8f0'; }}
        _open = name;
    }}
    window.skOpenPanel = openPanel;
}})();
</script>
"""
    return toolbar


def _tab(name: str, label: str, color: str, highlight: bool, active: bool) -> str:
    border = "2px solid #7c3aed" if active else "2px solid transparent"
    bg     = "rgba(127,58,237,.1)" if highlight else "transparent"
    return (
        f'<button id="sk-tab-{name}" class="sk-tab" data-color="{color}" '
        f'onclick="skOpenPanel(\'{name}\')" '
        f'style="background:{bg};border:none;border-bottom:{border};'
        f'color:{color};cursor:pointer;height:100%;padding:0 14px;'
        f'font-size:12px;font-family:inherit;white-space:nowrap">'
        f'{label}</button>'
    )


def _escape(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ── Intégration Flask ────────────────────────────────────────────────

def init_toolbar(app):
    """
    Enregistre les hooks Flask pour la debug toolbar.
    À appeler depuis create_app() après init_db().
    """
    # Attacher le handler à la racine pour capturer TOUS les loggers
    # (app.*, werkzeug.*, etc.) — le filtre se fait dans emit()
    root_logger = logging.getLogger()
    if _log_handler not in root_logger.handlers:
        root_logger.addHandler(_log_handler)
    # S'assurer que le niveau root n'est pas trop restrictif
    if root_logger.level == logging.NOTSET or root_logger.level > logging.DEBUG:
        root_logger.setLevel(logging.DEBUG)

    @app.before_request
    def _before():
        # On démarre la collecte AVANT tout appel à get_db()
        # pour que la connexion soit wrappée dès sa création.
        # On vérifie ensuite si le debug est activé et on annule si non.
        start_collection()

        from .models.settings import SettingsModel
        try:
            debug = SettingsModel.get("debug_toolbar", "0")
        except Exception:
            debug = "0"

        # Pas de toolbar sur les routes API/JSON ou les assets statiques
        skip = (
            debug != "1"
            or request.path.startswith("/api/")
            or request.path.startswith("/kicad/")
            or request.path.startswith("/static/")
            or request.path.startswith("/images/")
            or (request.path.startswith("/component/") and request.path.endswith("/image"))
        )
        if skip:
            # Annuler la collecte — vider le collecteur
            stop_collection()
            g._debug_active = False
            return
        g._debug_active = True

    @app.after_request
    def _after(response):
        if not getattr(g, "_debug_active", False):
            return response
        # Seulement sur les réponses HTML
        ct = response.content_type or ""
        if "text/html" not in ct:
            return response
        data = stop_collection()
        if data is None:
            return response
        try:
            toolbar_html = render_toolbar(data)
            body = response.get_data(as_text=True)
            # Injecter juste avant </body>
            if "</body>" in body:
                body = body.replace("</body>", toolbar_html + "\n</body>", 1)
                response.set_data(body)
        except Exception as e:
            logger.debug("Toolbar render error: %s", e)
        return response
