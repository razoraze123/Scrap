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
from pathlib import Path
from typing import Iterable, Callable, Optional

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


USER_AGENT = "ScrapImageBot/1.0"


def _download_binary(url: str, path: Path) -> None:
    """Download binary content from *url* into *path*."""
    headers = {"User-Agent": USER_AGENT}
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


def _handle_image(element, folder: Path, index: int) -> bool:
    src = element.get_attribute("src")
    if not src:
        return False

    if src.startswith("data:image"):
        header, encoded = src.split(",", 1)
        ext = header.split("/")[1].split(";")[0]
        filename = f"image_base64_{index}.{ext}"
        target = folder / filename
        if target.exists():
            return False
        _save_base64(encoded, target)
        return True

    if src.startswith("//"):
        src = "https:" + src

    filename = os.path.basename(src.split("?")[0])
    target = folder / filename
    if target.exists():
        return False
    _download_binary(src, target)
    return True


def _find_product_name(driver: webdriver.Chrome) -> str:
    try:
        elem = driver.find_element(By.TAG_NAME, "h1")
        return elem.text.strip() or "produit_woo"
    except Exception:
        return "produit_woo"


def download_images(
    url: str,
    css_selector: str = DEFAULT_CSS_SELECTOR,
    dest_dir: Path | str = "images",
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> None:
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("URL must start with http:// or https://")

    driver = _setup_driver()

    product_name = ""
    folder = Path()
    downloaded = 0
    skipped = 0

    try:
        logger.info("\U0001F30D Chargement de la page...")
        driver.get(url)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, css_selector))
        )

        product_name = _find_product_name(driver)
        folder = _safe_folder(product_name, dest_dir)

        img_elements = driver.find_elements(By.CSS_SELECTOR, css_selector)
        logger.info(
            f"\n\U0001F5BC {len(img_elements)} images trouvées avec le sélecteur : {css_selector}\n"
        )

        total = len(img_elements)
        for idx, img in enumerate(
            tqdm(img_elements, desc="\U0001F53D Téléchargement des images"), start=1
        ):
            try:
                if _handle_image(img, folder, idx):
                    downloaded += 1
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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        product_url = input("\U0001F517 Entrez l'URL du produit WooCommerce : ").strip()
        selector = (
            input(
                f"\U0001F3AF Classe CSS des images [défaut: {DEFAULT_CSS_SELECTOR}] : "
            ).strip()
            or DEFAULT_CSS_SELECTOR
        )
        dest = input("\U0001F4C2 Dossier de destination [defaut: images] : ").strip() or "images"
        download_images(product_url, selector, dest)
    except ValueError as exc:
        logger.error("Erreur : %s", exc)
    except KeyboardInterrupt:
        logger.info("\nInterruption par l'utilisateur.")
