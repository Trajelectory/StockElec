"""
Service Mouser — enrichissement via l'API officielle Mouser v1.
Documentation : https://api.mouser.com/api/docs

Endpoint : POST https://api.mouser.com/api/v1/search/partnumber?apiKey=<KEY>

Structure de réponse :
{
  "SearchResults": {
    "NumberOfResult": 1,
    "Parts": [
      {
        "MouserPartNumber": "652-3852A-282101AL",
        "ManufacturerPartNumber": "3852A-282-101AL",
        "Manufacturer": "Bourns",
        "Description": "Resistor Networks & Arrays ...",
        "DataSheetUrl": "https://...",
        "ImagePath": "https://...",
        "Category": "Resistor Networks & Arrays",
        "ProductDetailUrl": "https://...",
        "PriceBreaks": [
          {"Quantity": 1, "Price": "0.46", "Currency": "EUR"}
        ],
        "ProductAttributes": [
          {"AttributeName": "Resistance", "AttributeValue": "100 Ohms"},
          ...
        ]
      }
    ]
  }
}
"""

import os
import logging
import urllib.request

import requests

logger = logging.getLogger(__name__)

MOUSER_API_URL = "https://api.mouser.com/api/v1/search/partnumber"
IMAGES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "instance", "images")
)

_SESSION = requests.Session()
_SESSION.headers.update({
    "Content-Type": "application/json",
    "Accept":       "application/json",
})


