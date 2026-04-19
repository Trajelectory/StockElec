"""
Script de génération KiCad en batch.
Skips composants déjà générés (footprint + 3D présents).

Usage : python kicad_batch.py <output_prefix> <ref1> <ref2> ...
"""

import sys
import json
import time
import os
import subprocess


def _already_done(output_prefix: str, ref: str) -> bool:
    """Retourne True si le footprint ET au moins un modèle 3D existent déjà."""
    fp   = os.path.join(output_prefix + ".pretty", f"{ref}.kicad_mod")
    wrl  = os.path.join(output_prefix + ".3dshapes", f"{ref}.wrl")
    step = os.path.join(output_prefix + ".3dshapes", f"{ref}.step")
    return os.path.exists(fp) and (os.path.exists(wrl) or os.path.exists(step))


def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: kicad_batch.py <prefix> <ref1> ..."}))
        sys.exit(1)

    output_prefix = sys.argv[1]
    refs          = sys.argv[2:]

    try:
        import easyeda2kicad  # noqa — vérifie juste que c'est installé
    except ImportError as e:
        print(json.dumps({"error": f"easyeda2kicad non installé: {e}"}))
        sys.exit(1)

    results = {"ok": [], "skipped": [], "failed": [], "errors": {}}

    for ref in refs:
        ref = ref.strip().upper()
        if not ref:
            continue

        # Skip si déjà généré
        if _already_done(output_prefix, ref):
            results["skipped"].append(ref)
            results["ok"].append(ref)
            print(f"SKIP {ref}", flush=True)
            continue

        try:
            r = subprocess.run(
                [sys.executable, "-m", "easyeda2kicad",
                 "--symbol", "--footprint", "--3d",
                 "--lcsc_id", ref,
                 "--output", output_prefix,
                 "--overwrite"],
                capture_output=True, text=True, timeout=25,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if r.returncode == 0:
                results["ok"].append(ref)
                print(f"OK {ref}", flush=True)
            else:
                full = (r.stderr or "") + (r.stdout or "")
                if "403" in full or "Expecting value" in full or "JSONDecodeError" in full:
                    print(f"RATELIMIT {ref}", flush=True)
                    results["failed"].append(ref)
                    results["errors"][ref] = "rate_limit"
                    time.sleep(30)
                    continue
                else:
                    results["failed"].append(ref)
                    results["errors"][ref] = full[:100]
                    print(f"FAIL {ref}: {full[:80]}", flush=True)

        except Exception as e:
            err_str = str(e)
            results["failed"].append(ref)
            results["errors"][ref] = err_str
            print(f"FAIL {ref}: {err_str[:100]}", flush=True)

        time.sleep(6)

    print(json.dumps(results))


if __name__ == "__main__":
    main()
