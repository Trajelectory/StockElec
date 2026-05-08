import json
import logging
import re as _re

logger = logging.getLogger(__name__)

from flask import (
    request,
    jsonify,
    render_template,
    Response,
    current_app,
)

import time as _time
import threading
import requests as _requests

from ..models.component import ComponentModel
from ..models.settings import SettingsModel
from .utils import _t
from . import component_bp

# ── Cache thread-safe pour la détection P4 vs S3 ─────────────────────
_p4_cache: dict = {}
_p4_cache_lock  = threading.Lock()


def clear_p4_cache() -> None:
    """Vide le cache de détection P4 — à appeler après un changement d'URL ESP32."""
    with _p4_cache_lock:
        _p4_cache.clear()
    logger.debug("[LED] Cache P4 invalidé")


# ------------------------------------------------------------------ #
#  API LED — ESP32 WS2812B
# ------------------------------------------------------------------ #

def _get_led_config():
    """Retourne la config ESP32 depuis les settings — 1 seule requête SQL via get_all()."""
    s = SettingsModel.get_all()
    return {
        "url":      s.get("esp32_url",      "").strip().rstrip("/"),
        "color":    s.get("esp32_color",    "purple"),
        "duration": int(s.get("esp32_duration", "5") or "5"),
        "offsets":  s.get("esp32_offsets",  "{}"),
        "token":    s.get("esp32_token",    ""),
    }


def _resolve_cfg(atelier_id: str | None = None) -> dict:
    """
    Retourne la config ESP32 résolue dans cet ordre de priorité :
      1. Config de l'atelier demandé (si atelier_id fourni et esp32_url renseignée)
      2. Config globale (table settings, clé esp32_url)  ← fallback

    Copie TOUS les champs pertinents depuis l'atelier :
    url, token, duration ET offsets (les offsets sont propres à chaque atelier).
    """
    cfg = _get_led_config()  # fallback global
    if not atelier_id:
        return cfg
    from ..models.atelier import AtelierModel
    atelier = AtelierModel.get(atelier_id)
    if atelier and atelier.get("esp32_url"):
        cfg = dict(cfg)
        cfg["url"]      = atelier["esp32_url"].strip().rstrip("/")
        cfg["token"]    = atelier.get("esp32_token") or cfg["token"]
        cfg["duration"] = atelier.get("esp32_duration") or cfg["duration"]
        # Les offsets sont propres à chaque atelier — TOUJOURS les copier
        # Sans ça, _compute_led_indices utilise les offsets globaux (vides)
        # et les indices LED sont incorrects.
        if atelier.get("esp32_offsets"):
            cfg["offsets"] = atelier["esp32_offsets"]
    return cfg


def _led_headers(cfg: dict) -> dict:
    """Headers HTTP pour les requêtes ESP32 — inclut X-Token si configuré."""
    h = {}
    if cfg.get("token"):
        h["X-Token"] = cfg["token"]
    return h


