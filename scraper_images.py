#!/usr/bin/env python3
"""Simple tool to download product images from a WooCommerce page.

The script loads a product page in a headless Chrome browser, grabs all
matching image tags and stores them locally. Base64 encoded images and
regular image URLs are both supported. The output folder is created
based on the cleaned product name.
"""

from __future__ import annotations

import base64
import os
import re
import time
from pathlib import Path
from typing import Iterable

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from tqdm import tqdm
from webdriver_manager.chrome import ChromeDriverManager

DEFAULT_CSS_SELECTOR = ".product-gallery__media-list img"


def _setup_driver() -> webdriver.Chrome:
    """Return a headless Chrome WebDriver."""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-logging")
    options.add_argument("--log-level=3")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)


def _safe_folder(product_name: str) -> Path:
    """Return a Path object for the folder where images will be saved."""
    safe_name = re.sub(r"[^\w\-]", "_", product_name)
    folder = Path("images") / safe_name
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _download_binary(url: str, path: Path) -> None:
    """Download binary content from *url* into *path*."""
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    path.write_bytes(response.content)


def _save_base64(encoded: str, path: Path) -> None:
    path.write_bytes(base64.b64decode(encoded))


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


def download_images(url: str, css_selector: str = DEFAULT_CSS_SELECTOR) -> None:
    driver = _setup_driver()

    product_name = ""
    folder = Path()
    downloaded = 0
    skipped = 0

    try:
        print("\U0001F30D Chargement de la page...")
        driver.get(url)
        time.sleep(2)

        product_name = _find_product_name(driver)
        folder = _safe_folder(product_name)

        img_elements = driver.find_elements(By.CSS_SELECTOR, css_selector)
        print(
            f"\n\U0001F5BC {len(img_elements)} images trouvées avec le sélecteur : {css_selector}\n"
        )

        for idx, img in enumerate(
            tqdm(img_elements, desc="\U0001F53D Téléchargement des images"), start=1
        ):
            try:
                if _handle_image(img, folder, idx):
                    downloaded += 1
                else:
                    skipped += 1
                time.sleep(0.5)
            except Exception as exc:
                print(f"\u274c Erreur pour l'image {idx} : {exc}")
    finally:
        driver.quit()

    print("\n" + "-" * 50)
    print(f"\U0001F3AF Produit     : {product_name}")
    print(f"\U0001F4E6 Dossier     : {folder}")
    print(f"\u2705 Téléchargées : {downloaded}")
    print(f"\u27A1️ Ignorées     : {skipped}")
    print("-" * 50)


if __name__ == "__main__":
    try:
        product_url = input("\U0001F517 Entrez l'URL du produit WooCommerce : ").strip()
        selector = input(
            f"\U0001F3AF Classe CSS des images [défaut: {DEFAULT_CSS_SELECTOR}] : "
        ).strip() or DEFAULT_CSS_SELECTOR
        download_images(product_url, selector)
    except KeyboardInterrupt:
        print("\nInterruption par l'utilisateur.")
