#!/usr/bin/env python3
"""Simple tool to download product images from a WooCommerce page.

The script loads a product page in a headless Chrome browser, grabs all
matching image tags and stores them locally. Base64 encoded images and
regular image URLs are both supported. The output folder is created
based on the cleaned product name.
"""

from __future__ import annotations

import base64
import binascii
import logging
import os
import re
import sys
import subprocess
import json
import random
import unicodedata
from pathlib import Path
from typing import Iterable, Callable, Optional
import argparse

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from tqdm import tqdm
from webdriver_manager.chrome import ChromeDriverManager

DEFAULT_CSS_SELECTOR = ".product-gallery__media-list img"

# Path to the JSON file containing product names and ALT sentences
ALT_JSON_PATH = Path(__file__).with_name("product_sentences.json")

# Enable use of ALT sentences for renaming images by default
USE_ALT_JSON = True


logger = logging.getLogger(__name__)


def _setup_driver() -> webdriver.Chrome:
    """Return a headless Chrome WebDriver."""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-logging")
    options.add_argument("--log-level=3")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)


def _safe_folder(product_name: str, base_dir: Path | str = "images") -> Path:
    """Return a Path object for the folder where images will be saved."""
    safe_name = re.sub(r"[^\w\-]", "_", product_name)
    folder = Path(base_dir) / safe_name
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _open_folder(path: Path) -> None:
    """Open *path* in the system file explorer if possible."""
    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as exc:
        logger.warning("Impossible d'ouvrir le dossier %s : %s", path, exc)


USER_AGENT = "ScrapImageBot/1.0"


def _download_binary(url: str, path: Path, user_agent: str = USER_AGENT) -> None:
    """Download binary content from *url* into *path* using *user_agent*."""
    headers = {"User-Agent": user_agent}
    try:
        with requests.get(url, headers=headers, stream=True, timeout=10) as resp:
            resp.raise_for_status()
            with path.open("wb") as fh:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        fh.write(chunk)
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Failed to download {url}") from exc


def _save_base64(encoded: str, path: Path) -> None:
    try:
        data = base64.b64decode(encoded)
    except binascii.Error as exc:
        raise RuntimeError("Invalid base64 image data") from exc
    path.write_bytes(data)


def _unique_path(folder: Path, filename: str) -> Path:
    """Return a unique Path in *folder* for *filename*.

    If a file with the same name already exists, ``_n`` is appended before the
    extension where ``n`` increments until an unused name is found.
    """

    base, ext = os.path.splitext(filename)
    candidate = folder / filename
    counter = 1
    while candidate.exists():
        candidate = folder / f"{base}_{counter}{ext}"
        counter += 1
    return candidate


def _load_alt_sentences(path: Path = ALT_JSON_PATH) -> dict:
    """Load and return the ALT sentences mapping from *path*."""
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        logger.warning("Impossible de charger %s : %s", path, exc)
        return {}


