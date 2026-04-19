"""
clean_pycache.py — Supprime tous les dossiers __pycache__ et fichiers .pyc
Utilisation : python clean_pycache.py [chemin]
              python clean_pycache.py          (dossier courant)
              python clean_pycache.py C:/projets
"""

import os
import sys
import shutil

def clean(root: str) -> tuple[int, int]:
    """Supprime récursivement tous les __pycache__ et .pyc.
    Retourne (nb_dossiers, nb_fichiers) supprimés."""
    dirs_removed  = 0
    files_removed = 0

    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        # Supprimer les __pycache__ trouvés
        if "__pycache__" in dirnames:
            target = os.path.join(dirpath, "__pycache__")
            shutil.rmtree(target, ignore_errors=True)
            print(f"  ✓ {target}")
            dirs_removed += 1
            dirnames.remove("__pycache__")   # ne pas descendre dedans

        # Supprimer les .pyc isolés (hors __pycache__)
        for f in filenames:
            if f.endswith((".pyc", ".pyo")):
                fp = os.path.join(dirpath, f)
                os.remove(fp)
                print(f"  ✓ {fp}")
                files_removed += 1

    return dirs_removed, files_removed


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    root = os.path.abspath(root)

    if not os.path.isdir(root):
        print(f"Erreur : dossier introuvable → {root}")
        sys.exit(1)

    print(f"\n🧹 Nettoyage de : {root}\n")
    dirs, files = clean(root)
    print(f"\n{'—'*50}")
    print(f"  {dirs}  dossier(s) __pycache__ supprimé(s)")
    print(f"  {files} fichier(s)  .pyc/.pyo   supprimé(s)")
    print(f"  Terminé ✓")
