"""
Service d'accès à l'API officielle LCSC.

Documentation : https://www.lcsc.com/docs/openapi/index.html
Endpoint base  : https://ips.lcsc.com/rest/wmsc2agent/

Authentification :
  signature = sha1("key=<key>&nonce=<nonce>&secret=<secret>&timestamp=<ts>")
  Le timestamp est rejeté si > 60 s par rapport à l'horloge LCSC.
"""

import hashlib
import os
import random
import string
import time
import urllib.request
import urllib.error
from typing import Optional

import requests

# ------------------------------------------------------------------ #
#  Configuration (lue depuis les variables d'environnement ou .env)   #
# ------------------------------------------------------------------ #

LCSC_API_KEY    = os.environ.get("LCSC_API_KEY", "")
LCSC_API_SECRET = os.environ.get("LCSC_API_SECRET", "")
LCSC_BASE_URL   = "https://ips.lcsc.com/rest/wmsc2agent"
IMAGES_DIR      = os.path.join(os.path.dirname(__file__), "..", "..", "instance", "images")


# ------------------------------------------------------------------ #
#  Génération de la signature SHA1 LCSC                               #
# ------------------------------------------------------------------ #

def _nonce(length: int = 16) -> str:
    """Génère une chaîne aléatoire de 16 caractères alphanumériques."""
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choices(chars, k=length))


def _sign(key: str, secret: str, nonce: str, timestamp: int) -> str:
    """
    signature = sha1("key=<key>&nonce=<nonce>&secret=<secret>&timestamp=<ts>")
    Source: https://www.lcsc.com/docs/index.html
    """
    raw = f"key={key}&nonce={nonce}&secret={secret}&timestamp={timestamp}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _auth_params() -> dict:
    """Retourne les 4 paramètres d'authentification prêts à injecter."""
    nonce = _nonce()
    ts    = int(time.time())
    sig   = _sign(LCSC_API_KEY, LCSC_API_SECRET, nonce, ts)
    return {
        "key":       LCSC_API_KEY,
        "nonce":     nonce,
        "timestamp": ts,
        "signature": sig,
    }


# ------------------------------------------------------------------ #
#  Vérification de la disponibilité de l'API                          #
# ------------------------------------------------------------------ #

def is_configured() -> bool:
    """Retourne True si les clés API sont définies."""
    return bool(LCSC_API_KEY and LCSC_API_SECRET)


def reload_config(key: str, secret: str):
    """Met à jour les clés en mémoire (après sauvegarde dans la DB)."""
    global LCSC_API_KEY, LCSC_API_SECRET
    LCSC_API_KEY    = key.strip()
    LCSC_API_SECRET = secret.strip()


# ------------------------------------------------------------------ #
#  Appels API                                                          #
# ------------------------------------------------------------------ #

def get_product_details(lcsc_part_number: str) -> Optional[dict]:
    """
    Appelle getItem Details API et retourne le dict brut LCSC,
    ou None en cas d'erreur.

    GET /rest/wmsc2agent/product/info/{product_number}
    """
    if not is_configured():
        return None

    url = f"{LCSC_BASE_URL}/product/info/{lcsc_part_number}"
    try:
        resp = requests.get(url, params=_auth_params(), timeout=10)
        resp.raise_for_status()
        data = resp.json()
        # L'API LCSC retourne { code: 200, data: {...} }
        if data.get("code") == 200:
            return data.get("data") or data.get("result")
    except Exception:
        pass
    return None