def _compute_led_indices(cell_id: str, cfg: dict, all_settings: dict | None = None) -> tuple[list[int], str]:
    """
    Calcule les indices LED physiques pour une case donnée.
    cell_id = "A3" (plateau A, case 3)
    offsets = {"A": 0, "B": 50, ...}
    all_settings : dict optionnel déjà chargé (évite des requêtes SQL supplémentaires)
    """
    import json
    # Séparer plateau ID (lettres) et numéro de case (chiffres)
    m = _re.match(r'^([A-Za-z]+)(\d+)$', cell_id)
    if not m:
        return [], ""
    pid, num = m.group(1), int(m.group(2))

    try:
        offsets = json.loads(cfg["offsets"]) if cfg["offsets"] else {}
    except Exception:
        offsets = {}

    offset = int(offsets.get(pid, 0))

    # Récupérer la config du plateau
    # Priorité : cfg["_rangement_config"] (config propre à l'atelier)
    # puis all_settings, puis SettingsModel global
    # Toujours charger s pour rangement_sizes (utilisé plus bas)
    s = all_settings or SettingsModel.get_all()

    if cfg.get("_rangement_config") is not None:
        raw_config = cfg["_rangement_config"]
        # Pour les sizes, utiliser la clé préfixée par atelier si dispo
        atelier_id = cfg.get("_atelier_id", "")
        if atelier_id:
            raw_sizes_val = SettingsModel.get(f"atelier_{atelier_id}_rangement_sizes", "")
        else:
            raw_sizes_val = s.get("rangement_sizes", "")
    else:
        raw_config    = s.get("rangement_config", "")
        raw_sizes_val = s.get("rangement_sizes", "")
    try:
        plateau_cfg = json.loads(raw_config) if raw_config else {"plateaux": []}
    except Exception:
        plateau_cfg = {"plateaux": []}

    plateau = next((p for p in plateau_cfg.get("plateaux", []) if p["id"] == pid), None)
    if not plateau:
        # Fallback : indice direct
        return [offset + num - 1], pid

    cols = int(plateau.get("cols", 1))

    # Position de la case origine (1-indexé → 0-indexé)
    idx0  = num - 1
    row0  = idx0 // cols
    col0  = idx0 % cols

    # Taille de la boîte
    raw_sizes = raw_sizes_val
    try:
        sizes = json.loads(raw_sizes) if raw_sizes else {}
    except Exception:
        sizes = {}

    size  = sizes.get(cell_id, "1x1")
    parts = size.split("x")
    sw    = int(parts[0]) if len(parts) == 2 else 1
    sh    = int(parts[1]) if len(parts) == 2 else 1
    logger.info("[LED] cell=%s size=%s sw=%d sh=%d atelier=%s sizes_keys=%s",
                cell_id, size, sw, sh,
                cfg.get("_atelier_id", "global"),
                list(sizes.keys())[:5])

    # Générer tous les indices de la zone
    indices = []
    for r in range(row0, row0 + sh):
        for c in range(col0, col0 + sw):
            indices.append(offset + r * cols + c)

    return indices, pid


