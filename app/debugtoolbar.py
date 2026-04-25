"""
debugtoolbar.py — Debug toolbar complète pour StockEleK v3.

Panneaux :
  ① Timeline  — swimlanes SVG + tableau chronologique
  ② SQL       — coloration, rowcount, copie, N+1, EXPLAIN QUERY PLAN
  ③ Templates — durée, offset, variables
  ④ Logs      — niveaux colorés
  ⑤ Requête   — méthode, route, args, form, headers, session
  ⑥ Config    — Flask, système, env, mémoire, taille réponse
  ⑦ Historique — 10 dernières pages avec comparaison

Extras :
  - Cache settings par requête HTTP (1 SELECT * au lieu de N)
  - Padding body automatique
  - sessionStorage pour mémoriser l'onglet
  - Capture erreurs Flask
  - Badge onglet navigateur si requêtes lentes
  - Console.log des SLOW queries
  - Recherche dans SQL
  - Copier tout le SQL
"""

import time
import threading
import logging
import sqlite3
import os
import sys
import json
import traceback
from collections import deque
from flask import g, request

logger = logging.getLogger(__name__)

_local = threading.local()
_history: deque = deque(maxlen=10)
_history_lock = threading.Lock()


# ── Collecteur par requête ────────────────────────────────────────────
def get_collector():
    if not hasattr(_local, "collector"):
        _local.collector = None
    return _local.collector


# ── Registre global : thread_id → collecteur ─────────────────────────
# Permet aux threads enfants (LED, enrichissement...) de trouver
# le collecteur de leur requête Flask parente.
_collector_registry: dict = {}
_registry_lock = threading.Lock()


def _register_collector(c: dict):
    tid = threading.current_thread().ident
    with _registry_lock:
        _collector_registry[tid] = c


def _unregister_collector():
    tid = threading.current_thread().ident
    with _registry_lock:
        _collector_registry.pop(tid, None)


def _find_collector() -> dict | None:
    """Cherche un collecteur actif — thread courant OU registre global."""
    c = get_collector()
    if c is not None:
        return c
    with _registry_lock:
        if _collector_registry:
            return max(_collector_registry.values(), key=lambda x: x.get("t0", 0))
    return None


def start_collection():
    c = {
        "t0":        time.perf_counter(),
        "queries":   [],
        "templates": [],
        "logs":      [],
        "errors":    [],
        "mem_start": _get_mem_mb(),
    }
    _local.collector = c
    _register_collector(c)


def stop_collection():
    c = get_collector()
    if c is None:
        return None
    c["duration_ms"] = round((time.perf_counter() - c["t0"]) * 1000, 2)
    c["mem_end"]     = _get_mem_mb()
    _local.collector = None
    _unregister_collector()
    return c


def _get_mem_mb():
    try:
        import psutil
        return round(psutil.Process().memory_info().rss / 1024 / 1024, 1)
    except Exception:
        return None


def record_query(sql, params, duration_ms, rowcount, error=False):
    c = get_collector()
    if c is None:
        return
    sql_clean = " ".join(sql.split())
    c["queries"].append({
        "sql":         sql_clean,
        "params":      str(params)[:300] if params else "",
        "duration_ms": round(duration_ms, 3),
        "rowcount":    rowcount,
        "slow":        duration_ms > 50,
        "error":       error,
        "t_offset":    round((time.perf_counter() - c["t0"]) * 1000, 2),
        "plan":        None,  # rempli lazily si l'utilisateur clique
    })


def record_template(name, duration_ms, context_keys, t_offset):
    c = get_collector()
    if c is None:
        return
    c["templates"].append({
        "name":         name,
        "duration_ms":  round(duration_ms, 3),
        "context_keys": context_keys,
        "t_offset":     round(t_offset, 2),
    })


def record_error(exc):
    c = get_collector()
    if c is None:
        return
    c["errors"].append({
        "type":    type(exc).__name__,
        "message": str(exc)[:500],
        "tb":      traceback.format_exc()[:2000],
    })


# ── Logging handler ───────────────────────────────────────────────────
class _RequestLogHandler(logging.Handler):
    def emit(self, record):
        c = get_collector()
        if c is None:
            return
        try:
            t_offset = round((time.perf_counter() - c["t0"]) * 1000, 2)
        except Exception:
            t_offset = 0
        c["logs"].append({
            "level":    record.levelname,
            "name":     record.name.replace("app.", ""),
            "message":  self.format(record)[:400],
            "t_offset": t_offset,
        })


_log_handler = _RequestLogHandler()
_log_handler.setLevel(logging.DEBUG)
_log_handler.setFormatter(logging.Formatter("%(message)s"))


# ── Instrumentation sqlite3 ───────────────────────────────────────────
class _InstrumentedConnection:
    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        t0 = time.perf_counter()
        err = False
        cursor = None
        try:
            cursor = self._conn.execute(sql, params) if params is not None else self._conn.execute(sql)
            return cursor
        except Exception:
            err = True
            raise
        finally:
            dur = (time.perf_counter() - t0) * 1000
            rc = cursor.rowcount if cursor is not None else -1
            record_query(sql, params, dur, rc, err)

    def explain(self, sql, params=None):
        """Retourne le plan d'exécution SQLite pour une requête."""
        try:
            q = f"EXPLAIN QUERY PLAN {sql}"
            rows = self._conn.execute(q, params or []).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def executemany(self, sql, params):
        t0 = time.perf_counter()
        cursor = self._conn.executemany(sql, params)
        record_query(sql, None, (time.perf_counter() - t0) * 1000, cursor.rowcount)
        return cursor

    def executescript(self, sql):   return self._conn.executescript(sql)
    def commit(self):               return self._conn.commit()
    def rollback(self):             return self._conn.rollback()
    def close(self):                return self._conn.close()
    def __getattr__(self, name):    return getattr(self._conn, name)


def wrap_db(conn):
    return _InstrumentedConnection(conn)


# ── Helpers HTML ──────────────────────────────────────────────────────
def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _kv(items, empty="—"):
    if not items:
        return f'<div style="color:#475569;font-size:11px;padding:3px 0">{empty}</div>'
    rows = "".join(
        f'<tr>'
        f'<td style="color:#64748b;padding:3px 8px 3px 0;white-space:nowrap;vertical-align:top;font-size:11px">{_esc(str(k))}</td>'
        f'<td style="color:#e2e8f0;padding:3px 0;word-break:break-all;font-size:11px">{_esc(str(v)[:300])}</td>'
        f'</tr>'
        for k, v in items
    )
    return f'<table style="width:100%;border-collapse:collapse"><tbody>{rows}</tbody></table>'


def _tab(name, label, color, highlight):
    bg = "rgba(245,158,11,.1)" if highlight else "transparent"
    return (
        f'<button id="sk-tab-{name}" class="sk-tab" data-color="{color}" '
        f'onclick="skOpen(\'{name}\')" style="color:{color};background:{bg}">'
        f'{_esc(label)}</button>'
    )


# ── Coloration SQL ────────────────────────────────────────────────────
_SQL_KW = [
    "SELECT","FROM","WHERE","AND","OR","NOT","IN","IS","NULL",
    "JOIN","LEFT","RIGHT","INNER","OUTER","ON","AS",
    "INSERT","INTO","VALUES","UPDATE","SET","DELETE",
    "CREATE","TABLE","IF","EXISTS","INDEX","DROP","ALTER",
    "ORDER","BY","GROUP","HAVING","LIMIT","OFFSET",
    "CASE","WHEN","THEN","ELSE","END","DISTINCT","COUNT",
    "SUM","MAX","MIN","AVG","PRAGMA","WITH","COALESCE","NULLS","LAST",
]

