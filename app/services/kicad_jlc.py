"""
Service KiCad — génération des fichiers KiCad via JLC2KiCadLib.

JLC2KiCadLib doit être installé sur la machine :
    pip install JLC2KiCadLib

Structure générée dans instance/kicad/ :
    Resistors/
        0805W8F1003T5E_C149504/
            0805W8F1003T5E_C149504.kicad_sym
            R0805.kicad_mod
            R0805.step
    Amplifiers/
        TL082IDR_C6961/
            TL082IDR_C6961.kicad_sym
            SOIC-8_L5.0-W4.0-P1.27-LS6.0-BL.kicad_mod
            SOIC-8_L5.0-W4.0-P1.27-LS6.0-BL.step
"""

import os
import re
import glob
import shutil
import logging
import tempfile
import subprocess
import threading
import time

import requests

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
#  API JLCPCB — récupère catégorie + part_number
# ------------------------------------------------------------------ #

JLCPCB_API_URL = "https://cart.jlcpcb.com/shoppingCart/smtGood/getComponentDetail?componentCode={}"

_api_session = requests.Session()
_api_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
})


def _get_component_info(ref: str) -> tuple[str, str]:
    """
    Interroge l'API JLCPCB pour récupérer (category, part_number).
    Retourne ("Unknown", ref) en cas d'échec.
    """
    try:
        resp = _api_session.get(JLCPCB_API_URL.format(ref), timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data and "data" in data and data["data"]:
                category    = data["data"].get("firstSortName", "Unknown") or "Unknown"
                part_number = data["data"].get("componentModelEn", ref)    or ref
                return category.strip(), part_number.strip()
    except Exception as e:
        logger.warning("[KiCad] API JLCPCB échouée pour %s : %s", ref, e)
    return "Unknown", ref


def _safe_name(s: str) -> str:
    """Nettoie une chaîne pour l'utiliser comme nom de dossier/fichier."""
    s = s.strip()
    s = re.sub(r'[\\/:"*?<>|]', "-", s)
    s = re.sub(r'\s+', "_", s)
    s = re.sub(r'-{2,}', "-", s)
    return s or "Unknown"


# ------------------------------------------------------------------ #
#  État global du job (un seul job à la fois)
# ------------------------------------------------------------------ #

_job_lock = threading.Lock()

_state = {
    "running": False,
    "total":   0,
    "current": 0,
    "ref":     "",
    "log":     [],
    "done":    False,
}

_LOG_MAX = 500


def get_state() -> dict:
    with _job_lock:
        s = dict(_state)
        s["log"] = list(_state["log"])
        return s


def is_running() -> bool:
    with _job_lock:
        return _state["running"]


def _log(ref: str, status: str, msg: str):
    entry = {"ref": ref, "status": status, "msg": msg}
    logger.info("[KiCad] %s — %s — %s", ref, status, msg)
    with _job_lock:
        _state["log"].append(entry)
        if len(_state["log"]) > _LOG_MAX:
            _state["log"] = _state["log"][-_LOG_MAX:]


# ------------------------------------------------------------------ #
#  Téléchargement + organisation d'un composant
# ------------------------------------------------------------------ #

def _already_done(ref: str, kicad_dir: str) -> bool:
    """Vérifie si ce composant a déjà été généré (pour la reprise de job)."""
    return bool(glob.glob(os.path.join(kicad_dir, "*", f"*_{ref}")))




def get_missing_kicad_refs(kicad_dir: str, lcsc_refs: list[str]) -> list[str]:
    """
    Retourne les références LCSC qui n'ont PAS encore de fichiers KiCad générés.
    Utilise _already_done() qui vérifie l'existence d'un dossier *_<REF>.
    """
    if not lcsc_refs:
        return []
    return [ref for ref in lcsc_refs if not _already_done(ref, kicad_dir)]

def _download_one(ref: str, kicad_dir: str, prefix: str = "") -> str:
    """
    1. Appelle l'API JLCPCB pour récupérer catégorie + part_number
    2. Lance JLC2KiCadLib dans un dossier temporaire
    3. Déplace les fichiers dans kicad_dir/<Categorie>/<PartNumber>_<REF>/
    Retourne : "ok" | "skip" | "error"
    """
    if _already_done(ref, kicad_dir):
        _log(ref, "skip", "Déjà généré")
        return "skip"

    # Récupération des infos composant via API JLCPCB
    category, part_number = _get_component_info(ref)
    safe_cat    = _safe_name(category)
    safe_part   = _safe_name(part_number)
    folder_name = f"{safe_part}_{ref}"
    dest_dir    = os.path.join(kicad_dir, safe_cat, folder_name)

    # Nom de la librairie symbole = <prefix><part_number>_<ref>
    # (on utilise le nom du composant, pas la catégorie)
    sym_lib_name = f"{prefix}{folder_name}" if prefix else folder_name

    # JLC2KiCadLib génère dans un dossier temporaire
    with tempfile.TemporaryDirectory(prefix="jlc2kicad_") as tmp_dir:
        try:
            result = subprocess.run(
                ["JLC2KiCadLib", ref, "-dir", tmp_dir,
                 "-symbol_lib", sym_lib_name],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except FileNotFoundError:
            _log(ref, "error", "JLC2KiCadLib introuvable — pip install JLC2KiCadLib")
            return "error"
        except subprocess.TimeoutExpired:
            _log(ref, "warn", "Timeout (60s)")
            return "skip"
        except Exception as e:
            _log(ref, "error", str(e)[:120])
            return "error"

        if result.returncode != 0:
            stderr = (result.stderr or "").strip().splitlines()
            msg = stderr[-1] if stderr else "Erreur inconnue"
            if any(k in msg.lower() for k in ("no data", "not found", "no component")):
                _log(ref, "skip", "Pas de données KiCad disponibles")
            else:
                _log(ref, "warn", msg[:120])
            return "skip"

        # Collecter tous les fichiers KiCad générés
        generated = []
        for root, dirs, files in os.walk(tmp_dir):
            for fname in files:
                if fname.endswith((".kicad_sym", ".kicad_mod", ".step", ".wrl")):
                    generated.append(os.path.join(root, fname))

        if not generated:
            _log(ref, "skip", "Aucun fichier généré")
            return "skip"

        # Déplacement vers la destination organisée
        os.makedirs(dest_dir, exist_ok=True)
        moved = []
        for src in generated:
            dst = os.path.join(dest_dir, os.path.basename(src))
            shutil.copy2(src, dst)
            moved.append(os.path.basename(src))

    parts = []
    if any(f.endswith(".kicad_sym")      for f in moved): parts.append("symbol")
    if any(f.endswith(".kicad_mod")      for f in moved): parts.append("footprint")
    if any(f.endswith((".step", ".wrl")) for f in moved): parts.append("3D")

    _log(ref, "ok", f"{safe_cat}/{folder_name} — {', '.join(parts)}")
    return "ok"


# ------------------------------------------------------------------ #
#  Vérification de JLC2KiCadLib
# ------------------------------------------------------------------ #

def check_jlc2kicadlib() -> tuple[bool, str]:
    """
    Vérifie que JLC2KiCadLib est installé et accessible dans le PATH.
    Retourne (True, version) ou (False, message_erreur).
    """
    try:
        result = subprocess.run(
            ["JLC2KiCadLib", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        version = (result.stdout or result.stderr or "").strip().splitlines()
        version_str = version[0] if version else "version inconnue"
        return True, version_str
    except FileNotFoundError:
        return False, "JLC2KiCadLib introuvable — installe-le avec : pip install JLC2KiCadLib"
    except subprocess.TimeoutExpired:
        return False, "JLC2KiCadLib ne répond pas"
    except Exception as e:
        return False, str(e)


# ------------------------------------------------------------------ #
#  Job principal (thread daemon)
# ------------------------------------------------------------------ #

def start_job(lcsc_refs: list[str], kicad_dir: str, delay: float = 2.0, prefix: str = "") -> bool:
    """
    Lance le job de génération en arrière-plan.
    Retourne False si un job est déjà en cours.
    """
    with _job_lock:
        if _state["running"]:
            return False
        _state.update({
            "running": True,
            "total":   len(lcsc_refs),
            "current": 0,
            "ref":     "",
            "log":     [],
            "done":    False,
        })

    def _run():
        os.makedirs(kicad_dir, exist_ok=True)
        for i, ref in enumerate(lcsc_refs):
            with _job_lock:
                _state["current"] = i + 1
                _state["ref"]     = ref

            _download_one(ref, kicad_dir, prefix=prefix)

            if i < len(lcsc_refs) - 1:
                time.sleep(delay)

        with _job_lock:
            _state["running"] = False
            _state["done"]    = True
        logger.info("[KiCad] Job terminé — %d composants traités.", len(lcsc_refs))

    threading.Thread(target=_run, daemon=True).start()
    return True


# ------------------------------------------------------------------ #
#  Stats de la librairie générée
# ------------------------------------------------------------------ #

def get_library_stats(kicad_dir: str) -> dict:
    """
    Retourne des stats sur les fichiers individuels générés dans kicad_dir.
    Ne compte QUE les dossiers composant (ex: instance/kicad/Resistors/C12345/).
    Exclut les fichiers fusionnés (*.kicad_sym catégorie, .pretty/, packages3d/).
    """
    n_sym = 0
    n_fp  = 0
    n_m3d = 0

    if not os.path.isdir(kicad_dir):
        return {"n_sym": 0, "n_fp": 0, "n_m3d": 0, "has_files": False}

    for cat_name in os.listdir(kicad_dir):
        cat_dir = os.path.join(kicad_dir, cat_name)
        if not os.path.isdir(cat_dir):
            continue
        for comp_name in os.listdir(cat_dir):
            comp_dir = os.path.join(cat_dir, comp_name)
            # Ignorer les dossiers fusionnés (.pretty) et les fichiers
            if not os.path.isdir(comp_dir) or comp_name.endswith(".pretty"):
                continue
            for fname in os.listdir(comp_dir):
                if fname.endswith(".kicad_sym"):
                    n_sym += 1
                elif fname.endswith(".kicad_mod"):
                    n_fp  += 1
                elif fname.endswith((".step", ".wrl")):
                    n_m3d += 1

    return {
        "n_sym":     n_sym,
        "n_fp":      n_fp,
        "n_m3d":     n_m3d,
        "has_files": (n_sym + n_fp + n_m3d) > 0,
    }


# ------------------------------------------------------------------ #
#  Fusion des symboles par catégorie
# ------------------------------------------------------------------ #

def _extract_symbol_blocks(kicad_sym_path: str) -> list[str]:
    """
    Extrait les blocs (symbol ...) de premier niveau d'un fichier .kicad_sym.
    Retourne une liste de chaînes, chacune étant un bloc symbol complet.
    """
    try:
        with open(kicad_sym_path, encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        logger.warning("[KiCad] Impossible de lire %s : %s", kicad_sym_path, e)
        return []

    blocks = []
    i = 0
    n = len(content)

    while i < n:
        # Cherche le début d'un bloc (symbol "..."
        idx = content.find("(symbol ", i)
        if idx == -1:
            break

        # Vérifie que c'est bien un bloc de premier niveau (symbol du composant)
        # et pas un sous-bloc (symbol "NomComposant_0_1")
        # On remonte pour voir si on est dans un bloc parent
        # Compte les parenthèses ouvertes avant idx dans le fichier header
        before = content[:idx]
        depth = before.count("(") - before.count(")")
        if depth != 1:
            # C'est un sous-bloc, on avance
            i = idx + 1
            continue

        # Extrait le bloc complet en comptant les parenthèses
        depth = 0
        start = idx
        j = idx
        while j < n:
            if content[j] == "(":
                depth += 1
            elif content[j] == ")":
                depth -= 1
                if depth == 0:
                    blocks.append(content[start:j + 1])
                    i = j + 1
                    break
            j += 1
        else:
            break

    return blocks


def _patch_footprint_link(block: str, lib_name: str) -> str:
    """
    Dans un bloc symbole .kicad_sym, remplace le lien footprint générique
    généré par JLC2KiCadLib par le nom de la librairie StockElec.

    JLC2KiCadLib génère typiquement :
        (property "Footprint" "footprint:PDIP-14_L19.7-W6.6-P2.54-LS8.3-BL" ...)
    ou parfois sans préfixe :
        (property "Footprint" "PDIP-14_L19.7-W6.6-P2.54-LS8.3-BL" ...)

    On veut :
        (property "Footprint" "StockElec_Logic:PDIP-14_L19.7-W6.6-P2.54-LS8.3-BL" ...)
    """
    import re

    def replace_fp(m):
        fp_value = m.group(1)
        # Supprimer un éventuel préfixe de lib existant (ex: "footprint:", "KiCad_PCB:")
        if ":" in fp_value:
            fp_name = fp_value.split(":", 1)[1]
        else:
            fp_name = fp_value
        # Ne rien faire si vide ou déjà notre lib
        if not fp_name or fp_value.startswith(lib_name + ":"):
            return m.group(0)
        return m.group(0).replace(
            f'"{fp_value}"',
            f'"{lib_name}:{fp_name}"'
        )

    # Regex : (property "Footprint" "<valeur>"
    patched = re.sub(
        r'\(property\s+"Footprint"\s+"([^"]*)"',
        replace_fp,
        block,
    )
    return patched


def merge_symbols(kicad_dir: str, prefix: str = "", skip_existing: bool = False) -> dict:
    """
    Parcourt instance/kicad/<Categorie>/<Composant>/*.kicad_sym
    et fusionne les symboles de chaque catégorie en un seul fichier
    instance/kicad/<Categorie>/<Categorie>.kicad_sym

    skip_existing : si True, ne pas écraser les .kicad_sym déjà présents
                    (protège les modifications manuelles dans KiCad)
    Retourne un dict de stats : {categorie: n_symboles_fusionnes}
    """
    if not os.path.isdir(kicad_dir):
        return {}

    stats = {}

    # Parcourt chaque dossier catégorie
    for cat_name in sorted(os.listdir(kicad_dir)):
        cat_dir = os.path.join(kicad_dir, cat_name)
        if not os.path.isdir(cat_dir):
            continue

        all_blocks = []

        # Parcourt chaque dossier composant dans la catégorie
        for comp_name in sorted(os.listdir(cat_dir)):
            comp_dir = os.path.join(cat_dir, comp_name)
            if not os.path.isdir(comp_dir):
                continue

            # Cherche les .kicad_sym dans ce dossier composant
            sym_files = glob.glob(os.path.join(comp_dir, "*.kicad_sym"))
            for sym_file in sym_files:
                blocks = _extract_symbol_blocks(sym_file)
                all_blocks.extend(blocks)

        if not all_blocks:
            continue

        # Écrit la librairie fusionnée avec le préfixe
        lib_name = f"{prefix}{cat_name}" if prefix else cat_name
        lib_path = os.path.join(cat_dir, f"{lib_name}.kicad_sym")

        # skip_existing : ne pas écraser les symboles déjà présents dans la lib
        # → on lit les noms déjà fusionnés et on n'ajoute que les nouveaux
        existing_names: set[str] = set()
        if skip_existing and os.path.isfile(lib_path):
            for blk in _extract_symbol_blocks(lib_path):
                m = re.search(r'\(symbol\s+"([^"]+)"', blk)
                if m:
                    existing_names.add(m.group(1))

        # Filtrer : garder seulement les blocs absents de la lib existante
        if existing_names:
            new_blocks = []
            for blk in all_blocks:
                m = re.search(r'\(symbol\s+"([^"]+)"', blk)
                sym_name = m.group(1) if m else ""
                if sym_name not in existing_names:
                    new_blocks.append(blk)

            if not new_blocks:
                # Tout est déjà présent — rien à faire
                logger.info("[KiCad] Lib à jour, rien à ajouter : %s", lib_name)
                stats[cat_name] = 0
                continue

            # Ajouter les nouveaux blocs à la fin du fichier existant
            try:
                with open(lib_path, "r", encoding="utf-8") as f:
                    existing_content = f.read().rstrip()
                # Retirer la parenthèse fermante finale ")"
                if existing_content.endswith(")"):
                    existing_content = existing_content[:-1].rstrip()

                with open(lib_path, "w", encoding="utf-8") as f:
                    f.write(existing_content + "\n")
                    for blk in new_blocks:
                        blk = _patch_footprint_link(blk, lib_name)
                        indented = "\n".join("  " + line if line.strip() else line
                                             for line in blk.splitlines())
                        f.write(indented + "\n")
                    f.write(")\n")

                stats[cat_name] = len(new_blocks)
                logger.info("[KiCad] Lib mise à jour : %s (+%d symboles)", lib_name, len(new_blocks))
            except Exception as e:
                logger.error("[KiCad] Erreur mise à jour librairie %s : %s", lib_path, e)
        else:
            # Pas de lib existante (ou skip_existing=False) → réécriture complète
            try:
                with open(lib_path, "w", encoding="utf-8") as f:
                    f.write("(kicad_symbol_lib (version 20210201) (generator StockEleK)\n")
                    for blk in all_blocks:
                        blk = _patch_footprint_link(blk, lib_name)
                        indented = "\n".join("  " + line if line.strip() else line
                                             for line in blk.splitlines())
                        f.write(indented + "\n")
                    f.write(")\n")
                stats[cat_name] = len(all_blocks)
                logger.info("[KiCad] Librairie fusionnée : %s (%d symboles)", cat_name, len(all_blocks))
            except Exception as e:
                logger.error("[KiCad] Erreur écriture librairie %s : %s", lib_path, e)

    return stats


# ------------------------------------------------------------------ #
#  Vérification fichiers générés pour un composant
# ------------------------------------------------------------------ #

def get_component_kicad_status(lcsc_ref: str, kicad_dir: str) -> dict:
    """
    Vérifie si les fichiers KiCad ont été générés pour un composant donné.
    Retourne un dict :
        {
            "symbol":    True | False,
            "footprint": True | False,
            "model_3d":  True | False,
            "paths": {
                "symbol":    "/chemin/vers/fichier.kicad_sym" | None,
                "footprint": "/chemin/vers/fichier.kicad_mod" | None,
                "model3d":   "/chemin/vers/fichier.step"      | None,
            }
        }
    """
    result = {
        "symbol": False, "footprint": False, "model_3d": False,
        "paths": {"symbol": None, "footprint": None, "model3d": None},
    }
    if not lcsc_ref or not os.path.isdir(kicad_dir):
        return result

    # Cherche le dossier individuel *_<REF>
    comp_dirs = glob.glob(os.path.join(kicad_dir, "*", f"*_{lcsc_ref}"))

    for comp_dir in comp_dirs:
        # Symbole individuel
        syms = glob.glob(os.path.join(comp_dir, "*.kicad_sym"))
        if syms:
            result["symbol"] = True
            result["paths"]["symbol"] = syms[0]
        # Footprint
        fps = glob.glob(os.path.join(comp_dir, "*.kicad_mod"))
        if fps:
            result["footprint"] = True
            result["paths"]["footprint"] = fps[0]
        # Modèle 3D
        m3ds = glob.glob(os.path.join(comp_dir, "*.step")) or \
               glob.glob(os.path.join(comp_dir, "*.wrl"))
        if m3ds:
            result["model_3d"] = True
            result["paths"]["model3d"] = m3ds[0]

    return result


# ------------------------------------------------------------------ #
#  Enregistrement automatique dans KiCad sym-lib-table
# ------------------------------------------------------------------ #

def _find_sym_lib_table() -> str | None:
    """
    Cherche le fichier sym-lib-table global de KiCad.
    Emplacements selon l'OS :
      Windows : %APPDATA%/kicad/<version>/sym-lib-table
      Linux   : ~/.config/kicad/<version>/sym-lib-table
      macOS   : ~/Library/Preferences/kicad/<version>/sym-lib-table
    Retourne le chemin de la version la plus récente trouvée, ou None.
    """
    import sys

    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        base = os.path.join(appdata, "kicad")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Preferences/kicad")
    else:
        base = os.path.expanduser("~/.config/kicad")

    if not os.path.isdir(base):
        return None

    def _version_key(name: str):
        """Tri numérique des dossiers de version (ex: '10.0' > '9.0')."""
        try:
            return tuple(int(x) for x in name.split("."))
        except ValueError:
            return (0,)

    candidates = []

    # Chercher dans les sous-dossiers versionnés, triés du plus récent au plus ancien
    versioned = sorted(
        (e for e in os.listdir(base) if os.path.isdir(os.path.join(base, e))),
        key=_version_key,
        reverse=True,
    )
    for entry in versioned:
        candidate = os.path.join(base, entry, "sym-lib-table")
        if os.path.isfile(candidate):
            candidates.append(candidate)
            logger.debug("[KiCad] sym-lib-table trouvé : %s", candidate)

    # Aussi à la racine (anciennes versions sans sous-dossier)
    root_candidate = os.path.join(base, "sym-lib-table")
    if os.path.isfile(root_candidate):
        candidates.append(root_candidate)

    if not candidates:
        logger.warning("[KiCad] sym-lib-table introuvable dans %s", base)
        return None

    logger.info("[KiCad] sym-lib-table sélectionné : %s", candidates[0])
    return candidates[0]


def register_in_kicad(kicad_dir: str, prefix: str = "") -> dict:
    """
    Ajoute les librairies fusionnées de kicad_dir dans le sym-lib-table global KiCad.
    Crée le fichier s'il n'existe pas encore.
    Ne duplique pas les entrées existantes.

    Retourne :
        {
            "ok": True | False,
            "table_path": "/chemin/sym-lib-table",
            "kicad_version": "10.0",   # version détectée
            "added": ["StockElec_Logic", ...],
            "skipped": ["StockElec_Amplifiers-Comparators"],
            "error": None | "message"
        }
    """
    result = {
        "ok": False, "table_path": None, "kicad_version": None,
        "added": [], "skipped": [], "error": None,
    }

    table_path = _find_sym_lib_table()
    if not table_path:
        result["error"] = "sym-lib-table KiCad introuvable — KiCad est-il installé ?"
        return result

    result["table_path"] = table_path

    # Extraire la version depuis le chemin (ex: .../kicad/10.0/sym-lib-table)
    parts = table_path.replace("\\", "/").split("/")
    if len(parts) >= 2:
        version_candidate = parts[-2]
        try:
            tuple(int(x) for x in version_candidate.split("."))
            result["kicad_version"] = version_candidate
        except ValueError as e:
            logger.debug("Ignored: %s", e)

    table_path = _find_sym_lib_table()
    if not table_path:
        result["error"] = "sym-lib-table KiCad introuvable — KiCad est-il installé ?"
        return result

    result["table_path"] = table_path

    # Lire le contenu actuel
    try:
        with open(table_path, encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        result["error"] = f"Impossible de lire sym-lib-table : {e}"
        return result

    # Construire la liste des librairies fusionnées disponibles
    # Format : kicad_dir/<Categorie>/<prefix><Categorie>.kicad_sym
    new_libs = []
    if os.path.isdir(kicad_dir):
        for cat_name in sorted(os.listdir(kicad_dir)):
            cat_dir = os.path.join(kicad_dir, cat_name)
            if not os.path.isdir(cat_dir):
                continue
            lib_name = f"{prefix}{cat_name}" if prefix else cat_name
            lib_file = os.path.join(cat_dir, f"{lib_name}.kicad_sym")
            if os.path.isfile(lib_file):
                new_libs.append((lib_name, lib_file))

    if not new_libs:
        result["error"] = "Aucune librairie fusionnée trouvée — lancez d'abord la fusion."
        return result

    # Parser et mettre à jour le sym-lib-table
    # Format KiCad :
    # (sym_lib_table
    #   (lib (name "NomLib")(type "KiCad")(uri "/chemin/fichier.kicad_sym")(options "")(descr ""))
    # )
    for lib_name, lib_path in new_libs:
        # Normaliser le chemin (slashes)
        lib_path_normalized = lib_path.replace("\\", "/")

        # Vérifier si déjà présente (par nom)
        if f'(name "{lib_name}")' in content:
            result["skipped"].append(lib_name)
            logger.info("[KiCad] Librairie déjà enregistrée : %s", lib_name)
            continue

        # Construire l'entrée
        entry = (
            f'  (lib (name "{lib_name}")'
            f'(type "KiCad")'
            f'(uri "{lib_path_normalized}")'
            f'(options "")'
            f'(descr "StockEleK — {lib_name}"))\n'
        )

        # Insérer avant la dernière parenthèse fermante
        if content.rstrip().endswith(")"):
            content = content.rstrip()[:-1].rstrip() + "\n" + entry + ")\n"
        else:
            # Fichier vide ou mal formé — recréer
            content = "(sym_lib_table\n" + entry + ")\n"

        result["added"].append(lib_name)
        logger.info("[KiCad] Librairie enregistrée : %s → %s", lib_name, lib_path_normalized)

    # Écrire le fichier mis à jour
    try:
        with open(table_path, "w", encoding="utf-8") as f:
            f.write(content)
        result["ok"] = True
        logger.info("[KiCad] sym-lib-table mis à jour : %d ajoutées, %d ignorées",
                    len(result["added"]), len(result["skipped"]))
    except Exception as e:
        result["error"] = f"Impossible d'écrire sym-lib-table : {e}"

    return result


# ------------------------------------------------------------------ #
#  Fusion des footprints par catégorie → dossiers .pretty
# ------------------------------------------------------------------ #

def merge_footprints(kicad_dir: str, prefix: str = "", skip_existing: bool = False) -> dict:
    """
    Parcourt instance/kicad/<Categorie>/<Composant>/*.kicad_mod + *.step/*.wrl
    et copie dans instance/kicad/<Categorie>/<prefix><Categorie>.pretty/ :
      - les .kicad_mod directement dans le .pretty/
      - les .step/.wrl dans .pretty/packages3d/

    skip_existing : si True, ne pas écraser les .kicad_mod déjà présents
                    dans le .pretty/ (protège les modifications manuelles)
    Les doublons sont ignorés — on garde le premier.
    Retourne un dict de stats : {categorie: {"fp": n, "3d": n}}
    """
    if not os.path.isdir(kicad_dir):
        return {}

    stats = {}

    for cat_name in sorted(os.listdir(kicad_dir)):
        cat_dir = os.path.join(kicad_dir, cat_name)
        if not os.path.isdir(cat_dir):
            continue

        lib_name    = f"{prefix}{cat_name}" if prefix else cat_name
        pretty_dir  = os.path.join(cat_dir, f"{lib_name}.pretty")
        pkg3d_dir   = os.path.join(pretty_dir, "packages3d")
        os.makedirs(pretty_dir, exist_ok=True)
        os.makedirs(pkg3d_dir,  exist_ok=True)

        copied_fp = set()
        copied_3d = set()
        n_fp = 0
        n_3d = 0

        for comp_name in sorted(os.listdir(cat_dir)):
            comp_dir = os.path.join(cat_dir, comp_name)
            if not os.path.isdir(comp_dir) or comp_dir == pretty_dir:
                continue

            for fname in os.listdir(comp_dir):
                src = os.path.join(comp_dir, fname)

                # ── Footprints → directement dans .pretty/ ────────
                if fname.endswith(".kicad_mod"):
                    if fname in copied_fp:
                        continue
                    dst = os.path.join(pretty_dir, fname)
                    # skip_existing : ne pas écraser les .kicad_mod existants
                    # (protège les modifications manuelles de footprints)
                    if skip_existing and os.path.isfile(dst):
                        copied_fp.add(fname)  # déjà présent, on skip
                        continue
                    try:
                        shutil.copy2(src, dst)
                        copied_fp.add(fname)
                        n_fp += 1
                    except Exception as e:
                        logger.warning("[KiCad] Erreur copie fp %s : %s", fname, e)

                # ── Modèles 3D → dans .pretty/packages3d/ ─────────
                elif fname.endswith((".step", ".wrl")):
                    if fname in copied_3d:
                        continue
                    dst = os.path.join(pkg3d_dir, fname)
                    try:
                        shutil.copy2(src, dst)
                        copied_3d.add(fname)
                        n_3d += 1
                    except Exception as e:
                        logger.warning("[KiCad] Erreur copie 3D %s : %s", fname, e)

        if n_fp > 0 or n_3d > 0:
            stats[cat_name] = {"fp": n_fp, "3d": n_3d}
            logger.info("[KiCad] %s : %d fp, %d 3D", lib_name, n_fp, n_3d)

    return stats


# ------------------------------------------------------------------ #
#  Enregistrement des footprints dans fp-lib-table
# ------------------------------------------------------------------ #

def _find_fp_lib_table() -> str | None:
    """
    Cherche le fp-lib-table global de KiCad (même logique que sym-lib-table).
    """
    import sys

    if sys.platform == "win32":
        base = os.path.join(os.environ.get("APPDATA", ""), "kicad")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Preferences/kicad")
    else:
        base = os.path.expanduser("~/.config/kicad")

    if not os.path.isdir(base):
        return None

    def _version_key(name):
        try: return tuple(int(x) for x in name.split("."))
        except ValueError: return (0,)

    versioned = sorted(
        (e for e in os.listdir(base) if os.path.isdir(os.path.join(base, e))),
        key=_version_key, reverse=True,
    )
    for entry in versioned:
        candidate = os.path.join(base, entry, "fp-lib-table")
        if os.path.isfile(candidate):
            logger.info("[KiCad] fp-lib-table trouvé : %s", candidate)
            return candidate

    root = os.path.join(base, "fp-lib-table")
    return root if os.path.isfile(root) else None


def register_footprints_in_kicad(kicad_dir: str, prefix: str = "") -> dict:
    """
    Ajoute les librairies .pretty dans le fp-lib-table global KiCad.
    Ne duplique pas les entrées existantes.
    """
    result = {
        "ok": False, "table_path": None, "kicad_version": None,
        "added": [], "skipped": [], "error": None,
    }

    table_path = _find_fp_lib_table()
    if not table_path:
        result["error"] = "fp-lib-table KiCad introuvable — KiCad est-il installé ?"
        return result

    result["table_path"] = table_path

    # Extraire la version depuis le chemin
    parts = table_path.replace("\\", "/").split("/")
    if len(parts) >= 2:
        try:
            tuple(int(x) for x in parts[-2].split("."))
            result["kicad_version"] = parts[-2]
        except ValueError as e:
            logger.debug("Ignored: %s", e)

    # Lire le contenu actuel (ou créer un fichier vide)
    if os.path.isfile(table_path):
        try:
            with open(table_path, encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            result["error"] = f"Impossible de lire fp-lib-table : {e}"
            return result
    else:
        content = "(fp_lib_table\n)\n"

    # Trouver tous les dossiers .pretty disponibles
    new_libs = []
    if os.path.isdir(kicad_dir):
        for cat_name in sorted(os.listdir(kicad_dir)):
            cat_dir = os.path.join(kicad_dir, cat_name)
            if not os.path.isdir(cat_dir):
                continue
            lib_name   = f"{prefix}{cat_name}" if prefix else cat_name
            pretty_dir = os.path.join(cat_dir, f"{lib_name}.pretty")
            if os.path.isdir(pretty_dir):
                new_libs.append((lib_name, pretty_dir))

    if not new_libs:
        result["error"] = "Aucun dossier .pretty trouvé — lancez d'abord la fusion des footprints."
        return result

    for lib_name, pretty_path in new_libs:
        pretty_path_normalized = pretty_path.replace("\\", "/")

        if f'(name "{lib_name}")' in content:
            result["skipped"].append(lib_name)
            logger.info("[KiCad] Footprint lib déjà enregistrée : %s", lib_name)
            continue

        entry = (
            f'  (lib (name "{lib_name}")'
            f'(type "KiCad")'
            f'(uri "{pretty_path_normalized}")'
            f'(options "")'
            f'(descr "StockEleK — {lib_name}"))\n'
        )

        if content.rstrip().endswith(")"):
            content = content.rstrip()[:-1].rstrip() + "\n" + entry + ")\n"
        else:
            content = "(fp_lib_table\n" + entry + ")\n"

        result["added"].append(lib_name)
        logger.info("[KiCad] Footprint lib enregistrée : %s", lib_name)

    try:
        with open(table_path, "w", encoding="utf-8") as f:
            f.write(content)
        result["ok"] = True
        logger.info("[KiCad] fp-lib-table mis à jour : %d ajoutées, %d ignorées",
                    len(result["added"]), len(result["skipped"]))
    except Exception as e:
        result["error"] = f"Impossible d'écrire fp-lib-table : {e}"

    return result