# ── Mapping famille LCSC → couleur LED ───────────────────────────────
# Défauts hardcodés — overridables depuis les settings (led_color_<keyword>)
# Mapping catégories LCSC → familles LED — vérifié le 2025-04 (LCSC v3.x)
# À re-vérifier si LCSC change ses noms de catégories
LED_COLOR_DEFAULTS = {
    # ── Passifs ───────────────────────────────────────────────────
    "sensor":          "#34d399",   # Vert clair    — Capteurs (avant resistor)
    "resistor":        "#f97316",   # Orange        — Résistances
    "capacitor":       "#3b82f6",   # Bleu          — Condensateurs
    "inductor":        "#eab308",   # Jaune         — Inductances
    "ferrite":         "#eab308",   # Jaune         — Ferrites
    # ── Semi-conducteurs discrets ─────────────────────────────────
    "transistor":      "#22c55e",   # Vert          — Transistors / Thyristors
    "mosfet":          "#22c55e",   # Vert          — MOSFETs
    "diode":           "#ef4444",   # Rouge         — Diodes
    # ── Optoélectronique ─────────────────────────────────────────
    "optoelectronic":  "#06b6d4",   # Cyan          — Optoélectronique
    "display":         "#06b6d4",   # Cyan          — Afficheurs
    # ── LEDs & drivers ───────────────────────────────────────────
    "led driver":      "#f0abfc",   # Rose vif      — LED Drivers (avant "led")
    "led ":            "#f0abfc",   # Rose          — LEDs (espace évite "led driver")
    # ── ICs & logique ────────────────────────────────────────────
    "amplifier":       "#8b5cf6",   # Violet foncé  — Amplificateurs
    "comparator":      "#8b5cf6",   # Violet foncé  — Comparateurs
    "integrated":      "#a855f7",   # Violet        — Circuits intégrés
    "microcontroller": "#a855f7",   # Violet        — MCU
    "embedded":        "#a855f7",   # Violet        — Dev boards / MCU
    "memory":          "#a855f7",   # Violet        — Mémoires
    "logic":           "#a855f7",   # Violet        — Logique
    "interface":       "#a855f7",   # Violet        — Interface ICs
    # ── Connectique ──────────────────────────────────────────────
    "connector":       "#f8fafc",   # Blanc         — Connecteurs
    "socket":          "#f8fafc",   # Blanc         — Sockets
    "ic ":             "#a855f7",   # Violet        — ICs (après connector)
    "header":          "#f8fafc",   # Blanc         — Headers
    "shunt":           "#f8fafc",   # Blanc         — Shunts / Jumpers
    # ── Switches ─────────────────────────────────────────────────
    "switch":          "#94a3b8",   # Gris bleuté   — Interrupteurs
    "button":          "#94a3b8",   # Gris bleuté   — Boutons
    # ── Timing ───────────────────────────────────────────────────
    "crystal":         "#67e8f9",   # Cyan clair    — Quartz
    "oscillator":      "#67e8f9",   # Cyan clair    — Oscillateurs
    "clock":           "#67e8f9",   # Cyan clair    — Clock/Timing
    "real time":       "#67e8f9",   # Cyan clair    — RTC
    # ── Protection ───────────────────────────────────────────────
    "fuse":            "#fbbf24",   # Ambre         — Fusibles
    "protection":      "#fbbf24",   # Ambre         — Protection
    # ── Capteurs ─────────────────────────────────────────────────
    # ── Alimentation ─────────────────────────────────────────────
    "power":           "#fb923c",   # Orange vif    — Power Management
    "voltage":         "#fb923c",   # Orange vif    — Régulateurs
    # ── Relais ───────────────────────────────────────────────────
    "relay":           "#c084fc",   # Violet clair  — Relais
    "transformer":     "#c084fc",   # Violet clair  — Transformateurs
    # ── Moteurs ──────────────────────────────────────────────────
    "motor":           "#4ade80",   # Vert vif      — Moteurs / Servos
    "servo":           "#4ade80",   # Vert vif      — Servomoteurs
    # ── RF / Sans fil ────────────────────────────────────────────
    "rf":              "#38bdf8",   # Bleu clair    — RF
    "antenna":         "#38bdf8",   # Bleu clair    — Antennes
    "iot":             "#38bdf8",   # Bleu clair    — IoT modules
    "communication":   "#38bdf8",   # Bleu clair    — Modules comm
}

# Clés de settings par famille principale (keyword → setting key)
LED_COLOR_SETTING_KEYS = {
    "sensor":          "led_color_sensor",     # avant resistor (Photoresistors)
    "resistor":        "led_color_resistor",
    "capacitor":       "led_color_capacitor",
    "inductor":        "led_color_inductor",
    "ferrite":         "led_color_inductor",
    "transistor":      "led_color_transistor",
    "mosfet":          "led_color_transistor",
    "diode":           "led_color_diode",
    "optoelectronic":  "led_color_optoelectronic",
    "display":         "led_color_optoelectronic",
    "led driver":      "led_color_led",
    "led ":            "led_color_led",
    "amplifier":       "led_color_amplifier",
    "comparator":      "led_color_amplifier",
    "integrated":      "led_color_ic",
    "microcontroller": "led_color_ic",
    "embedded":        "led_color_ic",
    "memory":          "led_color_ic",
    "logic":           "led_color_ic",
    "interface":       "led_color_ic",
    "connector":       "led_color_connector",
    "ic ":             "led_color_ic",
    "socket":          "led_color_connector",
    "header":          "led_color_connector",
    "shunt":           "led_color_connector",
    "switch":          "led_color_switch",
    "button":          "led_color_switch",
    "crystal":         "led_color_crystal",
    "oscillator":      "led_color_crystal",
    "clock":           "led_color_crystal",
    "real time":       "led_color_crystal",
    "fuse":            "led_color_fuse",
    "protection":      "led_color_fuse",
    "power":           "led_color_power",
    "voltage":         "led_color_power",
    "relay":           "led_color_relay",
    "transformer":     "led_color_relay",
    "motor":           "led_color_motor",
    "servo":           "led_color_motor",
    "rf":              "led_color_rf",
    "antenna":         "led_color_rf",
    "iot":             "led_color_rf",
    "communication":   "led_color_rf",
}

