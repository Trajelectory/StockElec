"""
Scraper pour l'endpoint interne LCSC.
URL : https://wmsc.lcsc.com/ftps/wm/product/detail?productCode=<CXXXXXX>

Structure JSON réelle (vérifiée) :
{
  "code": 200,
  "ok": true,
  "result": {
    "productCode":        "C149504",
    "productModel":       "0805W8F1003T5E",
    "brandNameEn":        "UNI-ROYAL",
    "parentCatalogId":    308,
    "parentCatalogName":  "Resistors",
    "catalogId":          1199,
    "catalogName":        "Chip Resistor - Surface Mount",
    "parentCatalogList":  [
        {"catalogId": 30,  "catalogNameEn": "Passives"},
        {"catalogId": 501, "catalogNameEn": "Resistors"}
    ],
    "productImages": [
        "https://assets.lcsc.com/images/lcsc/900x900/...front.jpg",
        "https://assets.lcsc.com/images/lcsc/900x900/...back.jpg"
    ],
    "pdfUrl": "https://datasheet.lcsc.com/..."
  }
}
"""

import os
import time
import random
import urllib.request
import logging

import requests

logger = logging.getLogger(__name__)

LCSC_DETAIL_URL = "https://wmsc.lcsc.com/ftps/wm/product/detail"
IMAGES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "instance", "images")
)

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Referer":         "https://www.lcsc.com/",
    "Origin":          "https://www.lcsc.com",
})


# ------------------------------------------------------------------ #
#  Requête brute
# ------------------------------------------------------------------ #

def fetch_product(lcsc_part_number: str) -> dict | None:
    """
    Appelle l'endpoint et retourne le dict result{},
    ou None en cas d'échec.
    """
    try:
        resp = _SESSION.get(
            LCSC_DETAIL_URL,
            params={"productCode": lcsc_part_number},
            timeout=15,
        )
        resp.raise_for_status()
        payload = resp.json()

        # Structure réelle : {"code": 200, "ok": true, "result": {...}}
        if payload.get("code") == 200 and payload.get("ok"):
            return payload.get("result") or {}

        logger.warning("[LCSC] %s — code inattendu : %s", lcsc_part_number, payload.get("code"))

    except requests.exceptions.Timeout:
        logger.warning("[LCSC] %s — timeout", lcsc_part_number)
    except requests.exceptions.HTTPError as e:
        logger.warning("[LCSC] %s — HTTP %s", lcsc_part_number, e.response.status_code)
    except requests.exceptions.RequestException as e:
        logger.warning("[LCSC] %s — réseau : %s", lcsc_part_number, e)
    except ValueError as e:
        logger.warning("[LCSC] %s — JSON invalide : %s", lcsc_part_number, e)

    return None


# ------------------------------------------------------------------ #
#  Extraction des champs utiles
# ------------------------------------------------------------------ #

