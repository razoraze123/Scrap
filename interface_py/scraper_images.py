#!/usr/bin/env python3
"""Utilities to download product images from a WooCommerce page."""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Optional

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from tqdm import tqdm

from interface_py.driver_utils import setup_driver
from settings_manager import SettingsManager, DEFAULT_SETTINGS
from interface_py.constants import (
    IMAGES_DEFAULT_SELECTOR as DEFAULT_CSS_SELECTOR,
    USER_AGENT,
)
from . import download_helpers as dl_helpers
from . import rename_helpers

logger = logging.getLogger(__name__)


def _safe_folder(product_name: str, base_dir: Path | str = "images") -> Path:
    """Return a Path where images will be saved."""
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
    except Exception as exc:  # pragma: no cover - platform dependent
        logger.warning("Impossible d'ouvrir le dossier %s : %s", path, exc)


def _find_product_name(driver: webdriver.Chrome) -> str:
    """Return the product name found in the page."""
    selectors = [
        (By.CSS_SELECTOR, "meta[property='og:title']", "content"),
        (By.TAG_NAME, "title", None),
        (By.TAG_NAME, "h1", None),
    ]
    for by, value, attr in selectors:
        try:
            elem = driver.find_element(by, value)
            text = elem.get_attribute(attr) if attr else getattr(elem, "text", "")
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
    user_agent: str | None = None,
    use_alt_json: bool = rename_helpers.USE_ALT_JSON,
    *,
    alt_json_path: str | Path | None = None,
    max_threads: int = 4,
) -> dict:
    """Download all images from *url* and return folder and first image."""
    reserved_paths: set[Path] = set()
    manager = SettingsManager()
    if user_agent is None:
        user_agent = manager.settings.get("user_agent", DEFAULT_SETTINGS["user_agent"])

    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("URL must start with http:// or https://")

    driver = setup_driver()

    product_name = ""
    folder = Path()
    first_image: Path | None = None
    downloaded = 0
    skipped = 0

    if use_alt_json and alt_json_path:
        sentences = rename_helpers.load_alt_sentences(Path(alt_json_path))
    else:
        sentences = {}
        use_alt_json = False
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
        pbar = tqdm(range(total), desc="\U0001F53D Téléchargement des images")
        pbar_update = getattr(pbar, "update", lambda n=1: None)
        pbar_close = getattr(pbar, "close", lambda: None)
        futures: dict = {}

        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            for idx, img in enumerate(img_elements, start=1):
                try:
                    path, url_to_download = dl_helpers.handle_image(
                        img, folder, idx, user_agent, reserved_paths
                    )
                    WebDriverWait(driver, 5).until(
                        lambda d: img.get_attribute("src")
                        or img.get_attribute("data-src")
                        or img.get_attribute("data-srcset")
                    )
                    if url_to_download is None:
                        if use_alt_json:
                            path = rename_helpers.rename_with_alt(
                                path, sentences, warned_missing, reserved_paths
                            )
                        downloaded += 1
                        if first_image is None:
                            first_image = path
                        pbar_update(1)
                        if progress_callback:
                            progress_callback(idx, total)
                    else:
                        fut = executor.submit(
                            dl_helpers.download_binary,
                            url_to_download,
                            path,
                            user_agent,
                        )
                        futures[fut] = (idx, path)
                except Exception as exc:  # pragma: no cover - unexpected
                    logger.error("\u274c Erreur pour l'image %s : %s", idx, exc)
            for fut in as_completed(futures):
                idx, path = futures[fut]
                try:
                    fut.result()
                    if use_alt_json:
                        path = rename_helpers.rename_with_alt(
                            path, sentences, warned_missing, reserved_paths
                        )
                    downloaded += 1
                    if first_image is None:
                        first_image = path
                except Exception as exc:  # pragma: no cover - download failure
                    logger.error("\u274c Erreur pour l'image %s : %s", idx, exc)
                    skipped += 1
                pbar_update(1)
                if progress_callback:
                    progress_callback(idx, total)
        pbar_close()
    finally:
        driver.quit()

    logger.info("\n" + "-" * 50)
    logger.info("\U0001F3AF Produit     : %s", product_name)
    logger.info("\U0001F4E6 Dossier     : %s", folder)
    logger.info("\u2705 Téléchargées : %s", downloaded)
    logger.info("\u27A1️ Ignorées     : %s", skipped)
    logger.info("-" * 50)

    return {"folder": folder, "first_image": first_image}
