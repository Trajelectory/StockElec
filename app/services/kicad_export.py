"""
Service KiCad Export — génère des bibliothèques KiCad (.kicad_sym + .pretty/ + .3dshapes/)
à partir des composants LCSC du stock.

Utilise une copie locale d'easyeda2kicad (AGPL-3.0) sans dépendance externe.
Appel Python direct → une seule session HTTP, pas de rate limiting par subprocess.
"""

import os
import json
import logging
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

KICAD_DIR_NAME  = "kicad"
STATUS_FILENAME = "kicad_lib_status.json"
LIB_NAME        = "stockelek"

# Headers navigateur pour passer le filtre 403 EasyEDA
EASYEDA_HEADERS = {
    "Accept-Encoding": "gzip, deflate",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/102.0.5005.167 Electron/19.1.9 Safari/537.36 "
        "EasyEDA-Editor/6.5.46"
    ),
    "Origin": "https://easyeda.com",
    "Referer": "https://easyeda.com/editor",
    "X-Requested-With": "XMLHttpRequest",
}


def _kicad_dir(instance_path: str) -> str:
    d = os.path.join(instance_path, KICAD_DIR_NAME)
    os.makedirs(d, exist_ok=True)
    return d


def _status_path(instance_path: str) -> str:
    return os.path.join(_kicad_dir(instance_path), STATUS_FILENAME)


def get_status(instance_path: str) -> dict:
    path = _status_path(instance_path)
    if os.path.exists(path):
        try:
            return json.load(open(path))
        except Exception:
            pass
    return {
        "generated": False, "n_symbols": 0, "n_footprints": 0, "n_3d": 0,
        "n_failed": 0, "failed_refs": [], "last_update": None,
        "sym_path": None, "fp_path": None,
    }


def _save_status(instance_path: str, status: dict):
    json.dump(status, open(_status_path(instance_path), "w"),
              ensure_ascii=False, indent=2)


class RateLimitError(Exception):
    """Levée quand EasyEDA retourne un 403 ou réponse vide."""
    pass


class NoDataError(Exception):
    """Levée quand le composant n'a pas de symbole/footprint EasyEDA."""
    pass


def _import_libs():
    """Importe les modules easyeda2kicad locaux."""
    import sys
    import urllib.request, urllib.error, gzip as _gzip, ssl as _ssl, json as _json
    services_dir = os.path.dirname(os.path.abspath(__file__))
    if services_dir not in sys.path:
        sys.path.insert(0, services_dir)

    from easyeda2kicad.easyeda.easyeda_api import EasyedaApi, API_ENDPOINT
    from easyeda2kicad.easyeda.easyeda_importer import (
        EasyedaSymbolImporter, EasyedaFootprintImporter, Easyeda3dModelImporter
    )
    from easyeda2kicad.kicad.export_kicad_symbol import ExporterSymbolKicad
    from easyeda2kicad.kicad.export_kicad_footprint import ExporterFootprintKicad
    from easyeda2kicad.kicad.export_kicad_3d_model import Exporter3dModelKicad

    class SmartEasyedaApi(EasyedaApi):
        """Sous-classe qui distingue 403 (rate limit) de no-data (skip définitif)."""

        def get_cad_data_of_component(self, lcsc_id: str) -> dict:
            url = API_ENDPOINT.format(lcsc_id=lcsc_id)
            try:
                req = urllib.request.Request(url, headers=self.headers)
                with urllib.request.urlopen(req, timeout=30,
                                            context=self.ssl_context) as r:
                    raw = r.read()
                    data = _gzip.decompress(raw).decode() \
                           if raw[:2] == b"\x1f\x8b" else raw.decode("utf-8")
                    api_resp = _json.loads(data)

                # 403 déguisé en réponse JSON avec success=false
                if not api_resp:
                    raise RateLimitError(f"{lcsc_id}: réponse vide")

                if api_resp.get("success") is False:
                    # Peut être un composant Pro v2 OU un vrai no-data
                    # On lève NoDataError pour skip propre
                    raise NoDataError(f"{lcsc_id}: success=false (composant Pro ou inexistant)")

                result = api_resp.get("result", {})
                if not result:
                    raise NoDataError(f"{lcsc_id}: result vide")
                return result

            except urllib.error.HTTPError as e:
                if e.code == 403:
                    raise RateLimitError(f"403 sur {lcsc_id}")
                if e.code == 404:
                    raise NoDataError(f"404 sur {lcsc_id}: composant introuvable")
                raise RateLimitError(f"HTTP {e.code} sur {lcsc_id}")
            except urllib.error.URLError as e:
                raise RateLimitError(f"Réseau: {e}")
            except _json.JSONDecodeError:
                raise RateLimitError(f"JSON invalide (probable 403)")

    return (SmartEasyedaApi, EasyedaSymbolImporter, EasyedaFootprintImporter,
            Easyeda3dModelImporter, ExporterSymbolKicad, ExporterFootprintKicad,
            Exporter3dModelKicad)


