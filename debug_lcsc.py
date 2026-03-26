"""
Script de diagnostic — à lancer sur ta machine :
  python debug_lcsc.py

Il affiche :
  1. La réponse JSON brute de l'endpoint LCSC
  2. Les champs détectés (catégorie, image, datasheet)
  3. Un test de téléchargement d'image
"""

import json
import os
import sys

try:
    import requests
except ImportError:
    print("Installe requests : pip install requests")
    sys.exit(1)

PART = "C149504"
URL  = f"https://wmsc.lcsc.com/ftps/wm/product/detail?productCode={PART}"

print(f"=== Test endpoint LCSC pour {PART} ===\n")
print(f"URL : {URL}\n")

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.lcsc.com/",
    "Origin": "https://www.lcsc.com",
}

# ── 1. Requête brute ──────────────────────────────────────────────
try:
    resp = requests.get(URL, headers=headers, timeout=15)
    print(f"Status HTTP : {resp.status_code}")
    print(f"Content-Type : {resp.headers.get('Content-Type', '?')}\n")
except Exception as e:
    print(f"ERREUR RÉSEAU : {e}")
    sys.exit(1)

# ── 2. Parsing JSON ───────────────────────────────────────────────
try:
    data = resp.json()
except Exception as e:
    print(f"ERREUR JSON : {e}")
    print("Réponse brute :", resp.text[:500])
    sys.exit(1)

print("=== JSON complet (niveau racine) ===")
print(json.dumps({k: type(v).__name__ for k, v in data.items()}, indent=2))
print()

# ── 3. Clé 'data' ─────────────────────────────────────────────────
inner = data.get("data") or data.get("result") or {}
if not inner:
    print("ATTENTION : pas de clé 'data' dans la réponse.")
    print("Réponse complète :")
    print(json.dumps(data, indent=2, ensure_ascii=False)[:3000])
    sys.exit(1)

print("=== Champs disponibles dans data{} ===")
for k, v in inner.items():
    if isinstance(v, (list, dict)):
        preview = f"[{type(v).__name__}, {len(v)} éléments]"
    else:
        preview = str(v)[:120]
    print(f"  {k!r:40s} = {preview}")

print()

# ── 4. Détection des champs utiles ────────────────────────────────
print("=== Champs utiles détectés ===")

# Catégorie
for k in ("catalogName", "parentCatalogName", "catalogId", "parentCatalogId",
          "category", "categoryName", "subCategory", "firstCatalog", "secondCatalog"):
    if inner.get(k) is not None:
        print(f"  Catégorie → {k!r} = {inner[k]!r}")

# Image
for k in ("productImages", "images", "productImg", "imgUrl", "imageUrl", "img"):
    if inner.get(k):
        print(f"  Image     → {k!r} = {inner[k]!r}")

# Datasheet
for k in ("pdfUrl", "datasheetUrl", "dataManualUrl", "pdf", "datasheet"):
    if inner.get(k):
        print(f"  Datasheet → {k!r} = {inner[k]!r}")

print()

# ── 5. Test téléchargement image ──────────────────────────────────
images = inner.get("productImages") or inner.get("images") or []
if isinstance(images, str):
    images = [images]

if images:
    img_url = images[0] if isinstance(images[0], str) else images[0].get("url", "")
    if img_url:
        print(f"=== Test téléchargement image ===")
        print(f"URL : {img_url}")
        try:
            img_resp = requests.get(img_url, headers=headers, timeout=15)
            print(f"Status : {img_resp.status_code}")
            print(f"Content-Type : {img_resp.headers.get('Content-Type', '?')}")
            print(f"Taille : {len(img_resp.content)} octets")
        except Exception as e:
            print(f"ERREUR : {e}")
else:
    print("Aucune image trouvée dans la réponse.")

print()
print("=== JSON data{} complet ===")
print(json.dumps(inner, indent=2, ensure_ascii=False))