def _sql_highlight(sql):
    import re
    escaped = _esc(sql)
    pattern = r'\b(' + '|'.join(_SQL_KW) + r')\b'
    highlighted = re.sub(
        pattern,
        r'<span style="color:#38bdf8;font-weight:600">\1</span>',
        escaped, flags=re.IGNORECASE
    )
    highlighted = re.sub(r"'([^']*)'",
        r'<span style="color:#86efac">&#39;\1&#39;</span>', highlighted)
    highlighted = re.sub(r'\b(\d+(?:\.\d+)?)\b',
        r'<span style="color:#fdba74">\1</span>', highlighted)
    highlighted = highlighted.replace('?',
        '<span style="color:#c084fc">?</span>')
    return highlighted


# ── Timeline swimlanes ────────────────────────────────────────────────
def _build_timeline(queries, templates, page_ms):
    C_SQL="#3b82f6"; C_TPL="#8b5cf6"; C_ERR="#ef4444"; C_WARN="#f59e0b"; C_OK="#22c55e"

    total_sql = round(sum(q["duration_ms"] for q in queries), 2)
    total_tpl = round(sum(t["duration_ms"] for t in templates), 2)
    python_ms = round(max(0, page_ms - total_sql - total_tpl), 2)

    events = []
    for q in queries:
        events.append({"t": max(0, q["t_offset"]-q["duration_ms"]), "dur": q["duration_ms"],
                        "type":"sql","label":q["sql"][:65],"slow":q["slow"],"error":q["error"],"rc":q["rowcount"]})
    for t in templates:
        events.append({"t": max(0, t["t_offset"]-t["duration_ms"]), "dur": t["duration_ms"],
                        "type":"tpl","label":t["name"],"slow":False,"error":False,"rc":-1})
    events.sort(key=lambda e: e["t"])

    if not events or page_ms <= 0:
        return '<div style="padding:12px;color:#475569;font-size:11px">Aucun événement.</div>'

    W = 860
    lanes: list[float] = []
    def get_lane(start, end):
        px_s = start/page_ms*W; px_e = end/page_ms*W
        for i,le in enumerate(lanes):
            if px_s >= le+2: lanes[i]=px_e; return i
        lanes.append(px_e); return len(lanes)-1

    lane_map = [get_lane(e["t"], e["t"]+e["dur"]) for e in events]
    n_lanes = max(lane_map)+1 if lane_map else 1
    BAR_H=14; GAP=2; HDR=20
    svg_h = HDR + n_lanes*(BAR_H+GAP) + 8

    ticks = ""
    for pct in [0,25,50,75,100]:
        x=pct/100*W; ms_v=round(pct/100*page_ms)
        ticks += (f'<line x1="{x:.0f}" y1="{HDR}" x2="{x:.0f}" y2="{svg_h}" stroke="#1e293b" stroke-width="1"/>'
                  f'<text x="{x+2:.0f}" y="13" font-size="9" fill="#334155">{ms_v}ms</text>')

    bars = f'<rect x="0" y="{HDR}" width="{W}" height="{svg_h-HDR}" fill="#0a0f1e"/>'
    clips = "".join(f'<clipPath id="skc{i}"><rect x="0" y="{HDR+i*(BAR_H+GAP)}" width="{W}" height="{BAR_H}"/></clipPath>' for i in range(n_lanes))

    for e,lane in zip(events,lane_map):
        px = e["t"]/page_ms*W; pw = max(3,e["dur"]/page_ms*W)
        py = HDR+lane*(BAR_H+GAP)
        c = C_ERR if e["error"] else (C_WARN if e["slow"] else (C_SQL if e["type"]=="sql" else C_TPL))
        bars += f'<rect x="{px:.1f}" y="{py}" width="{pw:.1f}" height="{BAR_H}" rx="2" fill="{c}" opacity=".85"/>'
        if pw > 40:
            lbl = _esc(e["label"][:int(pw/6)])
            bars += f'<text x="{px+3:.1f}" y="{py+10}" font-size="9" fill="#fff" clip-path="url(#skc{lane})">{lbl}</text>'

    svg = (f'<svg width="100%" viewBox="0 0 {W} {svg_h}" xmlns="http://www.w3.org/2000/svg" style="display:block;min-width:400px">'
           f'<defs>{clips}</defs>{ticks}{bars}</svg>')

    legend = (f'<div style="display:flex;gap:16px;padding:6px 12px;border-bottom:1px solid #1e293b;font-size:11px;flex-wrap:wrap">'
              f'<span><i style="display:inline-block;width:10px;height:10px;background:{C_SQL};border-radius:2px;vertical-align:middle;margin-right:4px"></i>SQL : {total_sql}ms ({len(queries)})</span>'
              f'<span><i style="display:inline-block;width:10px;height:10px;background:{C_TPL};border-radius:2px;vertical-align:middle;margin-right:4px"></i>Templates : {total_tpl}ms ({len(templates)})</span>'
              f'<span><i style="display:inline-block;width:10px;height:10px;background:#1e293b;border:1px solid #334155;border-radius:2px;vertical-align:middle;margin-right:4px"></i>Python : {python_ms}ms</span>'
              f'<span style="margin-left:auto;color:#f59e0b;font-weight:600">Total : {page_ms}ms</span>'
              f'</div>')

    tbl = "".join(
        f'<tr style="border-bottom:1px solid #1a2030">'
        f'<td style="padding:3px 8px;color:#64748b;white-space:nowrap;font-size:11px">+{e["t"]:.1f}ms</td>'
        f'<td style="padding:3px 8px;white-space:nowrap">'
        f'<span style="background:{"#3b82f6" if e["type"]=="sql" else "#8b5cf6"};color:#fff;font-size:9px;padding:1px 5px;border-radius:2px">{"SQL" if e["type"]=="sql" else "TPL"}</span></td>'
        f'<td style="padding:3px 8px;white-space:nowrap;font-size:11px">'
        f'<span style="color:#f59e0b">{e["dur"]:.1f}ms</span>'
        f'{"<span style=color:#ef4444> ⚠ SLOW</span>" if e["slow"] else ""}'
        f'{"<span style=color:#ef4444> ✗ ERR</span>" if e["error"] else ""}'
        f'{"<span style=color:#475569;font-size:10px> → "+str(e["rc"])+" lignes</span>" if e["rc"]>=0 else ""}</td>'
        f'<td style="padding:3px 8px;color:#94a3b8;font-family:monospace;font-size:10px">{_esc(e["label"])}</td>'
        f'</tr>'
        for e in events
    )
    table = (f'<table style="width:100%;border-collapse:collapse">'
             f'<thead><tr>'
             f'<th style="padding:4px 8px;color:#334155;text-align:left;font-size:11px;border-bottom:1px solid #1e293b;white-space:nowrap">Offset</th>'
             f'<th style="padding:4px 8px;color:#334155;text-align:left;font-size:11px;border-bottom:1px solid #1e293b">Type</th>'
             f'<th style="padding:4px 8px;color:#334155;text-align:left;font-size:11px;border-bottom:1px solid #1e293b">Durée</th>'
             f'<th style="padding:4px 8px;color:#334155;text-align:left;font-size:11px;border-bottom:1px solid #1e293b">Détail</th>'
             f'</tr></thead><tbody>{tbl}</tbody></table>')

    return legend + f'<div style="padding:8px 12px 0;overflow-x:auto">{svg}</div>' + table


