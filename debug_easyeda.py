"""
Script de diagnostic EasyEDA — lance depuis ta machine :
  python debug_easyeda.py

Affiche :
  1. La réponse JSON brute
  2. Les SVGs extraits (result[0] et result[1])
  3. Les SVGs après nettoyage
  4. Sauvegarde les SVGs dans des fichiers pour vérification visuelle
"""

import requests
import json
import re
import os

REF = "C149504"
URL = f"https://easyeda.com/api/products/{REF}/svgs"

print(f"=== Test EasyEDA SVG pour {REF} ===")
print(f"URL : {URL}\n")

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
    "Referer":    "https://easyeda.com/",
    "Accept":     "application/json",
}

try:
    r = requests.get(URL, headers=headers, timeout=15)
    print(f"Status HTTP : {r.status_code}")
    print(f"Content-Type : {r.headers.get('Content-Type','?')}\n")
except Exception as e:
    print(f"ERREUR RÉSEAU : {e}")
    exit(1)

try:
    data = r.json()
except Exception as e:
    print(f"ERREUR JSON : {e}")
    print("Réponse brute :", r.text[:500])
    exit(1)

# ── Structure racine ─────────────────────────────────────────────────
print("=== Structure JSON ===")
print(f"  success : {data.get('success')}")
print(f"  code    : {data.get('code')}")
result = data.get("result") or []
print(f"  result  : {len(result)} élément(s)\n")

# ── Chaque élément ───────────────────────────────────────────────────
for i, item in enumerate(result):
    print(f"--- result[{i}] ---")
    print(f"  docType  : {item.get('docType')}")
    print(f"  component_uuid : {item.get('component_uuid','?')[:20]}...")
    svg = item.get("svg","")
    print(f"  svg      : {len(svg)} chars")
    if svg:
        print(f"  svg (début) : {svg[:200]}")
    print()

# ── Extraction directe par index (comme api.py) ───────────────────────
print("=== Extraction par index (méthode api.py) ===")
symbol_svg    = result[0].get("svg","") if len(result) > 0 else ""
footprint_svg = result[1].get("svg","") if len(result) > 1 else ""
print(f"  result[0]['svg'] → {len(symbol_svg)} chars")
print(f"  result[1]['svg'] → {len(footprint_svg)} chars")
print()

# ── Extraction par docType (méthode actuelle) ─────────────────────────
print("=== Extraction par docType (méthode StockElec) ===")
sym_dt = fp_dt = ""
for item in result:
    if item.get("docType") == 2:
        sym_dt = item.get("svg","")
    elif item.get("docType") == 4:
        fp_dt  = item.get("svg","")
print(f"  docType=2 (symbole)   → {len(sym_dt)} chars")
print(f"  docType=4 (footprint) → {len(fp_dt)} chars")
print()

# ── Test du nettoyage SVG ─────────────────────────────────────────────
def clean_svg(svg):
    if not svg: return svg
    svg = re.sub(r'(<svg[^>]*)\s+width="[^"]*"',  r'\1 width="100%"',  svg, count=1)
    svg = re.sub(r'(<svg[^>]*)\s+height="[^"]*"', r'\1 height="100%"', svg, count=1)
    if "preserveAspectRatio" not in svg:
        svg = re.sub(r'(<svg[^>]*)(>|/>)', r'\1 preserveAspectRatio="xMidYMid meet"\2', svg, count=1)
    return svg.strip()

sym_clean = clean_svg(symbol_svg)
fp_clean  = clean_svg(footprint_svg)

print("=== SVG nettoyés ===")
print(f"  Symbole après nettoyage : {sym_clean[:200] if sym_clean else 'VIDE'}")
print()
print(f"  Footprint après nettoyage : {fp_clean[:200] if fp_clean else 'VIDE'}")
print()

# ── Sauvegarde pour test visuel ───────────────────────────────────────
out_dir = os.path.dirname(os.path.abspath(__file__))

if sym_clean:
    # Enveloppe dans un HTML pour tester l'affichage dans le navigateur
    html = f"""<!DOCTYPE html>
<html><body style="background:#1a1d27;padding:20px;display:flex;gap:20px">
  <div style="background:#fff;width:200px;height:200px;padding:10px;border-radius:8px">
    <p style="font-size:10px;color:#999;margin:0 0 4px">Symbole (200×200)</p>
    {sym_clean}
  </div>
  <div style="background:#fff;width:200px;height:200px;padding:10px;border-radius:8px">
    <p style="font-size:10px;color:#999;margin:0 0 4px">Footprint (200×200)</p>
    {fp_clean}
  </div>
  <div style="background:#fff;width:120px;height:120px;padding:4px;border-radius:8px">
    <p style="font-size:8px;color:#999;margin:0 0 2px">Symbole (120×120 — vignette)</p>
    {sym_clean}
  </div>
  <div style="background:#fff;width:120px;height:120px;padding:4px;border-radius:8px">
    <p style="font-size:8px;color:#999;margin:0 0 2px">Footprint (120×120 — vignette)</p>
    {fp_clean}
  </div>
</body></html>"""
    path = os.path.join(out_dir, f"{REF}_test.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ Fichier de test HTML créé : {path}")
    print(f"   → Ouvre ce fichier dans ton navigateur pour vérifier l'affichage\n")

    # SVG bruts aussi
    with open(os.path.join(out_dir, f"{REF}_symbol_raw.svg"), "w", encoding="utf-8") as f:
        f.write(symbol_svg)
    with open(os.path.join(out_dir, f"{REF}_footprint_raw.svg"), "w", encoding="utf-8") as f:
        f.write(footprint_svg)
    with open(os.path.join(out_dir, f"{REF}_symbol_clean.svg"), "w", encoding="utf-8") as f:
        f.write(sym_clean)
    with open(os.path.join(out_dir, f"{REF}_footprint_clean.svg"), "w", encoding="utf-8") as f:
        f.write(fp_clean)
    print(f"✅ SVGs sauvegardés dans {out_dir}")

print()
print("=== Résumé ===")
print(f"  Symbole    : {'OK (' + str(len(sym_clean)) + ' chars)' if sym_clean else 'MANQUANT'}")
print(f"  Footprint  : {'OK (' + str(len(fp_clean)) + ' chars)' if fp_clean else 'MANQUANT'}")
print()
print("Si les SVGs sont présents mais ne s'affichent pas dans StockElec,")
print("ouvre le fichier HTML généré dans ton navigateur — si c'est OK là,")
print("le problème vient du CSS de StockElec. Envoie-moi une capture d'écran.")