def _color_for_category(category: str, default: str) -> str:
    """Retourne la couleur LED selon la catégorie — lit les settings en priorité."""
    if not category:
        return default
    cat_lower = category.lower()
    for keyword, setting_key in LED_COLOR_SETTING_KEYS.items():
        if keyword in cat_lower:
            # Lire depuis les settings (override utilisateur)
            saved = SettingsModel.get(setting_key, "").strip()
            if saved:
                return saved
            # Sinon valeur par défaut
            return LED_COLOR_DEFAULTS.get(keyword, default)
    return default


@component_bp.route("/api/led/<cell_id>/on", methods=["POST"])
def led_on(cell_id):
    """Allume les LEDs correspondant à la case donnée sur l'ESP32.

    Utilise _resolve_cfg() pour résoudre la config ESP32 dans le même
    ordre de priorité que led_off, led_ping et led_status :
      1. Config de l'atelier (atelier_id dans le body JSON ou query string)
      2. Config globale (table settings) en fallback
    """
    data       = request.get_json(silent=True) or {}
    atelier_id = (data.get("atelier_id") or
                  request.args.get("atelier_id", "")).strip()

    cfg = _resolve_cfg(atelier_id)

    # ── DEBUG TEMPORAIRE — à supprimer après validation ─────────────
    logger.warning(
        "[LED DEBUG] led_on appelé — atelier_id=%r  url_résolue=%r  body=%r",
        atelier_id, cfg.get("url"), dict(data)
    )
    # ────────────────────────────────────────────────────────────────

    # Enrichir la config avec les données de rangement de l'atelier
    if atelier_id:
        from ..models.settings import SettingsModel as _SM
        raw = _SM.get(f"atelier_{atelier_id}_rangement_config", "")
        cfg["_rangement_config"] = raw
        cfg["_atelier_id"]       = atelier_id

    if not cfg["url"]:
        return jsonify({"ok": False, "error": _t("msg.esp32_not_configured")}), 400

    indices, pid = _compute_led_indices(cell_id, cfg)
    if not indices:
        return jsonify({"ok": False, "error": _t("msg.led_calc_error")}), 400

    # Couleur : depuis la catégorie du composant si component_id fourni
    component_id = data.get("component_id")
    color        = cfg["color"]   # couleur par défaut
    comp_desc    = ""

    if component_id:
        comp = ComponentModel.get_by_id(int(component_id))
        if comp:
            comp_desc = comp.description or ""
            if comp.category:
                color = _color_for_category(comp.category, cfg["color"])

    # Index du tiroir pour le second ruban LED (A=0, B=1, C=2...)
    drawer_index = ord(pid.upper()[0]) - ord('A') if pid else None

    payload = {
        "leds":         indices,
        "color":        color,
        "duration":     cfg["duration"],
        "cell":         cell_id,
        "component_id": int(component_id) if component_id else None,
    }
    if drawer_index is not None:
        payload["drawer"] = drawer_index

    try:
        esp_url = cfg["url"]

        # ── Détection de l'endpoint — polyvalent S3 / P4 ─────────────
        # On interroge /ping pour avoir un indice, mais on valide
        # en testant réellement l'endpoint. Le résultat est mis en cache
        # 60s pour éviter un aller-retour à chaque LED.
        now = _time.time()
        with _p4_cache_lock:
            cached = _p4_cache.get(esp_url)

        if cached is None or now - cached[2] > 60:
            # Indice initial depuis /ping
            try:
                ping     = _requests.get(f"{esp_url}/ping", timeout=2)
                hint_p4  = ping.status_code == 200 and ping.json().get("display", False)
            except Exception:
                hint_p4  = False

            # Ordre de tentative : on commence par ce que dit le ping,
            # mais on a un fallback automatique si c'est 404
            endpoints_to_try = ["/led", "/leds"] if hint_p4 else ["/leds", "/led"]
            with _p4_cache_lock:
                _p4_cache[esp_url] = (hint_p4, endpoints_to_try, now)
        else:
            hint_p4, endpoints_to_try, _ = cached

        device = "P4" if hint_p4 else "S3"

        # ── Log lisible ───────────────────────────────────────────────
        logger.info(
            "\n"
            "┌─ LED ON ───────────────────────────────────\n"
            "│  Device    : %s  (%s)\n"
            "│  Case      : %s  →  LEDs %s  tiroir %s\n"
            "│  Couleur   : %s\n"
            "│  Durée     : %ss\n"
            "│  Composant : #%s  %s\n"
            "└────────────────────────────────────────────",
            device, esp_url,
            cell_id, indices, drawer_index,
            color,
            cfg["duration"],
            component_id or "—", comp_desc[:50] or "—",
        )

        # ── Envoi avec fallback automatique ──────────────────────────
        last_status = None
        for endpoint in endpoints_to_try:
            resp = _requests.post(
                f"{esp_url}{endpoint}",
                json=payload,
                headers=_led_headers(cfg),
                timeout=5,
            )
            last_status = resp.status_code
            status_icon = "✅" if resp.status_code in (200, 202) else "❌"
            logger.info("[LED] %s %s → HTTP %s", status_icon, endpoint, resp.status_code)

            if resp.status_code in (200, 202):
                queued = resp.status_code == 202
                if queued:
                    logger.info("[LED] ⏳ Mis en file d'attente (202)")
                # Mémoriser l'endpoint qui a marché en premier pour les 60s suivantes
                worked_p4 = endpoint == "/led"
                if worked_p4 != hint_p4:
                    logger.info("[LED] 🔄 Endpoint réel (%s) ≠ hint ping — cache mis à jour", endpoint)
                with _p4_cache_lock:
                    _p4_cache[esp_url] = (worked_p4, [endpoint], now)
                return jsonify({"ok": True, "leds": indices, "queued": queued,
                                "endpoint": endpoint})

            if resp.status_code == 404:
                logger.info("[LED] ↩️  404 sur %s — tentative sur l'autre endpoint", endpoint)
                continue

            # Autre erreur HTTP (pas 404) — on arrête
            break

        return jsonify({"ok": False, "error": f"ESP32 HTTP {last_status}"}), 502

    except _requests.RequestException as e:
        logger.warning("[LED] ✗ Erreur réseau : %s", e)
        return jsonify({"ok": False, "error": str(e)}), 503


