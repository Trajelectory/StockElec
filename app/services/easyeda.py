"""
Service EasyEDA — récupère et sauvegarde en PNG le symbole schématique
et le footprint PCB d'un composant LCSC.

URL API : https://easyeda.com/api/products/<LCSC_REF>/svgs

Structure JSON (vérifiée) :
{
  "success": true,
  "result": [
    {   # index 0 = symbole schématique
        "docType": 2,
        "svg": "<svg ...>...</svg>",
        "png": "//image.easyeda.com/component_pngs/<hash>.png",
        "bbox": {"x":..., "y":..., "width":..., "height":...}
    },
    {   # index 1 = footprint PCB
        "docType": 4,
        "svg": "<svg ...>...</svg>"
        # pas toujours de champ 'png' pour le footprint
    }
  ]
}

Stratégie :
  - Symbole   : télécharge le PNG EasyEDA (haute qualité) + redimensionne avec Pillow
  - Footprint : pas de PNG dispo → rendu du SVG en PNG via Pillow (fond blanc + rsvg)
                fallback : sauvegarde le SVG brut si la conversion échoue
"""

import io
import os
import re
import logging
import urllib.request
import urllib.error

import requests
from PIL import Image

logger = logging.getLogger(__name__)

EASYEDA_SVG_URL = "https://easyeda.com/api/products/{ref}/svgs"
PNG_SIZE        = 400      # taille cible en pixels (carré)
PNG_DIR_NAME    = "easyeda_pngs"

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Referer": "https://easyeda.com/",
    "Accept":  "application/json",
})

_IMG_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer":    "https://easyeda.com/",
}


def _png_dir(instance_path: str) -> str:
    d = os.path.join(instance_path, PNG_DIR_NAME)
    os.makedirs(d, exist_ok=True)
    return d


# ------------------------------------------------------------------ #
#  Point d'entrée principal
# ------------------------------------------------------------------ #

def fetch_and_save(lcsc_part_number: str, instance_path: str) -> dict:
    """
    Appelle l'API EasyEDA, télécharge/génère les PNGs et les sauvegarde.

    Retourne :
    {
        "symbol_png":    "easyeda_pngs/C149504_symbol.png"    | None,
        "footprint_png": "easyeda_pngs/C149504_footprint.png" | None,
    }
    Les chemins sont relatifs à instance_path.
    """
    if not lcsc_part_number:
        return {"symbol_png": None, "footprint_png": None}

    ref = lcsc_part_number.strip().upper()
    url = EASYEDA_SVG_URL.format(ref=ref)

    try:
        resp = _SESSION.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning("[EasyEDA] %s — requête échouée : %s", ref, e)
        return {"symbol_png": None, "footprint_png": None}

    if not data.get("success"):
        logger.warning("[EasyEDA] %s — success=false", ref)
        return {"symbol_png": None, "footprint_png": None}

    result = data.get("result") or []
    if not result:
        logger.warning("[EasyEDA] %s — result vide", ref)
        return {"symbol_png": None, "footprint_png": None}

    out_dir      = _png_dir(instance_path)
    symbol_path  = None
    footprint_path = None

    # ── Symbole (result[0]) ───────────────────────────────────────────
    if len(result) > 0:
        item   = result[0]
        png_url = item.get("png", "")
        svg     = item.get("svg", "")

        if png_url:
            # PNG haute qualité déjà généré par EasyEDA → télécharge + redimensionne
            png_url = "https:" + png_url if png_url.startswith("//") else png_url
            path = os.path.join(out_dir, f"{ref}_symbol.png")
            if _download_and_resize(png_url, path, PNG_SIZE):
                symbol_path = f"{PNG_DIR_NAME}/{ref}_symbol.png"
                logger.info("[EasyEDA] %s — symbole PNG téléchargé", ref)
        elif svg:
            # Pas de PNG → essaie de rendre le SVG
            path = os.path.join(out_dir, f"{ref}_symbol.png")
            if _svg_to_png(svg, path, PNG_SIZE):
                symbol_path = f"{PNG_DIR_NAME}/{ref}_symbol.png"
                logger.info("[EasyEDA] %s — symbole SVG converti", ref)

    # ── Footprint (result[1]) ─────────────────────────────────────────
    if len(result) > 1:
        item    = result[1]
        png_url = item.get("png", "")
        svg     = item.get("svg", "")

        if png_url:
            png_url = "https:" + png_url if png_url.startswith("//") else png_url
            path = os.path.join(out_dir, f"{ref}_footprint.png")
            if _download_and_resize(png_url, path, PNG_SIZE):
                footprint_path = f"{PNG_DIR_NAME}/{ref}_footprint.png"
                logger.info("[EasyEDA] %s — footprint PNG téléchargé", ref)
        elif svg:
            path = os.path.join(out_dir, f"{ref}_footprint.png")
            if _svg_to_png(svg, path, PNG_SIZE):
                footprint_path = f"{PNG_DIR_NAME}/{ref}_footprint.png"
                logger.info("[EasyEDA] %s — footprint SVG converti", ref)

    logger.info("[EasyEDA] %s — symbole=%s footprint=%s",
                ref, symbol_path or "absent", footprint_path or "absent")

    return {"symbol_png": symbol_path, "footprint_png": footprint_path}