# ── Panneau SQL avec recherche + copie globale + EXPLAIN ──────────────
def _build_sql_panel(queries, sql_counts, n_dup):
    C_ERR="#ef4444"; C_WARN="#f59e0b"; C_OK="#22c55e"; C_MUTED="#475569"

    dup_warn = ""
    if n_dup:
        dup_items = sorted([(s,c) for s,c in sql_counts.items() if c>1], key=lambda x:-x[1])
        dup_rows = "".join(
            f'<div style="padding:3px 8px;border-bottom:1px solid #2a1f00;font-size:11px;display:flex;gap:8px">'
            f'<span style="color:#f59e0b;font-weight:700;flex-shrink:0">×{c}</span>'
            f'<span style="color:#94a3b8;font-family:monospace">{_esc(s[:90])}</span></div>'
            for s,c in dup_items
        )
        dup_warn = (f'<div style="background:#1c1400;border-bottom:2px solid #2a1f00">'
                    f'<div style="padding:5px 8px;color:#f59e0b;font-size:11px;font-weight:700">'
                    f'⚠ {n_dup} requête(s) dupliquée(s) — N+1 probable</div>{dup_rows}</div>')

    if not queries:
        return dup_warn + '<div style="padding:12px;color:#475569;font-size:11px">Aucune requête SQL.</div>'

    # Barre d'outils SQL
    # Stocker le SQL dans un data-attribute pour éviter les backticks dans les f-strings
    toolbar = (
        f'<div style="padding:5px 8px;border-bottom:1px solid #1e293b;display:flex;gap:8px;align-items:center;background:#0d1117">'
        f'<input type="text" id="sk-sql-search" placeholder="Filtrer les requêtes…" oninput="skFilterSQL(this.value)"'
        f' style="background:#1e293b;border:1px solid #334155;color:#e2e8f0;font-size:11px;padding:3px 8px;border-radius:3px;flex:1;font-family:monospace"/>'
        f'<button id="sk-copy-all-btn" onclick="skCopyAllSQL(this)"'
        f' style="background:#1e293b;border:1px solid #334155;color:#94a3b8;font-size:10px;padding:3px 10px;border-radius:3px;cursor:pointer;white-space:nowrap">Copier tout le SQL</button>'
        f'<span style="color:#475569;font-size:10px">{len(queries)} requêtes</span>'
        f'</div>'
    )

    rows = ""
    for i, q in enumerate(queries):
        bg = "#0d1117" if i%2==0 else "#0f1923"
        badges = ""
        if q["slow"]:  badges += '<span style="background:#7f1d1d;color:#fca5a5;font-size:9px;padding:1px 5px;border-radius:2px;margin-left:5px">SLOW</span>'
        if q["error"]: badges += '<span style="background:#450a0a;color:#f87171;font-size:9px;padding:1px 5px;border-radius:2px;margin-left:5px">ERR</span>'
        dc = sql_counts.get(q["sql"][:120], 1)
        if dc > 1: badges += f'<span style="background:#1c1917;color:#f59e0b;font-size:9px;padding:1px 5px;border-radius:2px;margin-left:5px">×{dc}</span>'

        rc_color = C_WARN if q["rowcount"]==0 else C_MUTED
        rc_html = f'<span style="color:{rc_color};font-size:10px;margin-left:5px">{q["rowcount"]} lignes</span>' if q["rowcount"]>=0 else ""

        params_div = (f'<div style="color:#475569;font-size:10px;margin-top:3px;font-family:monospace">{_esc(q["params"])}</div>'
                      if q["params"] else "")

        # SQL dans data-attribute — évite les problèmes de quotes/backticks
        sql_data = _esc(q["sql"])
        copy_btn = (f'<button onclick="skCopySingle(this)"'
                    f' data-sql="{sql_data}"'
                    f' style="background:#1e293b;border:1px solid #334155;color:#64748b;font-size:9px;'
                    f'padding:1px 6px;border-radius:2px;cursor:pointer;margin-left:6px;vertical-align:middle">copy</button>')

        # EXPLAIN QUERY PLAN inline
        explain_id = f"sk-explain-{i}"
        explain_btn = (f'<button onclick="skExplain(this,\'{explain_id}\')"'
                       f' data-sql="{sql_data}"'
                       f' style="background:#0d1e35;border:1px solid #1a3055;color:#3b82f6;font-size:9px;'
                       f'padding:1px 6px;border-radius:2px;cursor:pointer;margin-left:4px;vertical-align:middle">EXPLAIN</button>')
        explain_div = f'<div id="{explain_id}" style="display:none;margin-top:5px;background:#050a14;border:1px solid #1e293b;border-radius:3px;padding:5px 8px;font-family:monospace;font-size:10px;color:#64748b;white-space:pre"></div>'

        rows += (
            f'<tr class="sk-sql-row" style="background:{bg}">'
            f'<td style="padding:4px 8px;color:#64748b;font-size:11px;white-space:nowrap;border-right:1px solid #1e293b;vertical-align:top">{q["duration_ms"]:.1f}ms</td>'
            f'<td style="padding:4px 8px;color:#475569;font-size:10px;white-space:nowrap;border-right:1px solid #1e293b;vertical-align:top">+{q["t_offset"]}ms</td>'
            f'<td style="padding:4px 8px;font-family:monospace;font-size:11px;word-break:break-all">'
            f'{_sql_highlight(q["sql"])}{badges}{rc_html}{copy_btn}{explain_btn}{params_div}{explain_div}'
            f'</td></tr>'
        )

    return dup_warn + toolbar + f'<table id="sk-sql-table" style="width:100%;border-collapse:collapse"><tbody>{rows}</tbody></table>'


