"""
Service DigiKey — enrichissement via l'API officielle v4.
Utilise le flow OAuth2 2-legged (Client Credentials) — pas de navigateur requis.

Flow :
  1. POST /v1/oauth2/token → access_token (valable ~30 min)
  2. POST /products/v4/search/keyword → données du composant

Le token est mis en cache en mémoire et renouvelé automatiquement à expiration.
"""

import logging
import time
import os
import urllib.request

import requests

logger = logging.getLogger(__name__)

TOKEN_URL   = "https://api.digikey.com/v1/oauth2/token"
SEARCH_URL   = "https://api.digikey.com/products/v4/search/keyword"
DETAILS_URL  = "https://api.digikey.com/products/v4/search/{part}/productdetails"
IMAGES_DIR  = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "instance", "images")
)

# Cache token en mémoire
_token_cache = {"access_token": None, "expires_at": 0}

_SESSION = requests.Session()
_SESSION.headers.update({"Accept": "application/json"})


def _get_token(client_id: str, client_secret: str) -> str | None:
    """Obtient un access token OAuth2 (2-legged), avec cache."""
    now = time.time()
    if _token_cache["access_token"] and now < _token_cache["expires_at"] - 60:
        return _token_cache["access_token"]

    try:
        resp = requests.post(
            TOKEN_URL,
            data={
                "client_id":     client_id,
                "client_secret": client_secret,
                "grant_type":    "client_credentials",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        token = data.get("access_token")
        expires_in = int(data.get("expires_in", 1800))
        if token:
            _token_cache["access_token"] = token
            _token_cache["expires_at"]   = now + expires_in
            logger.info("[DigiKey] Token obtenu, expire dans %ds", expires_in)
            return token
        logger.warning("[DigiKey] Pas de token dans la réponse : %s", data)
    except Exception as e:
        logger.warning("[DigiKey] Erreur token : %s", e)

    return None


def fetch_product(part_number: str, client_id: str, client_secret: str) -> dict | None:
    """
    Recherche un composant par numéro DigiKey ou MPN.
    Essaie d'abord /productdetails (plus de données) puis /keyword en fallback.
    """
    if not client_id or not client_secret:
        logger.warning("[DigiKey] Identifiants manquants")
        return None

    token = _get_token(client_id, client_secret)
    if not token:
        return None

    headers = {
        "Authorization":             f"Bearer {token}",
        "X-DIGIKEY-Client-Id":       client_id,
        "Content-Type":              "application/json",
        "X-DIGIKEY-Locale-Site":     "FR",
        "X-DIGIKEY-Locale-Language": "en",
        "X-DIGIKEY-Locale-Currency": "EUR",
    }

    # Essaie d'abord productdetails (retourne PhotoUrl, Parameters/attributs, etc.)
    # Certaines refs DigiKey ont un préfixe numérique (ex: "118-PTA2043...") que l'API
    # peut rejeter — on tente avec et sans ce préfixe avant de tomber en fallback.
    import re as _re
    candidates = [part_number]
    # Détecte et retire un préfixe "NNN-" (ex: "118-") pour avoir la ref nue
    stripped = _re.sub(r"^\d{2,4}-", "", part_number)
    if stripped != part_number:
        candidates.append(stripped)

    for candidate in candidates:
        try:
            url = DETAILS_URL.format(part=requests.utils.quote(candidate, safe=""))
            resp = _SESSION.get(url, headers=headers, timeout=15)
            if resp.status_code == 401:
                # Token expiré — forcer un refresh et réessayer une fois
                _token_cache["access_token"] = None
                token = _get_token(client_id, client_secret)
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                    resp = _SESSION.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                product = data.get("Product") or data
                if product:
                    logger.info("[DigiKey] %s — trouvé via productdetails (candidate: %s) — %d params",
                                part_number, candidate, len(product.get("Parameters") or []))
                    return product
            else:
                logger.debug("[DigiKey] productdetails %s → HTTP %s", candidate, resp.status_code)
        except Exception as e:
            logger.debug("[DigiKey] productdetails failed for %s : %s", candidate, e)

    # Fallback : recherche par keyword — retourne des données allégées SANS Parameters
    logger.warning("[DigiKey] %s — fallback /keyword (pas de Parameters/attributs disponibles)", part_number)
    try:
        resp = _SESSION.post(
            SEARCH_URL,
            headers=headers,
            json={"Keywords": part_number, "Limit": 1},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        products = data.get("Products") or []
        if not products:
            logger.warning("[DigiKey] %s — aucun résultat", part_number)
            return None
        product = products[0]

        # Tente un 2e appel productdetails avec la ref DigiKey exacte trouvée par keyword
        # pour récupérer les Parameters (attributs techniques)
        dk_num = None
        for v in (product.get("ProductVariations") or []):
            dk_num = v.get("DigiKeyProductNumber") or v.get("DigiKeyPartNumber")
            if dk_num:
                break
        dk_num = dk_num or product.get("DigiKeyPartNumber")

        # On tente productdetails même si dk_num == part_number :
        # le 1er essai a peut-être échoué pour une autre raison (token expiré, etc.)
        if dk_num:
            try:
                url2 = DETAILS_URL.format(part=requests.utils.quote(dk_num, safe=""))
                resp2 = _SESSION.get(url2, headers=headers, timeout=15)
                if resp2.status_code == 200:
                    data2 = resp2.json()
                    product2 = data2.get("Product") or data2
                    if product2 and product2.get("Parameters"):
                        logger.info("[DigiKey] %s — Parameters récupérés via 2e appel productdetails (%s)", part_number, dk_num)
                        return product2
            except Exception as e:
                logger.debug("[DigiKey] 2e appel productdetails échoué : %s", e)

        return product

    except requests.exceptions.Timeout:
        logger.warning("[DigiKey] %s — timeout", part_number)
    except requests.exceptions.RequestException as e:
        logger.warning("[DigiKey] %s — réseau : %s", part_number, e)
    except ValueError as e:
        logger.warning("[DigiKey] %s — JSON invalide : %s", part_number, e)

    return None


def extract_info(product: dict) -> dict:
    """
    Extrait les champs utiles depuis un résultat DigiKey v4 (productdetails).
    """
    if not product:
        return {}

    info = {}

    # Description
    desc_obj  = product.get("Description") or {}
    desc      = desc_obj.get("ProductDescription") or desc_obj.get("DetailedDescription") or ""
    desc_long = desc_obj.get("DetailedDescription") or ""
    if desc:
        info["description"] = desc
    if desc_long and desc_long != desc:
        info["description_long"] = desc_long

    # Ref fabricant
    if product.get("ManufacturerProductNumber"):
        info["manufacture_part_number"] = product["ManufacturerProductNumber"]

    # Ref DigiKey — dans ProductVariations (premier élément)
    variations = product.get("ProductVariations") or []
    if variations:
        dk_num = variations[0].get("DigiKeyProductNumber") or variations[0].get("DigiKeyPartNumber") or ""
        if dk_num:
            info["digikey_part_number"] = dk_num

    # Fabricant
    mfr = (product.get("Manufacturer") or {}).get("Name") or ""
    if mfr:
        info["manufacturer"] = mfr

    # Catégorie
    cat = (product.get("Category") or {}).get("Name") or ""
    if cat:
        info["category_name"] = cat

    # Package — cherche dans Parameters
    for p in (product.get("Parameters") or []):
        name = str(p.get("ParameterText") or p.get("Parameter") or p.get("ParameterId") or "").lower()
        if "package" in name or "case" in name:
            info["package"] = str(p.get("ValueText") or p.get("Value") or p.get("ValueId") or "")
            break

    # Datasheet
    if product.get("DatasheetUrl"):
        info["datasheet_url"] = product["DatasheetUrl"]

    # Image — PhotoUrl à la racine, décoder les %7E et autres encodages
    photo = product.get("PhotoUrl") or product.get("PrimaryPhoto") or \
            next((v.get("PhotoUrl") for v in variations if v.get("PhotoUrl")), None)
    if photo:
        from urllib.parse import unquote
        info["image_url"] = unquote(photo)

    # Prix — UnitPrice est directement à la racine dans productdetails
    unit_price = product.get("UnitPrice")
    if unit_price:
        try:
            price = float(unit_price)
            if price > 0:
                info["unit_price"] = round(price, 6)
        except (ValueError, TypeError):
            pass

    # Fallback prix — dans ProductVariations.StandardPricing
    if "unit_price" not in info:
        for v in variations:
            pricing = v.get("StandardPricing") or []
            if pricing:
                try:
                    sorted_p = sorted(pricing, key=lambda x: int(x.get("BreakQuantity", 0)))
                    price = float(sorted_p[0].get("UnitPrice", 0))
                    if price > 0:
                        info["unit_price"] = round(price, 6)
                        break
                except (ValueError, IndexError, TypeError):
                    pass

    # Attributs techniques — Parameters
    params = product.get("Parameters") or []
    if params:
        attrs = {}
        for p in params:
            name  = str(p.get("ParameterText") or p.get("Parameter") or p.get("ParameterId") or "")
            value = str(p.get("ValueText")      or p.get("Value")     or p.get("ValueId")    or "")
            if name and value and value not in ("", "-", "N/A", "Inconnu", "None"):
                attrs[name] = value
        if attrs:
            info["attributes"] = attrs

    # RoHS
    for cls in (product.get("Classifications") or {}).values() if isinstance(product.get("Classifications"), dict) else []:
        if isinstance(cls, str) and "compliant" in cls.lower():
            info["rohs"] = "YES"
            break

    # Lien produit
    if product.get("ProductUrl"):
        # Convertir en URL française et s'assurer du préfixe /fr/
        url = product["ProductUrl"]
        url = url.replace("digikey.com/en/", "digikey.fr/fr/")
        url = url.replace("digikey.com/products/", "digikey.fr/fr/products/")
        if "digikey.com" in url:
            url = url.replace("digikey.com", "digikey.fr")
        info["product_url"] = url

    return {k: v for k, v in info.items() if v not in (None, "", [], {})}


def download_image(image_url: str, ref: str) -> str | None:
    """Télécharge l'image dans instance/images/digikey_<ref>.<ext>"""
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

    filename = f"digikey_{ref.replace('/', '_').replace(' ', '_')}{ext}"
    filepath = os.path.join(IMAGES_DIR, filename)

    if os.path.exists(filepath) and os.path.getsize(filepath) > 500:
        return f"images/{filename}"

    try:
        req = urllib.request.Request(
            safe_url,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.digikey.com/"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            content = r.read()
        if len(content) < 500:
            return None
        with open(filepath, "wb") as f:
            f.write(content)
        logger.info("[DigiKey] %s — image téléchargée", ref)
        return f"images/{filename}"
    except Exception as e:
        logger.warning("[DigiKey] %s — échec image : %s", ref, e)
        return None


def enrich_component(digikey_part_number: str, client_id: str, client_secret: str) -> dict:
    """
    Point d'entrée principal — scrape DigiKey et télécharge l'image.
    Retourne un dict compatible avec ComponentModel.apply_enrichment().
    """
    if not digikey_part_number or not client_id or not client_secret:
        return {}

    product = fetch_product(digikey_part_number, client_id, client_secret)
    if not product:
        return {}

    info = extract_info(product)
    if not info:
        return {}

    if info.get("image_url"):
        local_path = download_image(info["image_url"], digikey_part_number)
        if local_path:
            info["image_path"] = local_path

    logger.info("[DigiKey] %s — enrichi : %s", digikey_part_number, list(info.keys()))
    return info