def search_product(lcsc_part_number: str) -> Optional[dict]:
    """
    Fallback : utilise getKeyword Search List API si getItem Details
    ne retourne rien (cas rare).

    GET /rest/wmsc2agent/search/product?keyword=<lcsc_part_number>
    """
    if not is_configured():
        return None

    params = {**_auth_params(), "keyword": lcsc_part_number, "match_type": "exact", "page_size": 1}
    try:
        resp = requests.get(f"{LCSC_BASE_URL}/search/product", params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") == 200:
            items = (data.get("data") or {}).get("list") or []
            return items[0] if items else None
    except Exception:
        pass
    return None


# ------------------------------------------------------------------ #
#  Extraction des informations utiles                                  #
# ------------------------------------------------------------------ #

def extract_enrichment(raw: dict) -> dict:
    """
    Extrait depuis la réponse brute LCSC :
      - category     : chemin de catégorie (ex. "Resistors / Chip Resistors")
      - image_url    : URL de la première image produit
      - datasheet_url: URL de la fiche technique
    """
    if not raw:
        return {}

    result = {}

    # ---- Catégorie ----
    # Selon les versions de l'API, les clés peuvent varier
    cat_path = []
    for key in ("catalogName", "catalog_name", "categoryName", "category_name"):
        if raw.get(key):
            cat_path.append(raw[key])
            break
    for key in ("subCatalogName", "sub_catalog_name", "subCategoryName", "sub_category_name"):
        if raw.get(key):
            cat_path.append(raw[key])
            break
    if cat_path:
        result["category"] = " / ".join(cat_path)

    # ---- Image ----
    # L'API peut retourner images[] ou productImages[] ou productImg
    images = (
        raw.get("productImages")
        or raw.get("images")
        or raw.get("imgUrl")  # parfois c'est une string directe
    )
    if isinstance(images, list) and images:
        img = images[0]
        result["image_url"] = img.get("productImage") or img.get("url") or img if isinstance(img, str) else None
    elif isinstance(images, str) and images:
        result["image_url"] = images
    else:
        # Dernier recours : champ direct
        for key in ("productImg", "product_img", "img", "image"):
            if raw.get(key):
                result["image_url"] = raw[key]
                break

    # ---- Datasheet ----
    for key in ("dataManualUrl", "data_manual_url", "datasheetUrl", "pdfUrl"):
        if raw.get(key):
            result["datasheet_url"] = raw[key]
            break

    return {k: v for k, v in result.items() if v}


# ------------------------------------------------------------------ #
#  Téléchargement de l'image                                           #
# ------------------------------------------------------------------ #

def download_image(image_url: str, lcsc_part_number: str) -> Optional[str]:
    """
    Télécharge l'image dans instance/images/<lcsc_part_number>.<ext>
    Retourne le chemin relatif depuis instance/ ou None si échec.
    """
    if not image_url:
        return None

    os.makedirs(IMAGES_DIR, exist_ok=True)

    # Déduction de l'extension
    clean_url = image_url.split("?")[0]
    ext = os.path.splitext(clean_url)[-1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        ext = ".jpg"

    filename  = f"{lcsc_part_number}{ext}"
    filepath  = os.path.join(IMAGES_DIR, filename)

    # Ne re-télécharge pas si déjà présent
    if os.path.exists(filepath):
        return f"images/{filename}"

    try:
        headers = {"User-Agent": "StockElec/1.0"}
        req = urllib.request.Request(image_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            with open(filepath, "wb") as f:
                f.write(response.read())
        return f"images/{filename}"
    except Exception:
        return None


# ------------------------------------------------------------------ #
#  Fonction principale : enrichissement d'un composant                 #
# ------------------------------------------------------------------ #

def enrich_component(lcsc_part_number: str) -> dict:
    """
    Récupère depuis l'API LCSC la catégorie et l'image pour un composant.
    Retourne un dict avec les champs à mettre à jour (peut être vide).
    """
    if not is_configured() or not lcsc_part_number:
        return {}

    raw = get_product_details(lcsc_part_number)
    if not raw:
        raw = search_product(lcsc_part_number)
    if not raw:
        return {}

    enrichment = extract_enrichment(raw)

    # Téléchargement de l'image
    if enrichment.get("image_url"):
        local_path = download_image(enrichment["image_url"], lcsc_part_number)
        enrichment["image_path"] = local_path

    return enrichment