# ── Historique inter-pages ────────────────────────────────────────────
def _build_history_panel():
    with _history_lock:
        hist = list(_history)
    if not hist:
        return '<div style="padding:12px;color:#475569;font-size:11px">Navigue entre quelques pages pour voir l\'historique.</div>'

    rows = ""
    prev_ms = None
    for entry in reversed(hist):
        t_color = "#ef4444" if entry["ms"]>500 else ("#f59e0b" if entry["ms"]>200 else "#22c55e")
        diff_html = ""
        if prev_ms is not None:
            diff = entry["ms"] - prev_ms
            diff_color = "#ef4444" if diff>50 else ("#22c55e" if diff<-50 else "#64748b")
            sign = "+" if diff>=0 else ""
            diff_html = f'<span style="color:{diff_color};font-size:10px;margin-left:4px">({sign}{diff:.0f}ms)</span>'
        prev_ms = entry["ms"]

        # Appels HTTP sortants pour les routes collect-only (ex: /api/led/)
        http_out_sub = ""
        for h in entry.get("http_out", []):
            DEST_C = {"ESP32":"#f59e0b","LCSC":"#22c55e","Mouser":"#3b82f6",
                      "DigiKey":"#ef4444","EasyEDA":"#8b5cf6","Externe":"#64748b"}
            dc = DEST_C.get(h.get("dest","Externe"),"#64748b")
            sc = "#22c55e" if 200<=(h.get("status") or 0)<300 else "#ef4444"
            http_out_sub += (
                f'<span style="background:{dc};color:#fff;font-size:8px;padding:0 4px;border-radius:2px;margin-right:3px">{h.get("dest","?")}</span>'
                f'<span style="color:{sc};font-size:9px">{h.get("status",0)}</span>'
                f'<span style="color:#475569;font-size:9px;margin:0 4px">→</span>'
                f'<span style="color:#94a3b8;font-size:9px;font-family:monospace">{_esc(h.get("url","")[:40])}</span>  '
            )

        rows += (
            f'<tr style="border-bottom:1px solid #1a2030">'
            f'<td style="padding:4px 8px;font-size:11px;color:#64748b;white-space:nowrap">{entry["time"]}</td>'
            f'<td style="padding:4px 8px;white-space:nowrap">'
            f'<span style="background:#064e3b;color:#34d399;font-size:9px;padding:1px 5px;border-radius:2px">{entry["method"]}</span></td>'
            f'<td style="padding:4px 8px;font-size:11px;color:#e2e8f0;font-family:monospace">'
            f'{_esc(entry["path"])}'
            + (f'<div style="margin-top:2px">{http_out_sub}</div>' if http_out_sub else "")
            + f'</td>'
            f'<td style="padding:4px 8px;font-size:11px;white-space:nowrap">'
            f'<span style="color:{t_color};font-weight:600">{entry["ms"]}ms</span>{diff_html}</td>'
            f'<td style="padding:4px 8px;font-size:11px;color:#64748b;white-space:nowrap">{entry["n_sql"]} SQL</td>'
            f'<td style="padding:4px 8px;font-size:11px;color:#64748b;white-space:nowrap">{entry["status"]}</td>'
            f'<td style="padding:4px 8px;font-size:11px;color:#64748b;white-space:nowrap">{entry.get("size_kb","?")} Ko</td>'
            f'</tr>'
        )

    return (
        f'<table style="width:100%;border-collapse:collapse">'
        f'<thead><tr>'
        + "".join(f'<th style="padding:4px 8px;color:#334155;text-align:left;font-size:11px;border-bottom:1px solid #1e293b;white-space:nowrap">{h}</th>'
                  for h in ["Heure","Mét.","Route","Temps","SQL","Status","Taille"])
        + f'</tr></thead><tbody>{rows}</tbody></table>'
    )


# ── Rendu principal ───────────────────────────────────────────────────

def _build_http_panel(data):
    """Panneau HTTP : requêtes entrantes enrichies + appels sortants."""
    from flask import request as req

    c_ajax = "#06b6d4"; c_esp = "#f59e0b"; c_lcsc = "#22c55e"
    c_ext = "#8b5cf6"; c_err = "#ef4444"

    DEST_COLORS = {
        "ESP32":   "#f59e0b", "LCSC":    "#22c55e", "Mouser":  "#3b82f6",
        "DigiKey": "#ef4444", "EasyEDA": "#8b5cf6", "JLCPCB":  "#06b6d4",
        "Externe": "#64748b",
    }
    METHOD_COLORS = {
        "GET":    "#22c55e", "POST":   "#3b82f6", "PUT":    "#f59e0b",
        "DELETE": "#ef4444", "PATCH":  "#8b5cf6",
    }

    # ── Requête entrante ──────────────────────────────────────────────
    from flask import request as req
    ajax_badge = ""
    if data.get("is_ajax"):
        ajax_badge = '<span style="background:#0e7490;color:#a5f3fc;font-size:9px;padding:1px 6px;border-radius:2px;margin-left:6px">AJAX</span>'

    mc = METHOD_COLORS.get(req.method, "#94a3b8")
    incoming = (
        f'<div style="padding:8px 12px;border-bottom:2px solid #1e293b">'
        f'<div style="color:#7c3aed;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px">Requête entrante</div>'
        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">'
        f'<span style="background:{mc};color:#fff;font-size:11px;font-weight:700;padding:2px 10px;border-radius:4px">{req.method}</span>'
        f'<span style="color:#f59e0b;font-size:12px;font-family:monospace">{_esc(req.path)}</span>'
        f'{ajax_badge}</div>'
    )

    # Form data
    if req.form:
        form_rows = "".join(
            f'<tr><td style="color:#64748b;padding:2px 8px 2px 0;white-space:nowrap;font-size:11px">{_esc(k)}</td>'
            f'<td style="color:#e2e8f0;padding:2px 0;word-break:break-all;font-size:11px">{_esc(str(v)[:200])}</td></tr>'
            for k, v in req.form.items()
        )
        incoming += (f'<div style="color:#64748b;font-size:10px;margin-bottom:4px">Form data ({len(req.form)} champ(s)) :</div>'
                     f'<table style="width:100%;border-collapse:collapse;margin-bottom:8px"><tbody>{form_rows}</tbody></table>')

    # JSON body
    json_body = data.get("json_body")
    if json_body:
        incoming += (f'<div style="color:#64748b;font-size:10px;margin-bottom:4px">JSON body :</div>'
                     f'<pre style="background:#050a14;color:#86efac;font-size:10px;padding:6px 8px;'
                     f'border-radius:3px;overflow-x:auto;margin:0 0 8px;white-space:pre-wrap">{_esc(json_body)}</pre>')

    # Fichiers uploadés
    uploads = data.get("uploads", [])
    if uploads:
        for u in uploads:
            incoming += (
                f'<div style="background:#0d1520;border:1px solid #1a2535;border-radius:4px;'
                f'padding:5px 8px;margin-bottom:4px;font-size:11px;display:flex;gap:10px;align-items:center">'
                f'<span style="color:#8b5cf6">📎</span>'
                f'<span style="color:#e2e8f0">{_esc(u["filename"])}</span>'
                f'<span style="color:#64748b">{_esc(u["mimetype"])}</span>'
                f'<span style="color:#475569;font-size:10px;font-family:monospace">magic: {u["magic"]}</span>'
                f'</div>'
            )

    incoming += '</div>'

    # ── Appels HTTP sortants ──────────────────────────────────────────
    http_out = data.get("http_out", [])
    if not http_out:
        outgoing = '<div style="padding:10px 12px;color:#475569;font-size:11px">Aucun appel HTTP sortant sur cette page.</div>'
    else:
        out_rows = ""
        for i, h in enumerate(http_out):
            bg = "#0d1117" if i%2==0 else "#0f1923"
            dest_color = DEST_COLORS.get(h["dest"], "#64748b")
            mc2 = METHOD_COLORS.get(h["method"], "#94a3b8")
            st_color = "#22c55e" if 200<=h["status"]<300 else ("#f59e0b" if h["status"]<500 else "#ef4444")
            err_div = (f'<div style="color:#ef4444;font-size:10px;margin-top:3px">{_esc(h["error"])}</div>'
                      if h["error"] else "")
            req_div = (f'<div style="color:#475569;font-size:10px;margin-top:3px;font-family:monospace;word-break:break-all">'
                       f'→ {_esc(h["req_body"])}</div>' if h["req_body"] else "")
            resp_div = (f'<div style="color:#64748b;font-size:10px;margin-top:2px;font-family:monospace;word-break:break-all">'
                        f'← {_esc(h["resp_preview"])}</div>' if h["resp_preview"] else "")
            out_rows += (
                f'<tr style="background:{bg}">'
                f'<td style="padding:4px 8px;white-space:nowrap;border-right:1px solid #1e293b;vertical-align:top">'
                f'<span style="background:{dest_color};color:#fff;font-size:9px;padding:1px 5px;border-radius:2px">{h["dest"]}</span></td>'
                f'<td style="padding:4px 8px;white-space:nowrap;border-right:1px solid #1e293b;vertical-align:top">'
                f'<span style="color:{mc2};font-size:10px;font-weight:600">{h["method"]}</span></td>'
                f'<td style="padding:4px 8px;white-space:nowrap;border-right:1px solid #1e293b;vertical-align:top">'
                f'<span style="color:{st_color};font-weight:600;font-size:11px">{h["status"] or "ERR"}</span></td>'
                f'<td style="padding:4px 8px;color:#64748b;font-size:10px;white-space:nowrap;border-right:1px solid #1e293b;vertical-align:top">'
                f'{h["duration_ms"]:.0f}ms</td>'
                f'<td style="padding:4px 8px;font-size:11px;font-family:monospace;color:#e2e8f0;word-break:break-all">'
                f'{_esc(h["url"])}{req_div}{resp_div}{err_div}</td>'
                f'</tr>'
            )
        outgoing = (
            f'<div style="padding:5px 12px;border-bottom:1px solid #1e293b;color:#7c3aed;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em">'
            f'Appels HTTP sortants ({len(http_out)})</div>'
            f'<table style="width:100%;border-collapse:collapse">'
            f'<thead><tr>'
            + "".join(f'<th style="padding:3px 8px;color:#334155;text-align:left;font-size:10px;border-bottom:1px solid #1e293b;white-space:nowrap">{h}</th>'
                      for h in ["Dest","Méth.","Status","Durée","URL / Payload / Réponse"])
            + f'</tr></thead><tbody>{out_rows}</tbody></table>'
        )

    return incoming + outgoing