INDEX_FILENAME = "kicad_index.json"


def _load_index(output_prefix: str) -> dict:
    """Charge l'index lcsc_ref → {sym, fp, 3d} depuis le disque."""
    path = output_prefix + "_" + INDEX_FILENAME
    if os.path.exists(path):
        try:
            return json.load(open(path))
        except Exception:
            pass
    return {}


def _save_index(output_prefix: str, index: dict):
    """Sauvegarde l'index sur le disque."""
    path = output_prefix + "_" + INDEX_FILENAME
    json.dump(index, open(path, "w"), indent=2)


def _check_done(index: dict, ref: str) -> dict:
    """Retourne ce qui est déjà généré pour cette ref selon l'index."""
    entry = index.get(ref, {})
    return {
        "sym": bool(entry.get("sym")),
        "fp":  bool(entry.get("fp")),
        "3d":  bool(entry.get("3d")),
    }


def get_all_status(instance_path: str) -> dict:
    """Retourne le statut de toutes les libs générées, en scannant les sous-dossiers."""
    kicad_dir = _kicad_dir(instance_path)
    result = {}

    def _scan_dir(d: str, label: str):
        for f in os.listdir(d):
            if not f.endswith(".kicad_sym"):
                continue
            lib_name   = f[:-len(".kicad_sym")]
            fp_dir     = os.path.join(d, lib_name + ".pretty")
            shapes_dir = os.path.join(d, lib_name + ".3dshapes")
            n_fp = len(os.listdir(fp_dir)) if os.path.exists(fp_dir) else 0
            n_3d = len([x for x in os.listdir(shapes_dir) if x.endswith(".step")])                    if os.path.exists(shapes_dir) else 0
            result[label] = {
                "sym_path": os.path.join(d, f),
                "fp_path":  fp_dir,
                "n_fp":     n_fp,
                "n_3d":     n_3d,
                "cat_dir":  d,
            }

    if not os.path.exists(kicad_dir):
        return result

    # Scanner racine + sous-dossiers (1 niveau)
    _scan_dir(kicad_dir, "global")
    for entry in os.scandir(kicad_dir):
        if entry.is_dir():
            _scan_dir(entry.path, entry.name)

    return result


def rebuild_index(instance_path: str) -> dict:
    """
    Reconstruit l'index JSON depuis les fichiers réellement présents sur le disque.
    Utile si des fichiers ont été supprimés/ajoutés manuellement.
    """
    kicad_dir = _kicad_dir(instance_path)
    rebuilt = 0

    for entry in os.scandir(kicad_dir):
        if not entry.is_dir():
            continue
        # Trouver le fichier .kicad_sym dans ce sous-dossier
        sym_file = None
        for f in os.listdir(entry.path):
            if f.endswith('.kicad_sym'):
                sym_file = os.path.join(entry.path, f)
                break
        if not sym_file:
            continue

        pretty_dir = os.path.join(entry.path, entry.name + '_stockelek.pretty')                      if False else None
        # Trouver les dossiers pretty et 3dshapes
        pretty_dir  = next((os.path.join(entry.path, f) for f in os.listdir(entry.path)
                            if f.endswith('.pretty')), None)
        shapes_dir  = next((os.path.join(entry.path, f) for f in os.listdir(entry.path)
                            if f.endswith('.3dshapes')), None)

        # Lire le .kicad_sym pour extraire toutes les refs LCSC
        try:
            sym_content = open(sym_file, encoding='utf-8').read()
        except Exception:
            continue

        # Construire un index des footprints et 3D disponibles
        fp_files = set()
        if pretty_dir and os.path.exists(pretty_dir):
            fp_files = set(os.listdir(pretty_dir))

        step_files = set()
        if shapes_dir and os.path.exists(shapes_dir):
            step_files = {f for f in os.listdir(shapes_dir) if f.endswith('.step')}

        # Charger l'index existant et le reconstruire
        lib_name = os.path.splitext(os.path.basename(sym_file))[0]
        prefix   = os.path.join(entry.path, lib_name)
        index    = _load_index(prefix)

        # Pour chaque ref dans l'index, revérifier
        for ref in list(index.keys()):
            has_sym = f'(symbol "{ref}"' in sym_content
            has_fp  = any(ref in f for f in fp_files)
            has_3d  = any(ref in f for f in step_files)
            index[ref] = {"sym": has_sym, "fp": has_fp, "3d": has_3d}

        _save_index(prefix, index)
        rebuilt += 1
        logger.info("[KiCad] Index reconstruit pour %s (%d refs)", entry.name, len(index))

    return {"rebuilt": rebuilt}