def fetch_product(mouser_part_number: str, api_key: str) -> dict | None:
    """
    Appelle l'API Mouser et retourne le premier résultat (dict Part),
    ou None en cas d'échec.
    """
    if not api_key:
        logger.warning("[Mouser] Clé API manquante")
        return None

    try:
        resp = _SESSION.post(
            MOUSER_API_URL,
            params={"apiKey": api_key},
            json={
                "SearchByPartRequest": {
                    "mouserPartNumber":  mouser_part_number.strip(),
                    "partSearchOptions": "Exact",
                }
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        errors = data.get("Errors") or []
        if errors:
            for e in errors:
                logger.warning("[Mouser] %s — erreur API : %s", mouser_part_number, e)
            return None

        parts = (data.get("SearchResults") or {}).get("Parts") or []
        if not parts:
            logger.warning("[Mouser] %s — aucun résultat", mouser_part_number)
            return None

        return parts[0]

    except requests.exceptions.Timeout:
        logger.warning("[Mouser] %s — timeout", mouser_part_number)
    except requests.exceptions.RequestException as e:
        logger.warning("[Mouser] %s — réseau : %s", mouser_part_number, e)
    except ValueError as e:
        logger.warning("[Mouser] %s — JSON invalide : %s", mouser_part_number, e)

    return None


def extract_info(part: dict) -> dict:
    """
    Extrait les champs utiles depuis un résultat Mouser.
    """
    if not part:
        return {}

    info = {}

    # Description
    if part.get("Description"):
        info["description"] = part["Description"]

    # Référence fabricant
    if part.get("ManufacturerPartNumber"):
        info["manufacture_part_number"] = part["ManufacturerPartNumber"]

    # Référence Mouser
    if part.get("MouserPartNumber"):
        info["mouser_part_number"] = part["MouserPartNumber"]

    # Fabricant
    if part.get("Manufacturer"):
        info["manufacturer"] = part["Manufacturer"]

    # Catégorie
    if part.get("Category"):
        info["category_name"] = part["Category"]

    # Datasheet
    if part.get("DataSheetUrl"):
        info["datasheet_url"] = part["DataSheetUrl"]

    # Image
    if part.get("ImagePath"):
        info["image_url"] = part["ImagePath"]

    # Lien produit
    if part.get("ProductDetailUrl"):
        info["product_url"] = part["ProductDetailUrl"]

    # RoHS — champ "ROHSStatus" dans la vraie API Mouser
    rohs = part.get("ROHSStatus") or ""
    if "compliant" in rohs.lower() or "rohs" in rohs.lower():
        info["rohs"] = "YES"

    # Prix — Mouser retourne "1,92 €" (virgule décimale + symbole €)
    price_breaks = part.get("PriceBreaks") or []
    if price_breaks:
        try:
            sorted_prices = sorted(price_breaks, key=lambda x: int(x.get("Quantity", 0)))
            raw_price = sorted_prices[0].get("Price", "")
            # Nettoie : virgule → point, supprime €, espaces
            clean_price = raw_price.replace(",", ".").replace("€", "").replace(" ", "").strip()
            price = float(clean_price)
            if price > 0:
                info["unit_price"] = round(price, 6)
        except (ValueError, IndexError, TypeError):
            pass

    # Attributs — concatène les valeurs si même clé (ex: "Conditionnement": "Reel / Cut Tape")
    attrs_raw = part.get("ProductAttributes") or []
    if attrs_raw:
        attrs = {}
        for a in attrs_raw:
            name  = a.get("AttributeName", "").strip()
            value = a.get("AttributeValue", "").strip()
            if name and value and value not in ("", "-", "N/A"):
                if name in attrs:
                    attrs[name] = f"{attrs[name]} / {value}"
                else:
                    attrs[name] = value
        if attrs:
            info["attributes"] = attrs

    return {k: v for k, v in info.items() if v not in (None, "", [], {})}

def download_image(image_url: str, ref: str) -> str | None:
    """
    Télécharge l'image dans instance/images/<ref>.jpg
    Retourne le chemin relatif "images/<filename>" ou None.
    """
    if not image_url:
        return None

    import urllib.parse
    os.makedirs(IMAGES_DIR, exist_ok=True)

    # Encoder l'URL pour gérer les espaces et caractères de contrôle
    parsed = urllib.parse.urlsplit(image_url)
    safe_url = urllib.parse.urlunsplit(
        parsed._replace(path=urllib.parse.quote(parsed.path, safe="/%"))
    )

    clean_url = safe_url.split("?")[0]
    ext = os.path.splitext(clean_url)[-1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        ext = ".jpg"

    # Préfixe "mouser_" pour éviter les conflits avec les images LCSC
    filename = f"mouser_{ref.replace('/', '_')}{ext}"
    filepath = os.path.join(IMAGES_DIR, filename)

    if os.path.exists(filepath) and os.path.getsize(filepath) > 500:
        # Vérifie que le fichier n'est pas du HTML (image corrompue)
        with open(filepath, "rb") as f:
            header = f.read(15)
        if not header.lstrip().startswith(b"<"):
            return f"images/{filename}"
        # Fichier corrompu — on le supprime et on retélécharge
        os.remove(filepath)

    try:
        req = urllib.request.Request(
            safe_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer":    "https://www.mouser.com/",
                "Accept":     "image/webp,image/apng,image/*,*/*;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            content_type = r.headers.get("Content-Type", "")
            content = r.read()

        # Rejette si pas une image réelle
        if len(content) < 500:
            logger.warning("[Mouser] %s — image trop petite (%d bytes)", ref, len(content))
            return None
        if "text/html" in content_type or content[:15].lstrip().startswith(b"<"):
            logger.warning("[Mouser] %s — réponse HTML reçue à la place de l'image", ref)
            return None

        with open(filepath, "wb") as f:
            f.write(content)

        logger.info("[Mouser] %s — image téléchargée (%d bytes)", ref, len(content))
        return f"images/{filename}"

    except Exception as e:
        logger.warning("[Mouser] %s — échec image : %s", ref, e)
        return None


def enrich_component(mouser_part_number: str, api_key: str) -> dict:
    """
    Point d'entrée principal — scrape Mouser et télécharge l'image.
    Retourne un dict compatible avec ComponentModel.apply_enrichment().
    """
    if not mouser_part_number or not api_key:
        return {}

    part = fetch_product(mouser_part_number, api_key)
    if not part:
        return {}

    info = extract_info(part)
    if not info:
        return {}

    # Télécharge l'image
    if info.get("image_url"):
        local_path = download_image(info["image_url"], mouser_part_number)
        if local_path:
            info["image_path"] = local_path

    # Double enrichissement LCSC si les attributs techniques sont insuffisants
    # (l'API Mouser v1 retourne peu d'attributs comparé au site)
    mpn = info.get("manufacture_part_number", "")
    if mpn and len(info.get("attributes") or {}) < 3:
        try:
            import time
            from . import lcsc_scraper
            time.sleep(0.25)  # délai poli envers LCSC (réduit pour BOM volumineuse)
            lcsc_result = lcsc_scraper.search_by_mpn(mpn)
            if lcsc_result:
                lcsc_info = lcsc_scraper.extract_info(lcsc_result)
                for key in ("attributes", "package", "datasheet_url", "description_long"):
                    if lcsc_info.get(key) and not info.get(key):
                        info[key] = lcsc_info[key]
                if lcsc_info.get("image_url") and not info.get("image_path"):
                    lcsc_code = lcsc_result.get("productCode", mpn)
                    lpath = lcsc_scraper.download_image(lcsc_info["image_url"], lcsc_code)
                    if lpath:
                        info["image_path"] = lpath
                lcsc_code = lcsc_result.get("productCode", "?")
                enriched = [k for k in ("attributes","package","datasheet_url","image_path") if info.get(k)]
                logger.info("[Mouser→LCSC] %s — complété depuis %s : %s",
                            mouser_part_number, lcsc_code, enriched)
            else:
                logger.debug("[Mouser→LCSC] %s — MPN %s introuvable sur LCSC", mouser_part_number, mpn)
        except Exception as e:
            logger.warning("[Mouser→LCSC] %s — échec : %s", mouser_part_number, e)

    logger.info("[Mouser] %s — enrichi : %s", mouser_part_number, list(info.keys()))
    return info