@component_bp.route("/api/led/off", methods=["POST"])
def led_off():
    """Éteint toutes les LEDs.

    Accepte un body JSON optionnel avec atelier_id pour cibler
    l'ESP32 d'un atelier spécifique plutôt que la config globale.
    """
    data       = request.get_json(silent=True) or {}
    atelier_id = data.get("atelier_id") or request.args.get("atelier_id", "").strip()
    cfg        = _resolve_cfg(atelier_id)
    if not cfg["url"]:
        return jsonify({"ok": False, "error": _t("msg.esp32_not_configured")}), 400
    logger.info("[LED] ⬛ OFF → %s (atelier=%s)", cfg["url"], atelier_id or "global")
    try:
        resp = _requests.post(f"{cfg['url']}/off", headers=_led_headers(cfg), timeout=5)
        status_icon = "✅" if resp.status_code == 200 else "❌"
        logger.info("[LED] %s OFF réponse HTTP %s", status_icon, resp.status_code)
        return jsonify({"ok": resp.status_code == 200})
    except _requests.RequestException as e:
        logger.warning("[LED] ✗ OFF erreur réseau : %s", e)
        return jsonify({"ok": False, "error": str(e)}), 503


def _count_leds_from_config(atelier_id: str) -> int | None:
    """
    Calcule le nombre total de LEDs depuis les offsets + la config des plateaux.
    Formule : max sur tous les plateaux de (offset[plateau] + cols * rows)
    Retourne None si les données sont insuffisantes.
    """
    import json as _json
    from ..models.atelier import AtelierModel as _AM
    try:
        atelier = _AM.get(atelier_id) if atelier_id else None
        if atelier:
            raw_offsets = atelier.get("esp32_offsets") or "{}"
            raw_config  = SettingsModel.get(f"atelier_{atelier_id}_rangement_config", "")
        else:
            raw_offsets = SettingsModel.get("esp32_offsets", "{}")
            raw_config  = SettingsModel.get("rangement_config", "")

        offsets  = _json.loads(raw_offsets) if raw_offsets else {}
        cfg_data = _json.loads(raw_config)  if raw_config  else {}
        plateaux = cfg_data.get("plateaux", [])

        if not offsets or not plateaux:
            return None

        total = 0
        for p in plateaux:
            pid   = p.get("id", "")
            cols  = int(p.get("cols", 1))
            rows  = int(p.get("rows", 1))
            off   = int(offsets.get(pid, 0))
            total = max(total, off + cols * rows)

        return total if total > 0 else None
    except Exception as e:
        logger.debug("[LED] _count_leds_from_config error: %s", e)
        return None