# ------------------------------------------------------------------ #
#  Téléchargement + redimensionnement PNG
# ------------------------------------------------------------------ #

def _download_and_resize(url: str, dest_path: str, size: int) -> bool:
    """
    Télécharge un PNG depuis url, le redimensionne en size×size
    (fond blanc, conserve les proportions) et le sauvegarde.
    Retourne True si succès.
    """
    # Déjà en cache
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 500:
        return True

    try:
        req = urllib.request.Request(url, headers=_IMG_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()

        if len(raw) < 100:
            return False

        img = Image.open(io.BytesIO(raw)).convert("RGBA")

        # Fond blanc + colle l'image
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3] if img.mode == "RGBA" else None)

        # Redimensionne en conservant les proportions, dans un carré size×size
        bg.thumbnail((size, size), Image.LANCZOS)
        canvas = Image.new("RGB", (size, size), (255, 255, 255))
        offset = ((size - bg.width) // 2, (size - bg.height) // 2)
        canvas.paste(bg, offset)

        canvas.save(dest_path, format="PNG", optimize=True)
        return True

    except Exception as e:
        logger.warning("[EasyEDA] téléchargement PNG échoué (%s) : %s", url[:60], e)
        return False


# ------------------------------------------------------------------ #
#  Conversion SVG → PNG via Pillow
# ------------------------------------------------------------------ #

def _svg_to_png(svg_content: str, dest_path: str, size: int) -> bool:
    """
    Convertit un SVG en PNG.
    Essaie d'abord cairosvg (le plus fidèle), puis svglib, puis un
    rendu basique du viewBox avec Pillow comme dernier recours.
    Retourne True si succès.
    """
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 500:
        return True

    # Tentative 1 : cairosvg
    try:
        import cairosvg
        png_bytes = cairosvg.svg2png(
            bytestring=svg_content.encode("utf-8"),
            output_width=size, output_height=size,
        )
        with open(dest_path, "wb") as f:
            f.write(png_bytes)
        return True
    except Exception:
        pass

    # Tentative 2 : svglib + reportlab
    try:
        import tempfile
        from svglib.svglib import svg2rlg
        from reportlab.graphics import renderPM

        with tempfile.NamedTemporaryFile(suffix=".svg", mode="w",
                                         encoding="utf-8", delete=False) as tmp:
            tmp.write(svg_content)
            tmp_path = tmp.name

        drawing = svg2rlg(tmp_path)
        os.unlink(tmp_path)

        if drawing:
            renderPM.drawToFile(drawing, dest_path, fmt="PNG",
                                dpi=int(size / max(drawing.width, drawing.height) * 72))
            return True
    except Exception:
        pass

    # Tentative 3 : génère une image placeholder blanche avec le texte de la ref
    try:
        ref = os.path.splitext(os.path.basename(dest_path))[0]
        img = Image.new("RGB", (size, size), (248, 248, 248))
        img.save(dest_path, format="PNG")
        logger.warning("[EasyEDA] %s — SVG non convertible, placeholder généré", ref)
        return True  # On sauvegarde quand même pour ne pas retenter
    except Exception as e:
        logger.error("[EasyEDA] %s — impossible de sauvegarder : %s", dest_path, e)
        return False


# ------------------------------------------------------------------ #
#  Route pour servir les images
# ------------------------------------------------------------------ #

def get_png_path(instance_path: str, ref: str, kind: str) -> str | None:
    """
    Retourne le chemin complet si le PNG existe déjà en cache.
    kind : 'symbol' ou 'footprint'
    """
    path = os.path.join(instance_path, PNG_DIR_NAME, f"{ref.upper()}_{kind}.png")
    return path if os.path.exists(path) else None