def _clean_filename(text: str) -> str:
    """Return *text* transformed into a safe file name."""
    normalized = unicodedata.normalize("NFD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_text = ascii_text.lower()
    ascii_text = re.sub(r"\s+", "_", ascii_text)
    ascii_text = re.sub(r"[^a-z0-9_-]", "", ascii_text)
    return ascii_text


def _rename_with_alt(path: Path, sentences: dict, warned: set[str]) -> Path:
    """Rename *path* using ALT sentences if available."""

    product_key = path.parent.name.replace("_", " ")
    phrase_list = sentences.get(product_key)
    if not phrase_list:
        if product_key not in warned:
            logger.warning(
                "Cle '%s' absente de product_sentences.json, pas de renommage", product_key
            )
            warned.add(product_key)
        return path

    alt_phrase = random.choice(phrase_list)
    filename = _clean_filename(alt_phrase) + path.suffix
    target = path.parent / filename
    if target != path and target.exists():
        target = _unique_path(path.parent, filename)
    try:
        path.rename(target)
    except OSError as exc:
        logger.warning("Echec du renommage %s -> %s : %s", path, target, exc)
        return path
    return target


def _handle_image(element, folder: Path, index: int, user_agent: str) -> Path | None:
    src = element.get_attribute("src")
    if not src:
        return None

    if src.startswith("data:image"):
        header, encoded = src.split(",", 1)
        ext = header.split("/")[1].split(";")[0]
        filename = f"image_base64_{index}.{ext}"
        target = _unique_path(folder, filename)
        _save_base64(encoded, target)
        return target

    if src.startswith("//"):
        src = "https:" + src

    raw_filename = os.path.basename(src.split("?")[0])
    filename = re.sub(r"-\d+(?=\.\w+$)", "", raw_filename)
    target = _unique_path(folder, filename)
    _download_binary(src, target, user_agent)
    return target


def _find_product_name(driver: webdriver.Chrome) -> str:
    """Return the product name found in the page.

    The function checks, in order, for a ``<meta property="og:title">`` tag,
    the page ``<title>`` element and finally the first ``<h1>`` element. If none
    of these elements provide a non-empty value, ``"produit_woo"`` is returned.
    """

    selectors = [
        (By.CSS_SELECTOR, "meta[property='og:title']", "content"),
        (By.TAG_NAME, "title", None),
        (By.TAG_NAME, "h1", None),
    ]

    for by, value, attr in selectors:
        try:
            elem = driver.find_element(by, value)
            text = (
                elem.get_attribute(attr)
                if attr
                else getattr(elem, "text", "")
            )
            if text:
                text = text.strip()
            if text:
                return text
        except Exception:
            continue

    return "produit_woo"


def download_images(
    url: str,
    css_selector: str = DEFAULT_CSS_SELECTOR,
    parent_dir: Path | str = "images",
    progress_callback: Optional[Callable[[int, int], None]] = None,
    user_agent: str = USER_AGENT,
    use_alt_json: bool = USE_ALT_JSON,
    *,
    alt_json_path: str | Path | None = None,
) -> dict:
    """Download all images from *url* and return folder and first image."""
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("URL must start with http:// or https://")

    driver = _setup_driver()

    product_name = ""
    folder = Path()
    first_image: Path | None = None
    downloaded = 0
    skipped = 0

    if use_alt_json:
        path = Path(alt_json_path) if alt_json_path else ALT_JSON_PATH
        sentences = _load_alt_sentences(path)
    else:
        sentences = {}
    warned_missing: set[str] = set()

    try:
        logger.info("\U0001F30D Chargement de la page...")
        driver.get(url)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, css_selector))
        )

        product_name = _find_product_name(driver)
        folder = _safe_folder(product_name, parent_dir)

        img_elements = driver.find_elements(By.CSS_SELECTOR, css_selector)
        logger.info(
            f"\n\U0001F5BC {len(img_elements)} images trouvées avec le sélecteur : {css_selector}\n"
        )

        total = len(img_elements)
        for idx, img in enumerate(
            tqdm(img_elements, desc="\U0001F53D Téléchargement des images"), start=1
        ):
            try:
                saved = _handle_image(img, folder, idx, user_agent)
                if saved:
                    if use_alt_json:
                        saved = _rename_with_alt(saved, sentences, warned_missing)
                    downloaded += 1
                    if first_image is None:
                        first_image = saved
                else:
                    skipped += 1
                WebDriverWait(driver, 5).until(lambda d: img.get_attribute("src"))
                if progress_callback:
                    progress_callback(idx, total)
            except Exception as exc:
                logger.error("\u274c Erreur pour l'image %s : %s", idx, exc)
    finally:
        driver.quit()

    logger.info("\n" + "-" * 50)
    logger.info("\U0001F3AF Produit     : %s", product_name)
    logger.info("\U0001F4E6 Dossier     : %s", folder)
    logger.info("\u2705 Téléchargées : %s", downloaded)
    logger.info("\u27A1️ Ignorées     : %s", skipped)
    logger.info("-" * 50)

    return {"folder": folder, "first_image": first_image}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Télécharger toutes les images d'un produit WooCommerce."
    )
    parser.add_argument(
        "url",
        nargs="?",
        help="URL du produit (si absent, demande à l'exécution)",
    )
    parser.add_argument(
        "-s",
        "--selector",
        default=DEFAULT_CSS_SELECTOR,
        help="Sélecteur CSS des images (defaut: %(default)s)",
    )
    parser.add_argument(
        "-d",
        "--dest",
        "--parent-dir",
        dest="parent_dir",
        default="images",
        help="Dossier parent des images (defaut: %(default)s)",
    )
    parser.add_argument(
        "--urls",
        help="Fichier contenant une liste d'URLs (une par ligne)",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Ouvrir le dossier des images après téléchargement",
    )
    parser.add_argument(
        "--user-agent",
        default=USER_AGENT,
        help="User-Agent à utiliser pour les requêtes (defaut: %(default)s)",
    )
    parser.add_argument(
        "--use-alt-json",
        dest="use_alt_json",
        action="store_true" if not USE_ALT_JSON else "store_false",
        help=(
            "Activer" if not USE_ALT_JSON else "Désactiver"
        )
        + " le renommage via product_sentences.json",
    )
    parser.add_argument(
        "--alt-json-path",
        default=str(ALT_JSON_PATH),
        help="Chemin du fichier JSON pour le renommage (defaut: %(default)s)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Niveau de logging (defaut: %(default)s)",
    )
    parser.set_defaults(use_alt_json=USE_ALT_JSON)
    args = parser.parse_args()

    if args.url and args.urls:
        parser.error("--url et --urls sont mutuellement exclusifs")

    urls_list = []
    if args.urls:
        try:
            with open(args.urls, "r", encoding="utf-8") as fh:
                urls_list = [line.strip() for line in fh if line.strip()]
        except OSError as exc:
            parser.error(f"Impossible de lire le fichier {args.urls}: {exc}")

    if not urls_list:
        if not args.url:
            args.url = input("\U0001F517 Entrez l'URL du produit WooCommerce : ").strip()
        urls_list = [args.url]

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(levelname)s: %(message)s",
    )

    for url in urls_list:
        try:
            info = download_images(
                url,
                css_selector=args.selector,
                parent_dir=args.parent_dir,
                user_agent=args.user_agent,
                use_alt_json=args.use_alt_json,
                alt_json_path=args.alt_json_path,
            )
            if args.preview:
                _open_folder(info["folder"])
        except ValueError as exc:
            logger.error("Erreur : %s", exc)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\nInterruption par l'utilisateur.")