@component_bp.route("/api/led/ping", methods=["GET"])
def led_ping():
    """Vérifie que l'ESP32 est joignable.

    Paramètre optionnel : ?atelier_id=<id> pour cibler l'ESP32
    d'un atelier spécifique plutôt que la config globale.

    Le nombre de LEDs est lu depuis la réponse /ping de l'ESP32.
    Si l'ESP32 ne le fournit pas (firmware P4 minimal), il est calculé
    automatiquement depuis les offsets + la config des plateaux de l'atelier.
    """
    atelier_id = request.args.get("atelier_id", "").strip()
    cfg        = _resolve_cfg(atelier_id)
    if not cfg["url"]:
        return jsonify({"ok": False, "error": _t("msg.esp32_not_configured")}), 400
    logger.info("[LED] 🔔 PING → %s (atelier=%s)", cfg["url"], atelier_id or "global")
    try:
        resp = _requests.get(f"{cfg['url']}/ping", headers=_led_headers(cfg), timeout=4)
        if resp.status_code == 200:
            data   = resp.json()
            device = "P4" if data.get("display") else "S3"

            # Nombre de LEDs : depuis l'ESP32 en priorité, sinon calculé localement
            leds = data.get("leds")
            if leds is None:
                leds = _count_leds_from_config(atelier_id)
                if leds is not None:
                    logger.info("[LED] ℹ️  leds non fourni par l'ESP32 — calculé depuis offsets : %d", leds)

            logger.info(
                "[LED] ✅ PING OK  device=%s  uptime=%ss  leds=%s  ip=%s",
                device, data.get("uptime", "?"), leds, cfg["url"]
            )
            return jsonify({"ok": True, "leds": leds,
                            "display": data.get("display", False), "ip": cfg["url"]})
        logger.warning("[LED] ❌ PING HTTP %s", resp.status_code)
        return jsonify({"ok": False, "error": f"HTTP {resp.status_code}"}), 502
    except _requests.RequestException as e:
        logger.warning("[LED] ✗ PING erreur réseau : %s", e)
        return jsonify({"ok": False, "error": str(e)}), 503



@component_bp.route("/api/led/ping-direct")
def led_ping_direct():
    """Ping un ESP32 à une URL donnée en paramètre — pour tester un atelier spécifique."""
    from flask import request as _req
    url = _req.args.get("url", "").strip().rstrip("/")
    if not url:
        return jsonify({"ok": False, "error": "URL manquante"}), 400
    try:
        import requests as _requests
        token = SettingsModel.get("esp32_token", "").strip()
        headers = {}
        if token:
            headers["X-Token"] = token
        resp = _requests.get(f"{url}/ping", headers=headers, timeout=4)
        data = resp.json()
        return jsonify({"ok": True, "leds": data.get("leds"), "ip": url,
                        "device": data.get("device", "S3")})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@component_bp.route("/api/led/status", methods=["GET"])