def render_toolbar(data, response_status=200, response_size_kb=0):
    import datetime
    from flask import request as req

    queries   = data.get("queries", [])
    templates = data.get("templates", [])
    logs      = data.get("logs", [])
    errors    = data.get("errors", [])
    page_ms   = data.get("duration_ms", 0)
    mem_start = data.get("mem_start")
    mem_end   = data.get("mem_end")

    http_out   = data.get("http_out", [])
    n_http_out = len(http_out)
    n_queries  = len(queries)
    total_sql  = round(sum(q["duration_ms"] for q in queries), 2)
    n_slow     = sum(1 for q in queries if q["slow"])
    n_warnings = sum(1 for l in logs if l["level"] in ("WARNING","ERROR","CRITICAL"))
    total_tpl  = round(sum(t["duration_ms"] for t in templates), 2)
    n_exc      = len(errors)
    python_ms  = round(max(0, page_ms-total_sql-total_tpl), 2)

    sql_counts = {}
    for q in queries:
        key = q["sql"][:120]
        sql_counts[key] = sql_counts.get(key,0)+1
    n_dup = sum(1 for c in sql_counts.values() if c>1)

    C_OK="#22c55e"; C_WARN="#f59e0b"; C_ERR="#ef4444"; C_MUTED="#475569"; C_ACCENT="#7c3aed"
    C_SQL="#3b82f6"; C_TPL="#8b5cf6"

    sql_color  = C_ERR if (n_slow or n_exc) else (C_WARN if total_sql>100 or n_dup else C_OK)
    time_color = C_ERR if page_ms>500 else (C_WARN if page_ms>200 else C_OK)
    log_color  = C_ERR if n_warnings else (C_WARN if logs else C_MUTED)
    tpl_color  = C_WARN if total_tpl>50 else C_OK

    # Mémoire
    mem_html = ""
    if mem_start is not None and mem_end is not None:
        diff = round(mem_end-mem_start, 1)
        mem_color = C_ERR if diff>5 else (C_WARN if diff>1 else C_MUTED)
        mem_html = (f'<span style="color:{mem_color}" title="Mémoire RSS">'
                    f'{mem_end}Mo ({("+" if diff>=0 else "")}{diff}Mo)</span>')

    with _history_lock:
        _history.append({
            "time":    datetime.datetime.now().strftime("%H:%M:%S"),
            "method":  req.method,
            "path":    req.path,
            "ms":      page_ms,
            "n_sql":   n_queries,
            "status":  str(response_status),
            "size_kb": response_size_kb,
        })

    # Panneaux
    timeline_html = _build_timeline(queries, templates, page_ms)
    sql_panel     = _build_sql_panel(queries, sql_counts, n_dup)
    history_panel = _build_history_panel()

    tpl_rows = "".join(
        f'<tr style="background:{"#0d1117" if i%2==0 else "#0f1923"}">'
        f'<td style="padding:5px 8px;color:#64748b;font-size:11px;white-space:nowrap;border-right:1px solid #1e293b;vertical-align:top">{t["duration_ms"]:.1f}ms</td>'
        f'<td style="padding:5px 8px;color:#475569;font-size:10px;white-space:nowrap;border-right:1px solid #1e293b;vertical-align:top">+{t["t_offset"]}ms</td>'
        f'<td style="padding:5px 8px"><div style="font-family:monospace;font-size:11px;color:#8b5cf6;margin-bottom:5px">{_esc(t["name"])}</div>'
        f'<div style="line-height:2">'
        + " ".join(f'<span style="background:#1e293b;color:#94a3b8;font-size:9px;padding:1px 5px;border-radius:2px;margin:1px;display:inline-block">{_esc(k)}</span>' for k in sorted(t["context_keys"])[:30])
        + f'</div></td></tr>'
        for i,t in enumerate(templates)
    )
    tpl_panel = (f'<table style="width:100%;border-collapse:collapse"><tbody>{tpl_rows}</tbody></table>'
                 if templates else '<div style="padding:12px;color:#475569;font-size:11px">Aucun template rendu.</div>')

    LCOLORS = {"DEBUG":("#64748b","#0f172a"),"INFO":("#38bdf8","#0c1a2e"),
               "WARNING":("#fbbf24","#1a1200"),"ERROR":("#f87171","#1a0000"),"CRITICAL":("#ef4444","#200000")}
    errors_html = "".join(
        f'<div style="padding:8px 12px;border-bottom:1px solid #2a0000;background:#100000">'
        f'<div style="color:#f87171;font-weight:700;font-size:12px;margin-bottom:4px">{_esc(e["type"])}: {_esc(e["message"])}</div>'
        f'<pre style="color:#94a3b8;font-size:10px;overflow-x:auto;margin:0;white-space:pre-wrap;background:#0a0000;padding:6px;border-radius:3px">{_esc(e["tb"])}</pre>'
        f'</div>' for e in errors
    )
    logs_html = "".join(
        f'<div style="padding:4px 8px;border-bottom:1px solid #1e293b;background:{LCOLORS.get(l["level"],("#94a3b8","#0d1117"))[1]};display:grid;grid-template-columns:65px 1fr;gap:8px;align-items:baseline">'
        f'<span style="color:{LCOLORS.get(l["level"],("#94a3b8","#0d1117"))[0]};font-weight:700;font-size:11px">{l["level"]}</span>'
        f'<div><span style="color:#475569;font-size:10px;margin-right:8px">{_esc(l["name"])}</span>'
        f'<span style="color:#cbd5e1;font-size:11px;word-break:break-all">{_esc(l["message"])}</span></div></div>'
        for l in logs
    )
    logs_panel = errors_html + (logs_html or '<div style="padding:12px;color:#475569;font-size:11px">Aucun log.</div>')

    useful_hdrs = ["Content-Type","Accept","Accept-Language","Referer","X-Requested-With","User-Agent","Origin"]
    hdr_items = [(k,req.headers.get(k)) for k in useful_hdrs if req.headers.get(k)]
    sess_items = []
    try:
        from flask import session as _s
        sess_items = [(k,v) for k,v in _s.items() if not str(k).startswith("_")]
    except Exception:
        pass

    req_panel = (
        f'<div style="display:grid;grid-template-columns:1fr 1fr 1fr">'
        f'<div style="padding:10px;border-right:1px solid #1e293b">'
        f'<div style="color:{C_ACCENT};font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px">Requête HTTP</div>'
        f'<div style="margin-bottom:8px"><span style="background:#064e3b;color:#34d399;font-size:13px;font-weight:700;padding:2px 10px;border-radius:4px">{req.method}</span>'
        f'<span style="color:#f59e0b;font-size:11px;margin-left:8px">{_esc(str(req.url_rule or req.path))}</span></div>'
        + _kv([("Path",req.path),("Endpoint",req.endpoint or ""),("View args",str(req.view_args or {})),("IP",req.remote_addr or ""),("Status",str(response_status)),("Taille",f"{response_size_kb} Ko")])
        + f'</div>'
        f'<div style="padding:10px;border-right:1px solid #1e293b">'
        f'<div style="color:{C_ACCENT};font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px">GET / POST</div>'
        + (f'<div style="color:#64748b;font-size:10px;margin-bottom:4px">Query params</div>'+_kv(list(req.args.items())) if req.args else '<div style="color:#475569;font-size:11px">Pas de query params</div>')
        + (f'<div style="color:#64748b;font-size:10px;margin:8px 0 4px">Form data</div>'+_kv(list(req.form.items())) if req.form else '<div style="color:#475569;font-size:11px;margin-top:8px">Pas de form data</div>')
        + f'</div>'
        f'<div style="padding:10px">'
        f'<div style="color:{C_ACCENT};font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px">Headers</div>'
        + _kv(hdr_items)
        + (f'<div style="color:{C_ACCENT};font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;margin:10px 0 6px">Session</div>'+_kv(sess_items) if sess_items else "")
        + f'</div></div>'
    )

    try:
        from flask import current_app as _ca
        flask_cfg = [("ENV",_ca.config.get("ENV","production")),("DEBUG",str(_ca.config.get("DEBUG",False))),
                     ("TESTING",str(_ca.config.get("TESTING",False))),
                     ("MAX_CONTENT_LENGTH",f'{(_ca.config.get("MAX_CONTENT_LENGTH") or 0)//1024//1024} Mo'),
                     ("SECRET_KEY","✓ configurée" if _ca.config.get("SECRET_KEY") else "❌ absente")]
    except Exception:
        flask_cfg = []

    sys_cfg = [("Python",sys.version.split()[0]),("Platform",sys.platform),("PID",str(os.getpid())),
               ("Threads",str(threading.active_count())),("CWD",os.getcwd()[:55])]
    if mem_start is not None:
        sys_cfg.append(("Mémoire RSS",f"{mem_end}Mo (Δ{round(mem_end-mem_start,1):+}Mo)"))
    sys_cfg.append(("Taille réponse",f"{response_size_kb} Ko"))
    env_cfg = [(k,os.environ.get(k,"—")) for k in ["FLASK_ENV","FLASK_DEBUG","PYTHONPATH","PORT"]]

    config_panel = (
        f'<div style="display:grid;grid-template-columns:1fr 1fr 1fr">'
        f'<div style="padding:10px;border-right:1px solid #1e293b">'
        f'<div style="color:{C_ACCENT};font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px">Flask config</div>'+_kv(flask_cfg)+f'</div>'
        f'<div style="padding:10px;border-right:1px solid #1e293b">'
        f'<div style="color:{C_ACCENT};font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px">Système & Perf</div>'+_kv(sys_cfg)+f'</div>'
        f'<div style="padding:10px">'
        f'<div style="color:{C_ACCENT};font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px">Variables env.</div>'+_kv(env_cfg)+f'</div></div>'
    )

    # Slow queries pour console.log
    slow_queries = [{"sql":q["sql"],"ms":q["duration_ms"]} for q in queries if q["slow"]]
    slow_json = json.dumps(slow_queries, ensure_ascii=False)

    # Pré-calculer le panneau HTTP avant la f-string
    # (évite qu'une exception ou des accolades dans le HTML cassent le JS)
    try:
        http_panel_html = _build_http_panel(data)
    except Exception as _e:
        http_panel_html = f'<div style="padding:12px;color:#ef4444;font-size:11px">Erreur panneau HTTP : {_esc(str(_e))}</div>'

    sql_lbl  = f"SQL ({n_queries})"+(f" ⚠{n_slow}" if n_slow else "")+(f" ×{n_dup}" if n_dup else "")
    http_lbl = f"HTTP ({n_http_out})"
    http_color = "#ef4444" if any(h.get("error") for h in http_out) else ("#f59e0b" if any(h.get("status",200)>=400 for h in http_out) else "#06b6d4")
    log_lbl = f"Logs ({len(logs)})"+(f" ⚠{n_warnings}" if n_warnings else "")+(f" ✗{n_exc}" if n_exc else "")

    return f"""
<style>
#sk-db{{position:fixed;bottom:0;left:0;right:0;z-index:99999;
    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    font-size:12px;line-height:1.4;box-shadow:0 -4px 20px rgba(0,0,0,.7);
    transition:transform .2s ease}}
#sk-db.sk-collapsed{{transform:translateY(calc(100% - 34px))}}
#sk-bar{{background:#0f172a;border-top:2px solid {C_ACCENT};
    display:flex;align-items:stretch;height:34px;user-select:none}}
.sk-tab{{background:none;border:none;border-bottom:2px solid transparent;
    cursor:pointer;height:100%;padding:0 11px;
    font-size:11px;font-family:inherit;white-space:nowrap;transition:background .1s;color:#94a3b8}}
.sk-tab:hover{{background:rgba(255,255,255,.05)}}
.sk-tab.sk-active{{border-bottom:2px solid {C_ACCENT};color:#e2e8f0}}
.sk-panel{{background:#0a0f1e;border-top:1px solid #1e293b;max-height:340px;overflow-y:auto;display:none}}
.sk-panel.sk-open{{display:block}}
.sk-brand{{padding:0 12px;color:{C_ACCENT};font-weight:700;font-size:13px;
    border-right:1px solid #1e293b;display:flex;align-items:center;flex-shrink:0}}
.sk-metrics{{margin-left:auto;display:flex;align-items:center;gap:12px;padding:0 10px;font-size:11px;border-left:1px solid #1e293b}}
.sk-btn{{background:none;border:none;color:#475569;cursor:pointer;font-size:15px;
    padding:0 7px;line-height:1;display:flex;align-items:center;height:100%;flex-shrink:0}}
.sk-btn:hover{{color:#94a3b8}}
.sk-sql-row.sk-hidden{{display:none}}
</style>

<div id="sk-db">
  <div id="sk-bar">
    <div class="sk-brand">⚡ Debug</div>
    {_tab("timeline", "Timeline",          "#94a3b8", False)}
    {_tab("history",  "Historique",        "#64748b", False)}
    {_tab("sql",      sql_lbl,             sql_color, bool(n_slow or n_dup))}
    {_tab("http",     http_lbl,            http_color, bool(n_http_out))}
    {_tab("tpl",      f"Tpl ({len(templates)})", tpl_color, total_tpl>50)}
    {_tab("logs",     log_lbl,             log_color, bool(n_warnings or n_exc))}
    {_tab("request",  "Requête",           "#94a3b8", False)}
    {_tab("config",   "Config",            "#64748b", False)}
    <div class="sk-metrics">
      <span style="color:{time_color};font-weight:600">{page_ms}ms</span>
      <span style="color:{sql_color}">{n_queries} SQL/{total_sql}ms</span>
      <span style="color:{tpl_color}">{len(templates)} tpl/{total_tpl}ms</span>
      {mem_html}
      <span style="color:{C_MUTED}">{response_size_kb}Ko</span>
      <span style="color:{C_MUTED}">{req.method} {_esc(req.path)}</span>
    </div>
    <button class="sk-btn" id="sk-collapse-btn" onclick="skCollapse()" title="Réduire">▼</button>
    <button class="sk-btn" onclick="document.getElementById('sk-db').remove();document.body.style.paddingBottom=''" title="Fermer">×</button>
  </div>
  <div id="sk-panel-timeline" class="sk-panel">{timeline_html}</div>
  <div id="sk-panel-http"     class="sk-panel">{http_panel_html}</div>
  <div id="sk-panel-history"  class="sk-panel">{history_panel}</div>
  <div id="sk-panel-sql"      class="sk-panel">{sql_panel}</div>
  <div id="sk-panel-tpl"      class="sk-panel">{tpl_panel}</div>
  <div id="sk-panel-logs"     class="sk-panel">{logs_panel}</div>
  <div id="sk-panel-request"  class="sk-panel">{req_panel}</div>
  <div id="sk-panel-config"   class="sk-panel">{config_panel}</div>
</div>

<script>
(function(){{
  var _open=null,_col=false;

  function updatePadding(){{
    var db=document.getElementById('sk-db');if(!db)return;
    var open=db.querySelector('.sk-panel.sk-open');
    document.body.style.paddingBottom=(_col?34:(34+(open?open.scrollHeight:0)))+'px';
  }}

  window.skOpen=function(n){{
    var wasActive=document.getElementById('sk-tab-'+n)&&document.getElementById('sk-tab-'+n).classList.contains('sk-active');
    document.querySelectorAll('.sk-panel').forEach(function(p){{p.classList.remove('sk-open');}});
    document.querySelectorAll('.sk-tab').forEach(function(t){{t.classList.remove('sk-active');}});
    if(!wasActive){{
      var p=document.getElementById('sk-panel-'+n);
      var t=document.getElementById('sk-tab-'+n);
      if(p)p.classList.add('sk-open');
      if(t)t.classList.add('sk-active');
      if(_col){{_col=false;document.getElementById('sk-db').classList.remove('sk-collapsed');document.getElementById('sk-collapse-btn').textContent='▼';}}
      _open=n;
      try{{sessionStorage.setItem('sk_panel',n);}}catch(e){{}}
    }} else {{
      _open=null;
      try{{sessionStorage.removeItem('sk_panel');}}catch(e){{}}
    }}
    updatePadding();
  }};

  window.skCollapse=function(){{
    _col=!_col;
    document.getElementById('sk-db').classList.toggle('sk-collapsed',_col);
    document.getElementById('sk-collapse-btn').textContent=_col?'▲':'▼';
    updatePadding();
  }};

  // Filtre SQL
  // Copier tout le SQL depuis les data-sql des boutons copy
  window.skCopyAllSQL=function(btn){{
    var sqls=[];
    document.querySelectorAll('[data-sql]').forEach(function(el){{
      var sql=el.getAttribute('data-sql');
      if(sql&&sqls.indexOf(sql)<0)sqls.push(sql);
    }});
    navigator.clipboard.writeText(sqls.join('\\n---\\n')).then(function(){{
      btn.textContent='✓ Copié';
      setTimeout(function(){{btn.textContent='Copier tout le SQL';}},1500);
    }});
  }};

  // Copier un seul SQL
  window.skCopySingle=function(btn){{
    var sql=btn.getAttribute('data-sql')||'';
    navigator.clipboard.writeText(sql).then(function(){{
      btn.textContent='✓';
      setTimeout(function(){{btn.textContent='copy';}},1200);
    }});
  }};

  // EXPLAIN — lire le SQL depuis data-sql
  window.skExplain=function(btn,divId){{
    var sql=btn.getAttribute('data-sql')||'';
    var div=document.getElementById(divId);
    if(div.style.display!=='none'){{div.style.display='none';btn.textContent='EXPLAIN';return;}}
    btn.textContent='...';
    fetch('/api/debug/explain',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{sql:sql}})}})
      .then(function(r){{return r.json();}})
      .then(function(data){{
        div.textContent=data.plan||'Pas de plan disponible';
        div.style.display='block';
        btn.textContent='HIDE';
      }})
      .catch(function(){{div.textContent='Erreur';div.style.display='block';btn.textContent='ERR';}});
  }};

  window.skFilterSQL=function(q){{
    q=q.toLowerCase();
    document.querySelectorAll('.sk-sql-row').forEach(function(row){{
      var txt=row.textContent.toLowerCase();
      row.classList.toggle('sk-hidden',q.length>0&&txt.indexOf(q)<0);
    }});
  }};

  // Badge titre navigateur si SLOW
  var slowQ={slow_json};
  if(slowQ.length>0){{
    document.title='⚠ '+document.title;
    console.group('%c⚡ StockEleK Debug — '+slowQ.length+' requête(s) lente(s)','color:#f59e0b;font-weight:bold');
    slowQ.forEach(function(q){{console.warn(q.ms+'ms — '+q.sql);}});
    console.groupEnd();
  }}

  // Restaurer onglet
  var saved=null;try{{saved=sessionStorage.getItem('sk_panel');}}catch(e){{}}
  skOpen(saved||'timeline');
}})();
</script>
"""