def _setup_library_dirs(instance_path: str, lib_suffix: str):
    """Crée les dossiers de sortie et prépare l'environnement KiCad.
    
    Retourne (output_prefix, lib_name, api, index) ou lève ImportError.
    """
    kicad_dir = _kicad_dir(instance_path)
    lib_name  = LIB_NAME + (f"_{lib_suffix}" if lib_suffix else "")

    cat_dir = os.path.join(kicad_dir, lib_suffix) if lib_suffix else kicad_dir
    os.makedirs(cat_dir, exist_ok=True)
    output_prefix = os.path.join(cat_dir, lib_name)

    for d in [output_prefix + ".pretty", output_prefix + ".3dshapes"]:
        os.makedirs(d, exist_ok=True)

    (EasyedaApi, EasyedaSymbolImporter, EasyedaFootprintImporter,
     Easyeda3dModelImporter, ExporterSymbolKicad, ExporterFootprintKicad,
     Exporter3dModelKicad) = _import_libs()

    api = EasyedaApi()
    api.headers = dict(EASYEDA_HEADERS)

    index = _load_index(output_prefix)
    return output_prefix, lib_name, api, index


def generate_library(lcsc_refs: list[str], instance_path: str,
                     progress_cb=None, lib_suffix: str = "") -> dict:
    """
    Génère symboles, footprints et modèles 3D pour une liste de refs LCSC.
    lib_suffix : suffixe optionnel pour la lib (ex: "_resistances")
    """
    if not lcsc_refs:
        return get_status(instance_path)

    try:
        output_prefix, lib_name, api, index = _setup_library_dirs(instance_path, lib_suffix)
    except ImportError as e:
        logger.error("[KiCad] Impossible d'importer easyeda2kicad local: %s", e)
        return get_status(instance_path)

    sym_path    = output_prefix + ".kicad_sym"
    fp_path     = output_prefix + ".pretty"
    shapes_dir  = output_prefix + ".3dshapes"
    n_ok = n_failed = 0
    failed = []

    for i, ref in enumerate(lcsc_refs):
        ref = ref.strip().upper()
        if not ref:
            continue

        if progress_cb:
            progress_cb(i + 1, len(lcsc_refs), ref)

        # Vérifier ce qui est déjà généré via l'index
        done = _check_done(index, ref)
        # On skip si sym ET fp sont déjà générés
        # Le 3D est optionnel (certains composants n'en ont pas)
        need_api = not done["sym"] or not done["fp"]

        if not need_api:
            logger.info("[KiCad] %s — tout déjà généré, skip", ref)
            n_ok += 1
            if progress_cb:
                progress_cb(i + 1, len(lcsc_refs), ref, "skip", "Déjà généré")
            continue

        try:
            # 1. Récupérer les données depuis EasyEDA
            #    RateLimitError (403) → retry exponentiel
            #    NoDataError         → pas de symbole EasyEDA → skip définitif
            cad_data  = None
            skip_ref  = False
            for attempt in range(8):
                try:
                    cad_data = api.get_cad_data_of_component(lcsc_id=ref)
                    break
                except NoDataError as e:
                    logger.info("[KiCad] %s — pas de données EasyEDA, skip: %s", ref, e)
                    if progress_cb:
                        progress_cb(i + 1, len(lcsc_refs), ref, "warn", f"Pas de données EasyEDA")
                    skip_ref = True
                    break
                except RateLimitError:
                    wait = min(15 * (2 ** attempt), 300)
                    logger.warning("[KiCad] %s — rate limit, attente %ds (tentative %d/8)\u2026",
                                   ref, wait, attempt + 1)
                    if progress_cb:
                        progress_cb(i + 1, len(lcsc_refs), ref, "ratelimit", f"Rate limit — attente {wait}s (tentative {attempt+1}/8)")
                    time.sleep(wait)

            if skip_ref or not cad_data:
                if not skip_ref:
                    logger.error("[KiCad] %s — abandon apres 8 tentatives", ref)
            if progress_cb:
                progress_cb(i + 1, len(lcsc_refs), ref, "error", "Abandon après 8 tentatives")
                n_failed += 1
                failed.append(ref)
                continue

            # 2. Symbole (si manquant)
            if not done["sym"]:
                try:
                    sym_importer = EasyedaSymbolImporter(easyeda_cp_cad_data=cad_data)
                    sym = sym_importer.get_symbol()
                    sym_exporter = ExporterSymbolKicad(symbol=sym)
                    sym_exporter.save_to_lib(
                        lib_path=output_prefix + ".kicad_sym",
                        footprint_lib_name=LIB_NAME,
                        overwrite=True,
                    )
                    entry["sym"] = True
                except Exception as e:
                    logger.warning("[KiCad] %s — symbole échoué: %s", ref, e)
                    if progress_cb:
                        progress_cb(i + 1, len(lcsc_refs), ref, "warn",
                                    f"Symbole échoué: {str(e)[:80]}")
            else:
                logger.debug("[KiCad] %s — symbole déjà présent", ref)

            # 3. Footprint (si manquant)
            if not done["fp"]:
                try:
                    fp_importer = EasyedaFootprintImporter(easyeda_cp_cad_data=cad_data)
                    fp = fp_importer.get_footprint()
                    fp_exporter = ExporterFootprintKicad(footprint=fp)
                    fp_name    = fp.info.name if fp.info.name else ref
                    fp_path    = output_prefix + f".pretty/{fp_name}.kicad_mod"
                    fp_3d_path = (output_prefix + f".3dshapes/{fp.info.model_3d_name}"
                                  if fp.info.model_3d_name else "")
                    fp_exporter.export(
                        footprint_full_path=fp_path,
                        model_3d_path=fp_3d_path,
                    )
                    entry["fp"] = True
                except Exception as e:
                    logger.warning("[KiCad] %s — footprint échoué: %s", ref, e)
                    if progress_cb:
                        progress_cb(i + 1, len(lcsc_refs), ref, "warn",
                                    f"Footprint échoué: {str(e)[:80]}")
            else:
                logger.debug("[KiCad] %s — footprint déjà présent", ref)

            # 4. Modèle 3D (si manquant) — seulement .step
            if not done["3d"]:
                try:
                    model_importer = Easyeda3dModelImporter(
                        easyeda_cp_cad_data=cad_data,
                        download_raw_3d_model=True,
                        api=api,
                    )
                    if model_importer.output:
                        model_exporter = Exporter3dModelKicad(model_3d=model_importer.output)
                        model_exporter.export(
                            output_dir=output_prefix + ".3dshapes",
                            overwrite=True,
                        )
                        # Supprimer le .wrl — on garde seulement le .step
                        shapes_dir = output_prefix + ".3dshapes"
                        if os.path.exists(shapes_dir):
                            for f in os.listdir(shapes_dir):
                                if f.endswith(".wrl"):
                                    try:
                                        os.remove(os.path.join(shapes_dir, f))
                                    except Exception:
                                        pass
                except Exception as e:
                    logger.warning("[KiCad] %s — modèle 3D échoué: %s", ref, e)
            else:
                logger.debug("[KiCad] %s — modèle 3D déjà présent", ref)

            # Mettre à jour l'index
            entry = index.get(ref, {})
            if not done["sym"]: entry["sym"] = True
            if not done["fp"]:  entry["fp"]  = True
            # Marquer 3d=True même si aucun fichier .step n'a été généré
            # (composant sans modèle 3D dans EasyEDA) pour éviter les retentatives infinies
            entry["3d"] = True
            index[ref] = entry
            _save_index(output_prefix, index)
            n_ok += 1
            logger.info("[KiCad] %s — OK", ref)
            if progress_cb:
                progress_cb(i + 1, len(lcsc_refs), ref, "ok", "OK")

        except Exception as e:
            n_failed += 1
            failed.append(ref)
            logger.warning("[KiCad] %s — erreur: %s", ref, e)

        # Délai entre composants — léger car on gère les 403 par retry
        time.sleep(2.0)

    sym_path  = output_prefix + ".kicad_sym"
    fp_path   = output_prefix + ".pretty"
    shapes_path = output_prefix + ".3dshapes"
    n_3d = len([f for f in os.listdir(shapes_path) if f.endswith(".step")])            if os.path.exists(shapes_path) else 0

    status = {
        "generated":    os.path.exists(sym_path),
        "n_symbols":    n_ok,
        "n_footprints": n_ok,
        "n_3d":         n_3d,
        "n_failed":     n_failed,
        "failed_refs":  failed[:20],
        "last_update":  datetime.now().isoformat(timespec="seconds"),
        "sym_path":     sym_path   if os.path.exists(sym_path)   else None,
        "fp_path":      fp_path    if os.path.exists(fp_path)    else None,
        "lib_name":     lib_name,
    }
    return status