def led_status():
    """Récupère l'état courant des LEDs depuis l'ESP32.

    Paramètre optionnel : ?atelier_id=<id> pour cibler l'ESP32
    d'un atelier spécifique plutôt que la config globale.
    """
    atelier_id = request.args.get("atelier_id", "").strip()
    cfg        = _resolve_cfg(atelier_id)
    if not cfg["url"]:
        return jsonify({"ok": False, "error": _t("msg.esp32_not_configured")}), 400
    try:
        resp = _requests.get(f"{cfg['url']}/status",
                             headers=_led_headers(cfg), timeout=4)
        if resp.status_code == 200:
            return jsonify(resp.json())
        return jsonify({"ok": False, "error": f"HTTP {resp.status_code}"}), 502
    except _requests.RequestException as e:
        logger.warning("[LED] ✗ STATUS erreur réseau : %s", e)
        return jsonify({"ok": False, "error": str(e)}), 503


@component_bp.route("/api/led/test", methods=["POST"])
def led_test():
    """Lance un chenillard sur un plateau pour valider le câblage.

    Accepte un paramètre optionnel atelier_id dans le body JSON
    ou en query string pour utiliser la config ESP32 propre à l'atelier.
    Utilise _resolve_cfg() comme toutes les autres routes LED.
    """
    data       = request.get_json() or {}
    atelier_id = (data.get("atelier_id") or
                  request.args.get("atelier_id", "")).strip()

    cfg = _resolve_cfg(atelier_id)

    if not cfg["url"]:
        return jsonify({"ok": False, "error": _t("msg.esp32_not_configured")}), 400

    esp32_url  = cfg["url"]
    esp32_tok  = cfg["token"]
    raw_off    = cfg["offsets"]
    raw_config = (SettingsModel.get(f"atelier_{atelier_id}_rangement_config", "")
                  if atelier_id else SettingsModel.get("rangement_config", ""))

    pid      = data.get("plateau", "A")
    delay_ms = int(data.get("delay_ms", 80))
    color    = data.get("color", cfg["color"])

    try:
        offsets = json.loads(raw_off) if raw_off else {}
    except Exception:
        offsets = {}

    try:
        plateau_cfg = json.loads(raw_config) if raw_config else {"plateaux": []}
    except Exception:
        plateau_cfg = {"plateaux": []}

    plateau = next((p for p in plateau_cfg.get("plateaux", []) if p["id"] == pid), None)
    if not plateau:
        return jsonify({"ok": False, "error": f"Plateau '{pid}' introuvable"}), 400

    offset = int(offsets.get(pid, 0))
    count  = plateau["cols"] * plateau["rows"]

    # Headers avec le bon token
    headers = {"Content-Type": "application/json"}
    if esp32_tok:
        headers["X-Token"] = esp32_tok

    payload = {"offset": offset, "count": count, "delay_ms": delay_ms, "color": color}
    logger.info("[LED] → TEST atelier=%s plateau=%s offset=%s count=%s delay=%sms",
                atelier_id or "global", pid, offset, count, delay_ms)
    try:
        resp = _requests.post(f"{esp32_url}/test",
                              json=payload,
                              headers=headers,
                              timeout=5)
        logger.info("[LED] ← TEST HTTP %s", resp.status_code)
        if resp.status_code == 200:
            return jsonify({"ok": True, "plateau": pid,
                            "offset": offset, "count": count})
        return jsonify({"ok": False, "error": f"ESP32 HTTP {resp.status_code}"}), 502
    except _requests.RequestException as e:
        logger.warning("[LED] ✗ TEST erreur réseau : %s", e)
        return jsonify({"ok": False, "error": str(e)}), 503


# ------------------------------------------------------------------ #
#  Serving images
# ------------------------------------------------------------------ #