# ── Appels HTTP sortants ──────────────────────────────────────────────

def record_http_out(method, url, status, duration_ms, req_body, resp_preview, error=None):
    """Enregistre un appel HTTP sortant — fonctionne depuis n'importe quel thread."""
    c = _find_collector()
    if c is None:
        return
    if "http_out" not in c:
        c["http_out"] = []
    # Catégoriser la destination
    dest = "Externe"
    url_lower = url.lower()
    if "192.168" in url or "localhost" in url or "127.0.0" in url:
        dest = "ESP32"
    elif "lcsc.com" in url_lower or "wmsc." in url_lower:
        dest = "LCSC"
    elif "mouser" in url_lower:
        dest = "Mouser"
    elif "digikey" in url_lower:
        dest = "DigiKey"
    elif "easyeda" in url_lower:
        dest = "EasyEDA"
    elif "jlc" in url_lower:
        dest = "JLCPCB"

    c["http_out"].append({
        "method":       method.upper(),
        "url":          url[:200],
        "status":       status,
        "duration_ms":  round(duration_ms, 2),
        "dest":         dest,
        "req_body":     str(req_body)[:300] if req_body else "",
        "resp_preview": str(resp_preview)[:200] if resp_preview else "",
        "error":        str(error)[:200] if error else None,
        "t_offset":     round((time.perf_counter() - c["t0"]) * 1000, 2),
    })