def extract_info(result: dict) -> dict:
    """
    Extrait depuis result{} tous les champs utiles.
    """
    if not result:
        return {}

    info = {}

    # Description / titre du composant — productNameEn en priorité (le plus précis)
    for key in ("productNameEn", "productIntroEn", "productDescEn", "productName"):
        if result.get(key):
            info["description"] = result[key]
            break

    # Description longue (productDescEn — contexte complet type "Red 1 Character Common Anode...")
    for key in ("productDescEn", "productIntroEn"):
        val = result.get(key, "")
        if val and val != info.get("description"):
            info["description_long"] = val
            break

    # Référence fabricant (MPN)
    if result.get("productModel"):
        info["manufacture_part_number"] = result["productModel"]

    # Fabricant
    for key in ("brandNameEn", "brandName", "manufacturerNameEn"):
        if result.get(key):
            info["manufacturer"] = result[key]
            break

    # Package / boîtier
    for key in ("encapStandard", "encap", "packageName", "package"):
        if result.get(key):
            info["package"] = result[key]
            break

    # RoHS
    if result.get("rohs") is not None:
        info["rohs"] = "YES" if result["rohs"] else "NO"

    # Catégorie directe (niveau feuille)
    if result.get("catalogName"):
        info["category_name"]   = result["catalogName"]
    if result.get("catalogId"):
        info["category_id"]     = result["catalogId"]

    # Catégorie parente
    if result.get("parentCatalogName"):
        info["parent_category_name"] = result["parentCatalogName"]
    if result.get("parentCatalogId"):
        info["parent_category_id"]   = result["parentCatalogId"]

    # Arborescence complète
    breadcrumb = result.get("parentCatalogList") or []
    if breadcrumb:
        info["breadcrumb"] = [
            {"id": c.get("catalogId"), "name": c.get("catalogNameEn", "")}
            for c in breadcrumb
        ]

    # Image — face avant (index 0)
    images = result.get("productImages") or []
    if isinstance(images, list) and images:
        info["image_url"] = images[0]
    elif isinstance(images, str) and images:
        info["image_url"] = images

    # Prix unitaire — palier le plus bas (quantité minimale)
    price_list = result.get("productPriceList") or result.get("priceList") or []
    if price_list and isinstance(price_list, list):
        # Trie par ladder (quantité) et prend le prix du palier 1
        try:
            sorted_prices = sorted(price_list, key=lambda x: x.get("ladder", 0) or x.get("quantity", 0))
            first = sorted_prices[0]
            price = first.get("price") or first.get("usdPrice") or first.get("productPrice")
            if price:
                info["unit_price"] = round(float(price), 6)
        except (IndexError, KeyError, TypeError, ValueError):
            pass

    # Key Attributes (caractéristiques techniques)
    # Stockés dans productNameEn sous forme "Clé:Valeur Clé:Valeur..."
    # ou dans paramVOList sous forme [{"paramNameEn": ..., "paramValueEn": ...}]
    params = result.get("paramVOList") or result.get("paramList") or []
    if params and isinstance(params, list):
        attrs = {}
        for p in params:
            name  = p.get("paramNameEn") or p.get("paramName") or ""
            value = p.get("paramValueEn") or p.get("paramValue") or ""
            if name and value:
                attrs[name] = value
        if attrs:
            info["attributes"] = attrs

    # Datasheet
    if result.get("pdfUrl"):
        info["datasheet_url"] = result["pdfUrl"]

    return {k: v for k, v in info.items() if v not in (None, "", [])}


# ------------------------------------------------------------------ #
#  Téléchargement de l'image
# ------------------------------------------------------------------ #

