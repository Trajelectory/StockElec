"""
image_utils.py — Téléchargement et validation d'images pour les scrapers.

Ce module centralise la logique commune aux trois scrapers (LCSC, Mouser, DigiKey) :
  - Calcul du chemin instance/images/ via current_app
  - Téléchargement avec headers adaptés à chaque source
  - Vérification de taille minimale et de magic bytes
  - Cache (ne re-télécharge pas si le fichier est déjà présent et valide)
"""

import os
import urllib.request
import urllib.parse
import logging

from flask import current_app

logger = logging.getLogger(__name__)

# Taille minimale acceptée pour une image (en dessous = probablement une erreur 404 HTML)
_MIN_SIZE = 500

# Extensions valides
_VALID_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

# Magic bytes des formats image supportés
_MAGIC = {
    b"\xff\xd8\xff": "jpeg",
    b"\x89PNG":      "png",
    b"GIF8":         "gif",
    b"RIFF":         "webp",  # RIFF....WEBP
    b"\x00\x00\x00": None,    # possible MP4 ou autre — accepté si > MIN_SIZE
}


def get_images_dir() -> str:
    """Retourne le chemin absolu vers instance/images/, le crée si nécessaire."""
    path = os.path.join(current_app.instance_path, "images")
    os.makedirs(path, exist_ok=True)
    return path


def _is_valid_image(content: bytes) -> bool:
    """Vérifie que le contenu ressemble à une image (magic bytes + taille + HTML)."""
    if len(content) < _MIN_SIZE:
        return False
    # Contenu HTML ou JSON = probablement une page d'erreur
    if content.lstrip()[:1] in (b"<", b"{"):
        return False
    # Vérification magic bytes — au moins un format connu
    for magic in _MAGIC:
        if content[:len(magic)] == magic:
            return True
    # Pas de magic bytes reconnu → accepter quand même si taille suffisante
    # (certains CDN servent des images sans en-tête standard)
    return len(content) >= _MIN_SIZE * 10  # > 5Ko = probablement une vraie image


def _ext_from_url(url: str) -> str:
    """Extrait l'extension depuis l'URL (sans query string). Défaut : .jpg"""
    clean = url.split("?")[0]
    ext = os.path.splitext(clean)[-1].lower()
    return ext if ext in _VALID_EXTS else ".jpg"


def _safe_url(url: str) -> str:
    """Encode proprement une URL (gère les espaces et caractères spéciaux)."""
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(
        parsed._replace(path=urllib.parse.quote(parsed.path, safe="/%"))
    )


def download_image(
    image_url: str,
    filename_prefix: str,
    *,
    referer: str = "https://www.lcsc.com/",
    extra_headers: dict | None = None,
) -> str | None:
    """
    Télécharge une image depuis image_url et la sauvegarde dans instance/images/.

    Paramètres :
        image_url       — URL source de l'image
        filename_prefix — préfixe du fichier (ex: "C149504", "mouser_652-xxx", "digikey_296-xxx")
        referer         — header Referer à envoyer (adapté à chaque distributeur)
        extra_headers   — headers supplémentaires (Accept, etc.)

    Retourne :
        Chemin relatif "images/<filename>" si succès, None sinon.
    """
    if not image_url:
        return None

    url = _safe_url(image_url)
    ext = _ext_from_url(url)
    # Nettoyer le préfixe pour éviter les caractères invalides dans un nom de fichier
    safe_prefix = filename_prefix.replace("/", "_").replace(" ", "_").replace("\\", "_")
    filename = f"{safe_prefix}{ext}"
    images_dir = get_images_dir()
    filepath = os.path.join(images_dir, filename)

    # ── Cache : ne re-télécharge pas si le fichier est déjà présent et valide ──
    if os.path.exists(filepath) and os.path.getsize(filepath) > _MIN_SIZE:
        # Vérifier que ce n'est pas un fichier HTML corrompu d'un téléchargement précédent
        with open(filepath, "rb") as f:
            header = f.read(15)
        if not header.lstrip().startswith(b"<"):
            logger.debug("[image_utils] %s — déjà en cache", filename)
            return f"images/{filename}"
        # Fichier corrompu → on le supprime et on re-télécharge
        logger.warning("[image_utils] %s — fichier corrompu, re-téléchargement", filename)
        try:
            os.remove(filepath)
        except OSError:
            pass

    # ── Téléchargement ────────────────────────────────────────────────
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Referer": referer,
        "Accept":  "image/webp,image/apng,image/*,*/*;q=0.8",
    }
    if extra_headers:
        headers.update(extra_headers)

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            content = response.read()

        if not _is_valid_image(content):
            logger.warning(
                "[image_utils] %s — contenu invalide (%d o), ignoré",
                filename_prefix, len(content)
            )
            return None

        with open(filepath, "wb") as f:
            f.write(content)

        logger.info(
            "[image_utils] %s — téléchargée ✅ (%d Ko)",
            filename, len(content) // 1024
        )
        return f"images/{filename}"

    except Exception as e:
        logger.warning("[image_utils] %s — échec : %s", filename_prefix, e)
        return None
