from __future__ import annotations

import base64
import binascii
import logging
import os
import re
from pathlib import Path

import requests

from interface_py.constants import USER_AGENT

logger = logging.getLogger(__name__)


def download_binary(url: str, path: Path, user_agent: str = USER_AGENT) -> None:
    """Download binary content from *url* into *path* using *user_agent*."""
    headers = {"User-Agent": user_agent}
    try:
        with requests.get(url, headers=headers, stream=True, timeout=10) as resp:
            resp.raise_for_status()
            with path.open("wb") as fh:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        fh.write(chunk)
    except requests.exceptions.RequestException as exc:  # pragma: no cover
        raise RuntimeError(f"Failed to download {url}") from exc


def save_base64(encoded: str, path: Path) -> None:
    """Decode base64 *encoded* data and write it to *path*."""
    try:
        data = base64.b64decode(encoded)
    except binascii.Error as exc:  # pragma: no cover - invalid data
        raise RuntimeError("Invalid base64 image data") from exc
    path.write_bytes(data)


def unique_path(folder: Path, filename: str, reserved: set[Path]) -> Path:
    """Return a unique ``Path`` in *folder* for *filename*."""
    base, ext = os.path.splitext(filename)
    candidate = folder / filename
    counter = 1
    while candidate.exists() or candidate in reserved:
        candidate = folder / f"{base}_{counter}{ext}"
        counter += 1
    reserved.add(candidate)
    return candidate


def handle_image(
    element, folder: Path, index: int, user_agent: str, reserved: set[Path]
) -> tuple[Path, str | None]:
    """Return target path and optional URL for *element* image."""
    src = (
        element.get_attribute("src")
        or element.get_attribute("data-src")
        or element.get_attribute("data-srcset")
    )
    if not src:
        raise RuntimeError("Aucun attribut src / data-src trouvé pour l'image")

    if " " in src and "," in src:
        candidates = [s.strip().split(" ")[0] for s in src.split(",")]
        src = candidates[-1]

    logger.debug("Téléchargement de l'image : %s", src)

    if src.startswith("data:image"):
        header, encoded = src.split(",", 1)
        ext = header.split("/")[1].split(";")[0]
        filename = f"image_base64_{index}.{ext}"
        target = unique_path(folder, filename, reserved)
        save_base64(encoded, target)
        return target, None

    if src.startswith("//"):
        src = "https:" + src

    raw_filename = os.path.basename(src.split("?")[0])
    filename = re.sub(r"-\d+(?=\.\w+$)", "", raw_filename)
    target = unique_path(folder, filename, reserved)
    return target, src