def _install_requests_hook():
    """
    Monkey-patch requests.Session.send pour capturer tous les appels HTTP sortants.
    Fonctionne aussi depuis les threads (enrichissement, LED...) en cherchant
    le collecteur dans g Flask si disponible, sinon dans un registre global
    indexé par thread-id de la requête parente.
    """
    import requests as _req

    _original_send = _req.Session.send

    def _patched_send(self, prepared_request, **kwargs):
        t0 = time.perf_counter()
        error = None
        response = None
        try:
            response = _original_send(self, prepared_request, **kwargs)
            return response
        except Exception as exc:
            error = exc
            raise
        finally:
            dur = (time.perf_counter() - t0) * 1000
            try:
                method = prepared_request.method or "?"
                url    = prepared_request.url or ""
                status = response.status_code if response is not None else 0

                # Body de la requête
                req_body = None
                if prepared_request.body:
                    body = prepared_request.body
                    if isinstance(body, bytes):
                        try: req_body = body.decode("utf-8")[:300]
                        except Exception: req_body = f"<binary {len(body)} bytes>"
                    else:
                        req_body = str(body)[:300]

                # Preview de la réponse
                resp_preview = None
                if response is not None:
                    ct = response.headers.get("Content-Type", "")
                    if "json" in ct:
                        try:
                            j = response.json()
                            resp_preview = json.dumps(j, ensure_ascii=False)[:200]
                        except Exception:
                            resp_preview = response.text[:200]
                    elif "text" in ct:
                        resp_preview = response.text[:200]
                    else:
                        resp_preview = f"<{ct} {len(response.content)} bytes>"

                record_http_out(method, url, status, dur, req_body, resp_preview, error)
            except Exception:
                pass

    _req.Session.send = _patched_send


