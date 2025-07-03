#!/usr/bin/env python3
"""Scrape product names and URLs from a collection page.

The script navigates through all pages of a Shopify (or similar) collection
and stores each product name and link into a UTF-8 encoded text file.
"""

from __future__ import annotations

import argparse
import logging
import random
import time
from pathlib import Path
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

# Default CSS selector used to locate product links in the collection page
DEFAULT_SELECTOR = "div.product-card__info h3.product-card__title a"
# Default CSS selector used to locate the "next page" button
DEFAULT_NEXT_SELECTOR = "a[rel=\"next\"]"


def _setup_driver() -> webdriver.Chrome:
    """Return a headless Chrome WebDriver."""

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-logging")
    options.add_argument("--log-level=3")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--disable-blink-features=AutomationControlled")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    # Hide webdriver flag
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    return driver


def _random_sleep(min_s: float = 1.0, max_s: float = 2.5) -> None:
    """Sleep for a random duration between *min_s* and *max_s* seconds."""

    time.sleep(random.uniform(min_s, max_s))


def scrape_collection(
    url: str,
    output_txt: Path,
    css_selector: str = DEFAULT_SELECTOR,
    next_selector: str = DEFAULT_NEXT_SELECTOR,
) -> None:
    """Scrape all products from *url* using *css_selector* and save them to *output_txt*.

    ``next_selector`` is used to detect the button leading to the next page.
    """

    driver = _setup_driver()
    results: list[dict[str, str]] = []

    try:
        page_num = 1

        logging.info("Ouverture de la collection : %s", url)
        if not url.lower().startswith(("http://", "https://")):
            raise ValueError("URL invalide : seul http(s) est autorise")
        driver.get(url)
        _random_sleep(2.0, 4.0)

        while True:
            logging.info("Traitement de la page %d", page_num)

            WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, css_selector))
            )
            elems = driver.find_elements(By.CSS_SELECTOR, css_selector)

            for el in elems:
                name = el.get_attribute("innerText").strip()
                href = el.get_attribute("href") or el.get_attribute("data-href") or ""
                full_url = href if href.startswith("http") else urljoin(url, href)
                results.append({"name": name, "url": full_url})
                logging.debug("\u2192 %s : %s", name, full_url)

            try:
                next_btn = driver.find_element(By.CSS_SELECTOR, next_selector)
                next_href = next_btn.get_attribute("href")
                if not next_href:
                    break
                logging.info("\u2192 Page suivante detectee, navigation vers %s", next_href)
                current_url = driver.current_url
                next_btn.click()
                WebDriverWait(driver, 10).until(
                    lambda d: d.current_url != current_url
                    or EC.staleness_of(next_btn)(d)
                )
                page_num += 1
            except Exception:
                logging.info("\u2192 Pas de page suivante, fin de la pagination.")
                break
    finally:
        driver.quit()

    output_txt.parent.mkdir(parents=True, exist_ok=True)
    with output_txt.open("w", encoding="utf-8-sig") as f:
        for row in results:
            f.write(f"{row['name']} - {row['url']}\n")

    logging.info("\u2714\ufe0f %d produits sauvegardes dans %s", len(results), output_txt)


def main() -> None:
    """Entry point for the script when run from the command line."""

    parser = argparse.ArgumentParser(
        description="Scraper les noms et liens de produits depuis une collection Shopify (ou autre)."
    )
    parser.add_argument(
        "url",
        nargs="?",
        help="URL de la page de collection (si absent, demande a l'execution)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="products.txt",
        help="Chemin du fichier de sortie (defaut: %(default)s)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Niveau de logging (defaut: %(default)s)",
    )
    parser.add_argument(
        "--next-selector",
        default=DEFAULT_NEXT_SELECTOR,
        help="Selecteur CSS du bouton 'page suivante' (defaut: %(default)s)",
    )
    args = parser.parse_args()

    if not args.url:
        args.url = input("Entrez l'URL de la collection a scraper : ").strip()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    print(f"\U0001F7E1 Selecteur CSS par defaut : {DEFAULT_SELECTOR}")
    user_input = input(
        "Souhaitez-vous utiliser un autre selecteur CSS ? (laisser vide pour garder le defaut) : "
    ).strip()
    css_selector = user_input or DEFAULT_SELECTOR

    print(
        f"\U0001F7E1 Selecteur CSS pour le bouton 'page suivante' : {args.next_selector}"
    )

    try:
        scrape_collection(args.url, Path(args.output), css_selector, args.next_selector)
    except Exception as exc:
        logging.error("Une erreur est survenue : %s", exc)
        exit(1)


if __name__ == "__main__":
    main()