def download_image(image_url: str, lcsc_part_number: str) -> str | None:
    """
    Télécharge l'image dans instance/images/<CXXXXXX>.jpg
    Retourne le chemin relatif "images/<filename>" ou None si échec.
    """
    if not image_url:
        return None

    os.makedirs(IMAGES_DIR, exist_ok=True)

    # Extension depuis l'URL (sans query string)
    clean_url = image_url.split("?")[0]
    ext = os.path.splitext(clean_url)[-1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        ext = ".jpg"

    filename = f"{lcsc_part_number}{ext}"
    filepath = os.path.join(IMAGES_DIR, filename)

    # Ne re-télécharge pas si déjà présent
    if os.path.exists(filepath):
        logger.debug("[LCSC] %s — image déjà en cache", lcsc_part_number)
        return f"images/{filename}"

    try:
        req = urllib.request.Request(
            image_url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer":    "https://www.lcsc.com/",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            content = response.read()

        if len(content) < 500:          # image trop petite = probablement une erreur
            logger.warning("[LCSC] %s — image trop petite (%d o), ignorée", lcsc_part_number, len(content))
            return None

        with open(filepath, "wb") as f:
            f.write(content)

        logger.info("[LCSC] %s — image téléchargée (%d Ko)", lcsc_part_number, len(content) // 1024)
        return f"images/{filename}"

    except Exception as e:
        logger.warning("[LCSC] %s — échec téléchargement image : %s", lcsc_part_number, e)
        return None


# ------------------------------------------------------------------ #
#  Fonction principale
# ------------------------------------------------------------------ #

def search_by_mpn(mpn: str) -> dict | None:
    """
    Recherche un composant LCSC par MPN (Manufacturer Part Number).
    Retourne le dict result{} complet (même format que fetch_product) ou None.
    Utilisé pour le double enrichissement Mouser→LCSC.

    Stratégie :
      1. Recherche dans la liste LCSC par keyword (MPN)
      2. Récupère le productCode du premier résultat correspondant
      3. Appelle fetch_product avec ce code pour avoir la structure complète
    """
    if not mpn or len(mpn) < 4:
        return None
    try:
        # Endpoint de recherche par keyword
        resp = _SESSION.get(
            "https://wmsc.lcsc.com/ftps/wm/product/list",
            params={"keyword": mpn, "currentPage": 1, "pageSize": 8},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if not (data.get("code") == 200 and data.get("ok")):
            logger.debug("[LCSC] search_by_mpn %s — code inattendu: %s", mpn, data.get("code"))
            return None

        result = data.get("result") or {}
        # L'endpoint list peut retourner les produits sous différentes clés
        products = (result.get("productList")
                    or result.get("list")
                    or result.get("products")
                    or [])
        if not products:
            logger.debug("[LCSC] search_by_mpn %s — aucun résultat", mpn)
            return None

        # Cherche correspondance exacte sur productModel (MPN)
        product_code = None
        for p in products:
            pm = str(p.get("productModel") or p.get("mpn") or "")
            if pm.upper() == mpn.upper():
                product_code = p.get("productCode") or p.get("lcscPartNumber")
                break
        # Fallback : premier résultat
        if not product_code:
            p = products[0]
            product_code = p.get("productCode") or p.get("lcscPartNumber")

        if not product_code:
            logger.debug("[LCSC] search_by_mpn %s — productCode introuvable dans les résultats", mpn)
            return None

        logger.debug("[LCSC] search_by_mpn %s → %s — appel detail", mpn, product_code)
        # Appel detail pour avoir la structure complète (attributs, images, etc.)
        return fetch_product(str(product_code))

    except Exception as e:
        logger.debug("[LCSC] search_by_mpn %s : %s", mpn, e)
        return None


def enrich_component(lcsc_part_number: str) -> dict:
    """
    Scrape LCSC pour un composant et télécharge son image.

    Retourne un dict avec tout ce qu'on a pu récupérer :
      category_name, parent_category_name, category_id, parent_category_id,
      breadcrumb, image_url, image_path, datasheet_url
    """
    if not lcsc_part_number:
        return {}

    result = fetch_product(lcsc_part_number)
    if result is None:
        return {}

    info = extract_info(result)
    if not info:
        logger.warning("[LCSC] %s — résultat vide après extraction", lcsc_part_number)
        return {}

    # Téléchargement de l'image
    if info.get("image_url"):
        local_path = download_image(info["image_url"], lcsc_part_number)
        if local_path:
            info["image_path"] = local_path
        else:
            logger.warning("[LCSC] %s — image non téléchargée", lcsc_part_number)

    logger.info("[LCSC] %s — enrichi : %s", lcsc_part_number, list(info.keys()))
    return info


# ------------------------------------------------------------------ #
#  Batch avec délai poli
# ------------------------------------------------------------------ #

def enrich_batch(items: list, apply_fn, delay: float = 0.6):
    """
    items    : list of (component_id, lcsc_part_number)
    apply_fn : callable(component_id, enrichment_dict)
    delay    : pause entre requêtes (secondes)
    """
    for comp_id, lcsc_num in items:
        if not lcsc_num:
            continue
        try:
            info = enrich_component(lcsc_num)
            if info:
                apply_fn(comp_id, info)
                logger.info("[LCSC] composant %d enrichi", comp_id)
            else:
                logger.warning("[LCSC] composant %d (%s) — aucune donnée", comp_id, lcsc_num)
        except Exception as e:
            logger.error("[LCSC] composant %d (%s) — exception : %s", comp_id, lcsc_num, e)

        # Pause polie pour ne pas se faire bannir
        time.sleep(delay + random.uniform(0.0, 0.3))