_requests_hook_installed = False

# ── Intégration Flask ─────────────────────────────────────────────────
def init_toolbar(app):
    global _requests_hook_installed
    root_logger = logging.getLogger()
    if _log_handler not in root_logger.handlers:
        root_logger.addHandler(_log_handler)
    if root_logger.level == logging.NOTSET or root_logger.level > logging.DEBUG:
        root_logger.setLevel(logging.DEBUG)
    # Installer le hook requests une seule fois
    if not _requests_hook_installed:
        _install_requests_hook()
        _requests_hook_installed = True

    from flask.signals import before_render_template, template_rendered
    from flask import Blueprint, jsonify as _jsonify
    _starts = {}

    # Route EXPLAIN QUERY PLAN
    debug_bp = Blueprint("sk_debug", __name__)

    @debug_bp.route("/api/debug/explain", methods=["POST"])
    def debug_explain():
        from flask import request as _req
        sql = (_req.json or {}).get("sql", "")
        if not sql or not sql.strip().upper().startswith("SELECT"):
            return _jsonify({"plan": "Seules les requêtes SELECT sont supportées."})
        try:
            from .models.database import get_db
            db = get_db()
            raw = db._conn.execute(f"EXPLAIN QUERY PLAN {sql}").fetchall() if hasattr(db, '_conn') else []
            lines = [f"{'  '*row['subquery_depth'] if 'subquery_depth' in row.keys() else ''}{row['detail']}" for row in raw]
            plan_text = "\n".join(lines) if lines else "Pas de plan disponible."
            # Détecter SCAN sans index
            has_scan = any("SCAN" in l and "INDEX" not in l for l in lines)
            if has_scan:
                plan_text = "⚠ FULL SCAN détecté — envisager un index\n\n" + plan_text
        except Exception as e:
            plan_text = f"Erreur : {e}"
        return _jsonify({"plan": plan_text})

    @debug_bp.route("/api/debug/history")
    def debug_history():
        with _history_lock:
            return _jsonify(list(_history))

    app.register_blueprint(debug_bp)

    @before_render_template.connect_via(app)
    def _tpl_before(sender, template, context, **kw):
        c = get_collector()
        if c is None:
            return
        _starts[id(template)] = (time.perf_counter(), c["t0"])

    @template_rendered.connect_via(app)
    def _tpl_after(sender, template, context, **kw):
        c = get_collector()
        if c is None:
            return
        entry = _starts.pop(id(template), None)
        if entry is None:
            return
        t0_tpl, t0_req = entry
        dur   = (time.perf_counter() - t0_tpl) * 1000
        t_off = (time.perf_counter() - t0_req) * 1000
        skip = {"g","config","request","session","url_for","get_flashed_messages",
                "current_app","namespace","t","app_name","lang"}
        keys = [k for k in context.keys() if k not in skip]
        record_template(template.name or "<string>", dur, keys, t_off)

    @app.errorhandler(Exception)
    def _catch_exception(exc):
        c = get_collector()
        if c is not None:
            record_error(exc)
        raise exc

    @app.before_request
    def _before():
        start_collection()
        from .models.settings import SettingsModel
        try:
            debug = SettingsModel.get("debug_toolbar", "0")
        except Exception:
            debug = "0"
        skip = (
            debug != "1"
            or request.path.startswith("/api/debug/")
            or request.path.startswith("/static/")
            or request.path.startswith("/images/")
            or (request.path.startswith("/component/") and request.path.endswith("/image"))
        )
        # Les routes /api/* retournent du JSON — pas de toolbar HTML injectée
        # MAIS on veut quand même collecter leurs appels HTTP sortants (ESP32, etc.)
        # On distingue :
        #  - routes qui peuvent déclencher des appels sortants → collecter sans injecter
        #  - routes purement internes → skipper complètement
        api_collect_only = (
            request.path.startswith("/api/led/")
            or request.path.startswith("/api/price-check/")
            or request.path.startswith("/kicad/")
        )
        if skip:
            stop_collection()
            g._debug_active = False
            return
        g._debug_active = not api_collect_only  # False = pas d'injection HTML
        g._debug_collect_only = api_collect_only

        # Capturer JSON body et fichiers uploadés dans le collecteur
        c = get_collector()
        if c is not None:
            # JSON body (appels AJAX/API)
            json_body = None
            if request.is_json:
                try:
                    json_body = json.dumps(request.get_json(), ensure_ascii=False, indent=2)[:500]
                except Exception:
                    json_body = "<erreur décodage JSON>"
            c["json_body"] = json_body

            # Fichiers uploadés
            uploads = []
            for field, fobj in request.files.items():
                if fobj and fobj.filename:
                    # Lire les premiers octets pour détecter le type
                    head = fobj.read(4)
                    fobj.seek(0)
                    uploads.append({
                        "field":    field,
                        "filename": fobj.filename,
                        "mimetype": fobj.mimetype or "?",
                        "size_est": "?",  # taille pas encore connue avant lecture complète
                        "magic":    head.hex() if head else "",
                    })
            c["uploads"] = uploads

            # Marquer si requête AJAX
            c["is_ajax"] = (
                request.headers.get("X-Requested-With") == "XMLHttpRequest"
                or request.is_json
                or request.path.startswith("/api/")
            )

    @app.after_request
    def _after(response):
        collect_only = getattr(g, "_debug_collect_only", False)

        # Routes collect-only (ex: /api/led/) — stocker dans l'historique mais pas d'injection HTML
        if collect_only:
            data = stop_collection()
            if data and data.get("http_out"):
                import datetime
                with _history_lock:
                    _history.append({
                        "time":    datetime.datetime.now().strftime("%H:%M:%S"),
                        "method":  request.method,
                        "path":    request.path,
                        "ms":      data.get("duration_ms", 0),
                        "n_sql":   len(data.get("queries", [])),
                        "status":  str(response.status_code),
                        "size_kb": 0,
                        "http_out": data.get("http_out", []),
                    })
            return response

        if not getattr(g, "_debug_active", False):
            return response
        if "text/html" not in (response.content_type or ""):
            return response
        data = stop_collection()
        if data is None:
            return response
        try:
            body       = response.get_data(as_text=True)
            size_kb    = round(len(body.encode("utf-8")) / 1024, 1)
            html       = render_toolbar(data, response.status_code, size_kb)
            if "</body>" in body:
                body = body.replace("</body>", html + "\n</body>", 1)
                response.set_data(body)
        except Exception as e:
            logger.debug("Toolbar render error: %s", e)
        return response
