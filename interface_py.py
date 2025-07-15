from __future__ import annotations

import sys
import logging
import io
import os
import shutil
import subprocess
import time
import re
import csv
import json
import base64
import binascii
import random
import unicodedata
import argparse
import types
from pathlib import Path
from typing import Callable, Iterable, Optional
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

import requests

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QListWidget,
    QStackedWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLineEdit,
    QComboBox,
    QPushButton,
    QPlainTextEdit,
    QLabel,
    QProgressBar,
    QFileDialog,
    QCheckBox,
    QSpinBox,
    QFontComboBox,
    QTextEdit,
    QGroupBox,
    QMessageBox,
    QToolBar,
    QToolButton,
    QScrollArea,
    QSizePolicy,
    QFrame,
)
try:
    from PySide6.QtCore import (
        QThread,
        Signal,
        Qt,
        QRect,
        QTimer,
        QPropertyAnimation,
        QEasingCurve,
    )
except Exception:  # pragma: no cover - used in test stubs
    from PySide6.QtCore import (
        QThread,
        Signal,
        Qt,
        QRect,
        QTimer,
        QPropertyAnimation,
    )

    class QEasingCurve:
        InOutCubic = 0
from PySide6.QtGui import QFont, QPainter, QColor, QPixmap, QClipboard

# QSplitter might not be available in all test environments
try:
    from PySide6.QtWidgets import QSplitter
except Exception:  # pragma: no cover - used only for stub environments
    class QSplitter:
        def __init__(self, *args, **kwargs):
            pass

        def addWidget(self, *args, **kwargs):
            pass

        def setStretchFactor(self, *args, **kwargs):
            pass

from alpha_engine import AlphaEngine

from settings_manager import SettingsManager, apply_settings
from site_profile_manager import SiteProfileManager


try:
    from PySide6.QtCore import QSize  # type: ignore
except Exception:  # pragma: no cover - fallback for tests
    class QSize:  # type: ignore
        def __init__(self, *args, **kwargs) -> None:
            pass

try:
    from PySide6.QtGui import QIcon  # type: ignore
except Exception:  # pragma: no cover - fallback for tests
    class QIcon:  # type: ignore
        def __init__(self, *args, **kwargs) -> None:
            pass


ICONS_DIR = Path(__file__).resolve().parent / "icons"

# Sidebar sizing constants
ICON_SIZE = 24
SIDEBAR_EXPANDED_WIDTH = 180
SIDEBAR_COLLAPSED_WIDTH = ICON_SIZE + 16


# ----- driver_utils.py -----

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def setup_driver(headless: bool | None = None, driver_path: str | None = None) -> webdriver.Chrome:
    """Return a configured Chrome WebDriver."""
    driver_path = driver_path or _load_driver_path_from_settings()
    if headless is None:
        headless = _load_headless_from_settings()

    options = Options()
    if headless:
        options.add_argument("--headless")
    options.add_argument("--disable-logging")
    options.add_argument("--log-level=3")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--disable-blink-features=AutomationControlled")

    if driver_path and Path(driver_path).is_file():
        service = Service(str(driver_path))
    else:
        service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    return driver


def _load_headless_from_settings() -> bool:
    settings_file = Path("settings.json")
    if settings_file.is_file():
        try:
            data = json.loads(settings_file.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "headless" in data:
                return bool(data["headless"])
        except Exception:
            pass
    return True


def _load_driver_path_from_settings() -> str | None:
    settings_file = Path("settings.json")
    if settings_file.is_file():
        try:
            data = json.loads(settings_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data.get("driver_path")
        except Exception:
            pass
    return None


# ----- find_css_selector.py -----

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover - optional dependency
    BeautifulSoup = None  # type: ignore

try:
    from PySide6.QtWidgets import (
        QApplication,
        QMainWindow,
        QWidget,
        QVBoxLayout,
        QLabel,
        QPlainTextEdit,
        QLineEdit,
        QPushButton,
    )
except Exception:  # pragma: no cover - optional GUI
    QApplication = None  # type: ignore

_BLACKLIST_PATTERNS = [
    re.compile(pattern)
    for pattern in (
        r"^v-stack$",
        r"^h-stack$",
        r"^gap-",
        r"^grid$",
        r"^grid-",
        r"^w-full$",
        r"^h-full$",
    )
]


def _clean_classes(classes: Iterable[str] | None) -> list[str]:
    if not classes:
        return []
    return [c for c in classes if not any(pat.search(c) for pat in _BLACKLIST_PATTERNS)]


def _build_selector(a_tag) -> str:
    parts: list[str] = ["a"]
    for parent in a_tag.parents:
        if parent.name == "[document]":
            break
        classes = _clean_classes(parent.get("class"))
        if parent.get("id"):
            parts.append(f"{parent.name}#{parent['id']}")
            break
        if classes:
            parts.append(f"{parent.name}." + ".".join(classes))
            break
    return " ".join(reversed(parts))


def find_best_css_selector(html: str) -> str:
    if BeautifulSoup is None:
        raise RuntimeError("BeautifulSoup is required for this function")
    soup = BeautifulSoup(html, "html.parser")
    anchors = [
        a
        for a in soup.find_all("a")
        if a.get("href") and a.get_text(strip=True)
    ]
    if not anchors:
        raise ValueError("No valid <a> tags found")

    candidates = {_build_selector(a) for a in anchors}
    return sorted(candidates, key=len)[0]


def run_selector_gui() -> None:
    if QApplication is None:
        raise RuntimeError("PySide6 is not installed")

    class MainWindow(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("CSS Selector Tester")

            container = QWidget()
            layout = QVBoxLayout(container)
            self.setCentralWidget(container)

            layout.addWidget(QLabel("HTML input"))
            self.input_html = QPlainTextEdit()
            self.input_html.setPlaceholderText("Paste HTML snippet here...")
            layout.addWidget(self.input_html)

            self.button = QPushButton("Find selector")
            layout.addWidget(self.button)

            layout.addWidget(QLabel("Best selector"))
            self.output = QLineEdit()
            self.output.setReadOnly(True)
            layout.addWidget(self.output)

            self.status = QLabel()
            layout.addWidget(self.status)

            self.button.clicked.connect(self.on_click)

        def on_click(self) -> None:
            html = self.input_html.toPlainText().strip()
            if not html:
                self.status.setText("Please provide HTML")
                self.output.clear()
                return
            try:
                selector = find_best_css_selector(html)
            except Exception as exc:  # noqa: BLE001
                self.status.setText(str(exc))
                self.output.clear()
            else:
                self.output.setText(selector)
                self.status.setText("")

    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(600, 400)
    window.show()
    sys.exit(app.exec())


def _gui_entry() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a CSS selector for product links from HTML input",
    )
    parser.add_argument("file", nargs="?", help="Path to an HTML file")
    parser.add_argument("--gui", action="store_true", help="Launch the graphical interface")
    args = parser.parse_args()

    if args.gui:
        run_selector_gui()
    else:
        if args.file:
            with open(args.file, "r", encoding="utf-8") as fh:
                content = fh.read()
        else:
            content = sys.stdin.read()
        print(find_best_css_selector(content))


# ----- generateur_lien.py -----

class WooImageURLGenerator(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Générateur de Liens WooCommerce")

        self.layout = QVBoxLayout()

        self.label_base_url = QLabel("Domaine WooCommerce :")
        self.input_base_url = QLineEdit("https://www.planetebob.fr")
        self.layout.addWidget(self.label_base_url)
        self.layout.addWidget(self.input_base_url)

        self.label_date = QLabel("Date (format YYYY/MM) :")
        self.input_date = QLineEdit("2025/07")
        self.layout.addWidget(self.label_date)
        self.layout.addWidget(self.input_date)

        self.btn_select_folder = QPushButton("Choisir le dossier d'images")
        self.btn_select_folder.clicked.connect(self.choose_folder)
        self.layout.addWidget(self.btn_select_folder)

        self.output_links = QTextEdit()
        self.output_links.setPlaceholderText("Les URLs générées s'afficheront ici.")
        self.layout.addWidget(self.output_links)

        action_layout = QHBoxLayout()
        self.btn_generate = QPushButton("Générer")
        self.btn_generate.clicked.connect(self.generate_links)
        action_layout.addWidget(self.btn_generate)

        self.btn_copy = QPushButton("Copier les liens")
        self.btn_copy.clicked.connect(self.copy_to_clipboard)
        action_layout.addWidget(self.btn_copy)

        self.btn_export = QPushButton("Exporter en .txt")
        self.btn_export.clicked.connect(self.export_to_txt)
        action_layout.addWidget(self.btn_export)

        self.layout.addLayout(action_layout)

        self.setLayout(self.layout)
        self.folder_path = ""

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Sélectionner un dossier")
        if folder:
            self.folder_path = folder
            self.btn_select_folder.setText(f"Dossier : {os.path.basename(folder)}")

    def generate_links(self):
        if not self.folder_path:
            QMessageBox.warning(self, "Erreur", "Veuillez choisir un dossier.")
            return

        base_url = self.input_base_url.text().strip().rstrip("/")
        date_path = self.input_date.text().strip()

        links = []
        for root, _, files in os.walk(self.folder_path):
            for file in files:
                if file.lower().endswith((".webp", ".jpg", ".jpeg", ".png")):
                    file_url = f"{base_url}/wp-content/uploads/{date_path}/{file}"
                    links.append(file_url)

        if links:
            self.output_links.setText("\n".join(links))
        else:
            self.output_links.setText("Aucune image valide trouvée dans le dossier.")

    def copy_to_clipboard(self):
        clipboard: QClipboard = QApplication.clipboard()
        clipboard.setText(self.output_links.toPlainText())
        QMessageBox.information(self, "Copié", "Les liens ont été copiés dans le presse-papiers.")

    def export_to_txt(self):
        if not self.output_links.toPlainText():
            QMessageBox.warning(self, "Erreur", "Aucun lien à exporter.")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Enregistrer sous", "liens_images.txt", "Fichier texte (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.output_links.toPlainText())
            QMessageBox.information(self, "Exporté", "Les liens ont été enregistrés avec succès.")


# ----- moteur_variante.py -----

MV_DEFAULT_SELECTOR = ".variant-picker__option-values span.sr-only"


def extract_variants(url: str, selector: str = MV_DEFAULT_SELECTOR) -> tuple[str, list[str]]:
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("URL must start with http:// or https://")

    driver = setup_driver()
    try:
        logging.info("\U0001F310 Chargement de la page %s", url)
        driver.get(url)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
        )
        title = driver.find_element(By.CSS_SELECTOR, "h1").text.strip()
        elems = driver.find_elements(By.CSS_SELECTOR, selector)
        variants = [e.text.strip() for e in elems if e.text.strip()]
        logging.info("\u2714\ufe0f %d variante(s) détectée(s)", len(variants))
        return title, variants
    finally:
        driver.quit()


def extract_variants_with_images(url: str) -> tuple[str, dict[str, str]]:
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("URL must start with http:// or https://")

    driver = setup_driver()
    try:
        logging.info("\U0001F310 Chargement de la page %s", url)
        driver.get(url)
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "h1")))
        title = driver.find_element(By.CSS_SELECTOR, "h1").text.strip()

        container = driver.find_element(By.CSS_SELECTOR, ".variant-picker__option-values")
        inputs = container.find_elements(By.CSS_SELECTOR, "input[type='radio'].sr-only")

        results: dict[str, str] = {}
        for inp in inputs:
            name = inp.get_attribute("value")
            if not name or name in results:
                continue

            img_elem = driver.find_element(By.CSS_SELECTOR, ".product-gallery__media.is-selected img")
            old_src = img_elem.get_attribute("src")

            if inp.get_attribute("checked") is None:
                driver.execute_script("arguments[0].click();", inp)
                time.sleep(random.uniform(0.1, 0.2))
                WebDriverWait(driver, 5).until(
                    lambda d: d.find_element(By.CSS_SELECTOR, ".product-gallery__media.is-selected img").get_attribute("src") != old_src
                )
                img_elem = driver.find_element(By.CSS_SELECTOR, ".product-gallery__media.is-selected img")

            src = img_elem.get_attribute("src")
            if src.startswith("//"):
                src = "https:" + src
            results[name] = src
            logging.info("%s -> %s", name, src)

        return title, results
    finally:
        driver.quit()


def save_to_file(title: str, variants: list[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        fh.write(f"{title}\t{', '.join(variants)}\n")
    logging.info("\U0001F4BE Variantes enregistrées dans %s", path)


def save_images_to_file(title: str, variants: dict[str, str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        fh.write(f"{title}\n")
        for name, img in variants.items():
            fh.write(f"{name} : {img}\n")
    logging.info("\U0001F4BE Variantes enregistrées dans %s", path)


def scrape_variants(url: str, selector: str, output: Path) -> None:
    title, variants = extract_variants(url, selector)
    save_to_file(title, variants, output)


def variant_main() -> None:
    parser = argparse.ArgumentParser(description="Extrait le titre du produit et la liste des variantes.")
    parser.add_argument("url", nargs="?", help="URL du produit (si absent, demande à l'exécution)")
    parser.add_argument("-s", "--selector", default=MV_DEFAULT_SELECTOR, help="Sélecteur CSS des variantes")
    parser.add_argument("-o", "--output", default="variants.txt", help="Fichier de sortie")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Niveau de logging")
    args = parser.parse_args()
    if not args.url:
        args.url = input("URL du produit : ").strip()
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(levelname)s: %(message)s")
    try:
        scrape_variants(args.url, args.selector, Path(args.output))
    except Exception as exc:
        logging.error("%s", exc)

moteur_variante = types.SimpleNamespace(
    extract_variants=extract_variants,
    extract_variants_with_images=extract_variants_with_images,
    save_to_file=save_to_file,
    save_images_to_file=save_images_to_file,
    scrape_variants=scrape_variants,
    variant_main=variant_main,
    DEFAULT_SELECTOR=MV_DEFAULT_SELECTOR,
)


# ----- scrap_lien_collection.py -----

SLC_DEFAULT_SELECTOR = "div.product-card__info h3.product-card__title a"
SLC_DEFAULT_NEXT_SELECTOR = "a[rel=\"next\"]"


def _random_sleep(min_s: float = 1.0, max_s: float = 2.5) -> None:
    time.sleep(random.uniform(min_s, max_s))


def scrape_collection(
    url: str,
    output_path: Path,
    css_selector: str = SLC_DEFAULT_SELECTOR,
    next_selector: str = SLC_DEFAULT_NEXT_SELECTOR,
    output_format: str = "txt",
) -> None:
    driver = setup_driver()
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
                    lambda d: d.current_url != current_url or EC.staleness_of(next_btn)(d)
                )
                page_num += 1
            except Exception:
                logging.info("\u2192 Pas de page suivante, fin de la pagination.")
                break
    finally:
        driver.quit()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "json":
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
    elif output_format == "csv":
        with output_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["name", "url"])
            writer.writeheader()
            writer.writerows(results)
    else:
        with output_path.open("w", encoding="utf-8-sig") as f:
            for row in results:
                f.write(f"{row['name']} - {row['url']}\n")
    logging.info("\u2714\ufe0f %d produits sauvegardes dans %s", len(results), output_path)


def scrape_collection_main() -> None:
    parser = argparse.ArgumentParser(
        description="Scraper les noms et liens de produits depuis une collection Shopify (ou autre)."
    )
    parser.add_argument("url", nargs="?", help="URL de la page de collection (si absent, demande a l'execution)")
    parser.add_argument("-o", "--output", default="products.txt", help="Chemin du fichier de sortie (defaut: %(default)s)")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Niveau de logging (defaut: %(default)s)")
    parser.add_argument("-s", "--selector", default=SLC_DEFAULT_SELECTOR, help="Selecteur CSS des liens produits (defaut: %(default)s)")
    parser.add_argument("--next-selector", default=SLC_DEFAULT_NEXT_SELECTOR, help="Selecteur CSS du bouton 'page suivante' (defaut: %(default)s)")
    parser.add_argument("--format", choices=["txt", "json", "csv"], default="txt", help="Format de sortie : txt, json ou csv (defaut: %(default)s)")
    args = parser.parse_args()
    if not args.url:
        args.url = input("Entrez l'URL de la collection a scraper : ").strip()
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(asctime)s %(levelname)s %(message)s")
    css_selector = args.selector
    print(f"\U0001F7E1 Selecteur CSS utilise : {css_selector}")
    print(f"\U0001F7E1 Selecteur CSS pour le bouton 'page suivante' : {args.next_selector}")
    try:
        scrape_collection(args.url, Path(args.output), css_selector, args.next_selector, args.format)
    except Exception as exc:
        logging.error("Une erreur est survenue : %s", exc)
        sys.exit(1)


scrap_lien_collection = types.SimpleNamespace(
    scrape_collection=scrape_collection,
    scrape_collection_main=scrape_collection_main,
    DEFAULT_SELECTOR=SLC_DEFAULT_SELECTOR,
    DEFAULT_NEXT_SELECTOR=SLC_DEFAULT_NEXT_SELECTOR,
)


# ----- scrap_description_produit.py -----

SDP_DEFAULT_SELECTOR = ".rte"


def extract_html_description(url: str, css_selector: str = SDP_DEFAULT_SELECTOR) -> str:
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("URL must start with http:// or https://")

    driver = setup_driver()
    try:
        driver.get(url)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, css_selector)))
        element = driver.find_element(By.CSS_SELECTOR, css_selector)
        html = element.get_attribute("innerHTML")
        logging.info("\u2714\ufe0f HTML extrait avec succès")
        return html.strip()
    finally:
        driver.quit()


def save_html_to_file(html: str, filename: Path = Path("description.html")) -> None:
    filename.parent.mkdir(parents=True, exist_ok=True)
    filename.write_text(html, encoding="utf-8")
    logging.info("\U0001F4BE Description enregistrée dans %s", filename.resolve())


def scrape_description(url: str, selector: str, output: Path) -> None:
    html = extract_html_description(url, selector)
    save_html_to_file(html, output)


def description_main() -> None:
    parser = argparse.ArgumentParser(
        description="Extraire la description HTML d'un produit et la sauvegarder dans un fichier."
    )
    parser.add_argument("url", nargs="?", help="URL du produit (si absent, demande à l'exécution)")
    parser.add_argument("-s", "--selector", default=SDP_DEFAULT_SELECTOR, help="Sélecteur CSS de la description (defaut: %(default)s)")
    parser.add_argument("-o", "--output", default="description.html", help="Fichier de sortie (defaut: %(default)s)")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Niveau de logging (defaut: %(default)s)")
    args = parser.parse_args()
    if not args.url:
        args.url = input("\U0001F517 Entrez l'URL du produit : ").strip()
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(levelname)s: %(message)s")
    try:
        scrape_description(args.url, args.selector, Path(args.output))
    except Exception as exc:
        logging.error("%s", exc)

scrap_description_produit = types.SimpleNamespace(
    extract_html_description=extract_html_description,
    save_html_to_file=save_html_to_file,
    scrape_description=scrape_description,
    description_main=description_main,
    DEFAULT_SELECTOR=SDP_DEFAULT_SELECTOR,
)

# ----- scrap_prix_produit.py -----

SPP_DEFAULT_SELECTOR = ".price"


def extract_price(url: str, css_selector: str = SPP_DEFAULT_SELECTOR) -> str:
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("URL must start with http:// or https://")

    driver = setup_driver()
    try:
        driver.get(url)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, css_selector)))
        element = driver.find_element(By.CSS_SELECTOR, css_selector)
        price = element.get_attribute("innerText")
        logging.info("\u2714\ufe0f Prix extrait avec succès")
        return price.strip()
    finally:
        driver.quit()


def save_price_to_file(price: str, filename: Path = Path("price.txt")) -> None:
    filename.parent.mkdir(parents=True, exist_ok=True)
    filename.write_text(price, encoding="utf-8")
    logging.info("\U0001F4BE Prix enregistré dans %s", filename.resolve())


def scrape_price(url: str, selector: str, output: Path) -> None:
    price = extract_price(url, selector)
    save_price_to_file(price, output)


def price_main() -> None:
    parser = argparse.ArgumentParser(
        description="Extraire le prix d'un produit et le sauvegarder dans un fichier."
    )
    parser.add_argument("url", nargs="?", help="URL du produit (si absent, demande à l'exécution)")
    parser.add_argument("-s", "--selector", default=SPP_DEFAULT_SELECTOR, help="Sélecteur CSS du prix (defaut: %(default)s)")
    parser.add_argument("-o", "--output", default="price.txt", help="Fichier de sortie (defaut: %(default)s)")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Niveau de logging (defaut: %(default)s)")
    args = parser.parse_args()
    if not args.url:
        args.url = input("\U0001F517 Entrez l'URL du produit : ").strip()
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(levelname)s: %(message)s")
    try:
        scrape_price(args.url, args.selector, Path(args.output))
    except Exception as exc:  # noqa: BLE001
        logging.error("%s", exc)

scrap_prix_produit = types.SimpleNamespace(
    extract_price=extract_price,
    save_price_to_file=save_price_to_file,
    scrape_price=scrape_price,
    price_main=price_main,
    DEFAULT_SELECTOR=SPP_DEFAULT_SELECTOR,
)

# ----- scraper_images.py -----

DEFAULT_CSS_SELECTOR = ".product-gallery__media-list img"
ALT_JSON_PATH = Path(__file__).with_name("product_sentences.json")
USE_ALT_JSON = True

logger = logging.getLogger(__name__)

_RESERVED_PATHS: set[Path] = set()


def _safe_folder(product_name: str, base_dir: Path | str = "images") -> Path:
    safe_name = re.sub(r"[^\w\-]", "_", product_name)
    folder = Path(base_dir) / safe_name
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _open_folder(path: Path) -> None:
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
    base, ext = os.path.splitext(filename)
    candidate = folder / filename
    counter = 1
    while candidate.exists() or candidate in _RESERVED_PATHS:
        candidate = folder / f"{base}_{counter}{ext}"
        counter += 1
    _RESERVED_PATHS.add(candidate)
    return candidate


_ALT_SENTENCES_CACHE: dict[Path, dict] = {}


def _load_alt_sentences(path: Path = ALT_JSON_PATH) -> dict:
    global _ALT_SENTENCES_CACHE
    path = Path(path)
    cached = _ALT_SENTENCES_CACHE.get(path)
    if cached is not None:
        return cached
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        logger.warning("Impossible de charger %s : %s", path, exc)
        data = {}
    _ALT_SENTENCES_CACHE[path] = data
    return data


def _clean_filename(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_text = ascii_text.lower()
    ascii_text = re.sub(r"\s+", "_", ascii_text)
    ascii_text = re.sub(r"[^a-z0-9_-]", "", ascii_text)
    return ascii_text


def _rename_with_alt(path: Path, sentences: dict, warned: set[str]) -> Path:
    product_key = path.parent.name.replace("_", " ")
    phrase_list = sentences.get(product_key)
    if not phrase_list:
        if product_key not in warned:
            logger.warning("Aucune phrase ALT pour %s", product_key)
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


def _handle_image(element, folder: Path, index: int, user_agent: str) -> tuple[Path, str | None]:
    src = element.get_attribute("src") or element.get_attribute("data-src") or element.get_attribute("data-srcset")
    if not src:
        raise RuntimeError("Aucun attribut src / data-src trouvé pour l'image")
    if " " in src and "," in src:
        candidates = [s.strip().split(" ")[0] for s in src.split(",")]
        src = candidates[-1]
    logger.debug(f"Téléchargement de l'image : {src}")
    if src.startswith("data:image"):
        header, encoded = src.split(",", 1)
        ext = header.split("/")[1].split(";")[0]
        filename = f"image_base64_{index}.{ext}"
        target = _unique_path(folder, filename)
        _save_base64(encoded, target)
        return target, None
    if src.startswith("//"):
        src = "https:" + src
    raw_filename = os.path.basename(src.split("?")[0])
    filename = re.sub(r"-\d+(?=\.\w+$)", "", raw_filename)
    target = _unique_path(folder, filename)
    return target, src


def _find_product_name(driver: webdriver.Chrome) -> str:
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
    use_alt_json: bool = USE_ALT_JSON,
    *,
    alt_json_path: str | Path | None = None,
    max_threads: int = 4,
) -> dict:
    _RESERVED_PATHS.clear()
    if user_agent is None:
        try:
            path = Path("settings.json")
            if path.is_file():
                data = json.loads(path.read_text(encoding="utf-8"))
                user_agent = data.get("user_agent", USER_AGENT)
            else:
                user_agent = USER_AGENT
        except Exception:
            user_agent = USER_AGENT
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("URL must start with http:// or https://")

    driver = setup_driver()

    product_name = ""
    folder = Path()
    first_image: Path | None = None
    downloaded = 0
    skipped = 0

    if use_alt_json and alt_json_path:
        sentences = _load_alt_sentences(Path(alt_json_path))
    else:
        sentences = {}
        use_alt_json = False
    warned_missing: set[str] = set()

    try:
        logger.info("\U0001F30D Chargement de la page...")
        driver.get(url)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, css_selector)))
        product_name = _find_product_name(driver)
        folder = _safe_folder(product_name, parent_dir)
        img_elements = driver.find_elements(By.CSS_SELECTOR, css_selector)
        logger.info(f"\n\U0001F5BC {len(img_elements)} images trouvées avec le sélecteur : {css_selector}\n")
        total = len(img_elements)
        pbar = tqdm(range(total), desc="\U0001F53D Téléchargement des images")
        pbar_update = getattr(pbar, "update", lambda n=1: None)
        pbar_close = getattr(pbar, "close", lambda: None)
        futures: dict = {}
        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            for idx, img in enumerate(img_elements, start=1):
                try:
                    path, url_to_download = _handle_image(img, folder, idx, user_agent)
                    WebDriverWait(driver, 5).until(
                        lambda d: img.get_attribute("src") or img.get_attribute("data-src") or img.get_attribute("data-srcset")
                    )
                    if url_to_download is None:
                        if use_alt_json:
                            path = _rename_with_alt(path, sentences, warned_missing)
                        downloaded += 1
                        if first_image is None:
                            first_image = path
                        pbar_update(1)
                        if progress_callback:
                            progress_callback(idx, total)
                    else:
                        fut = executor.submit(_download_binary, url_to_download, path, user_agent)
                        futures[fut] = (idx, path)
                except Exception as exc:
                    logger.error("\u274c Erreur pour l'image %s : %s", idx, exc)
            for fut in as_completed(futures):
                idx, path = futures[fut]
                try:
                    fut.result()
                    if use_alt_json:
                        path = _rename_with_alt(path, sentences, warned_missing)
                    downloaded += 1
                    if first_image is None:
                        first_image = path
                except Exception as exc:
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


def scraper_images_main() -> None:
    parser = argparse.ArgumentParser(description="Télécharger toutes les images d'un produit WooCommerce.")
    parser.add_argument("url", nargs="?", help="URL du produit (si absent, demande à l'exécution)")
    parser.add_argument("-s", "--selector", default=DEFAULT_CSS_SELECTOR, help="Sélecteur CSS des images (defaut: %(default)s)")
    parser.add_argument("-d", "--dest", "--parent-dir", dest="parent_dir", default="images", help="Dossier parent des images (defaut: %(default)s)")
    parser.add_argument("--urls", help="Fichier contenant une liste d'URLs (une par ligne)")
    parser.add_argument("--preview", action="store_true", help="Ouvrir le dossier des images après téléchargement")
    parser.add_argument("--user-agent", default=USER_AGENT, help="User-Agent à utiliser pour les requêtes (defaut: %(default)s)")
    parser.add_argument("--use-alt-json", dest="use_alt_json", action="store_true" if not USE_ALT_JSON else "store_false", help=("Activer" if not USE_ALT_JSON else "Désactiver") + " le renommage via product_sentences.json")
    parser.add_argument("--alt-json-path", default=str(ALT_JSON_PATH), help="Chemin du fichier JSON pour le renommage (defaut: %(default)s)")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Niveau de logging (defaut: %(default)s)")
    parser.add_argument("--max-threads", type=int, default=4, help="Nombre maximal de threads pour les telechargements (defaut: %(default)s)")
    parser.add_argument("--jobs", type=int, default=1, help="Nombre maximal de pages a traiter en parallele (defaut: %(default)s)")
    parser.set_defaults(use_alt_json=USE_ALT_JSON)
    args = parser.parse_args()

    if not args.alt_json_path:
        args.alt_json_path = None

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

    logging.basicConfig(level=getattr(logging, args.log_level), format="%(levelname)s: %(message)s")

    if args.jobs > 1 and len(urls_list) > 1:
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            futures = {
                executor.submit(
                    scraper_images.download_images,
                    url,
                    css_selector=args.selector,
                    parent_dir=args.parent_dir,
                    user_agent=args.user_agent,
                    use_alt_json=args.use_alt_json,
                    alt_json_path=args.alt_json_path,
                    max_threads=args.max_threads,
                ): url
                for url in urls_list
            }
            for fut in as_completed(futures):
                try:
                    info = fut.result()
                    if args.preview:
                        scraper_images._open_folder(info["folder"])
                except ValueError as exc:
                    logger.error("Erreur : %s", exc)
    else:
        for url in urls_list:
            try:
                info = scraper_images.download_images(
                    url,
                    css_selector=args.selector,
                    parent_dir=args.parent_dir,
                    user_agent=args.user_agent,
                    use_alt_json=args.use_alt_json,
                    alt_json_path=args.alt_json_path,
                    max_threads=args.max_threads,
                )
                if args.preview:
                    scraper_images._open_folder(info["folder"])
            except ValueError as exc:
                logger.error("Erreur : %s", exc)

scraper_images = types.SimpleNamespace(
    download_images=download_images,
    scraper_images_main=scraper_images_main,
    DEFAULT_CSS_SELECTOR=DEFAULT_CSS_SELECTOR,
    ALT_JSON_PATH=ALT_JSON_PATH,
    USE_ALT_JSON=USE_ALT_JSON,
    _open_folder=_open_folder,
)
def load_stylesheet(path: str = "style.qss") -> None:
    """Apply the application's stylesheet if available."""
    app = QApplication.instance()
    if app is None:
        return
    qss_path = Path(path)
    if qss_path.exists():
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))


class QtLogHandler(logging.Handler):
    """Forward logging records to a Qt signal."""

    def __init__(self, signal):
        super().__init__()
        self._signal = signal

    def emit(self, record):
        msg = self.format(record)
        self._signal.emit(msg)


class ToggleSwitch(QCheckBox):
    """Simple ON/OFF switch widget."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._offset = 2
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(40, 20)
        QCheckBox.setChecked(self, False)
        self.setStyleSheet("QCheckBox::indicator { width:0; height:0; }")

    def mouseReleaseEvent(self, event) -> None:  # noqa: D401
        super().mouseReleaseEvent(event)
        self.setChecked(not self.isChecked())

    def setChecked(self, checked: bool) -> None:  # type: ignore[override]
        self._offset = self.width() - self.height() + 2 if checked else 2
        super().setChecked(checked)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: D401
        radius = self.height() / 2
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#4cd964" if self.isChecked() else "#bbbbbb"))
        painter.drawRoundedRect(0, 0, self.width(), self.height(), radius, radius)
        painter.setBrush(QColor("white"))
        painter.drawEllipse(QRect(self._offset, 2, self.height() - 4, self.height() - 4))


class CollapsibleSection(QWidget):
    """Simple collapsible section used for the sidebar."""

    def __init__(self, title: str, icon: QIcon, callback) -> None:
        super().__init__()
        self._title = title
        self._callback = callback
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.header = QToolButton()
        self.header.setText(self._title)
        self.header.setIcon(icon)
        self.header.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.header.setCheckable(True)
        self.header.clicked.connect(callback)
        layout.addWidget(self.header)


class ScrapLienWorker(QThread):
    log = Signal(str)
    finished = Signal()

    def __init__(
        self,
        url: str,
        output: Path,
        selector: str,
        log_level: str,
        output_format: str,
    ):
        super().__init__()
        self.url = url
        self.output = output
        self.selector = selector
        self.log_level = log_level
        self.output_format = output_format

    def run(self) -> None:
        logger = logging.getLogger()
        logger.setLevel(getattr(logging, self.log_level, logging.INFO))
        handler = QtLogHandler(self.log)
        formatter = logging.Formatter("%(levelname)s: %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        stream = io.StringIO()
        stream_handler = logging.StreamHandler(stream)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
        try:
            scrape_collection(
                self.url,
                self.output,
                self.selector,
                SLC_DEFAULT_NEXT_SELECTOR,
                self.output_format,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("%s", exc)
        finally:
            logger.removeHandler(handler)
            logger.removeHandler(stream_handler)
            self.finished.emit()


class ScraperImagesWorker(QThread):
    """Background worker to download images using scraper_images."""

    log = Signal(str)
    progress = Signal(int, int)
    finished = Signal()
    preview_path = Signal(str)

    def __init__(
        self,
        urls: list[str],
        parent_dir: Path,
        selector: str,
        open_folder: bool,
        show_preview: bool,
        alt_json: str | None,
        max_threads: int = 4,
        max_jobs: int = 1,
    ):
        super().__init__()
        self.urls = urls
        self.parent_dir = parent_dir
        self.selector = selector
        self.open_folder = open_folder
        self.show_preview = show_preview
        self.alt_json = alt_json
        self.max_threads = max_threads
        self.max_jobs = max_jobs

    def run(self) -> None:
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        handler = QtLogHandler(self.log)
        formatter = logging.Formatter("%(levelname)s: %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        try:
            images_done = 0
            total_images = 0
            lock = threading.Lock()

            def make_cb() -> Callable[[int, int], None]:
                first = True

                def cb(i: int, t: int) -> None:
                    nonlocal first, images_done, total_images
                    with lock:
                        if first:
                            total_images += t
                            first = False
                        images_done += 1
                        self.progress.emit(images_done, total_images)

                return cb

            self.progress.emit(0, 0)

            preview_sent = False
            with ThreadPoolExecutor(max_workers=self.max_jobs) as executor:
                future_to_url = {
                    executor.submit(
                        scraper_images.download_images,
                        url,
                        css_selector=self.selector,
                        parent_dir=self.parent_dir,
                        progress_callback=make_cb(),
                        alt_json_path=self.alt_json,
                        max_threads=self.max_threads,
                    ): url
                    for url in self.urls
                }

                for fut in as_completed(future_to_url):
                    url = future_to_url[fut]
                    try:
                        info = fut.result()
                        folder = info["folder"]
                        if (
                            self.show_preview
                            and not preview_sent
                            and info.get("first_image")
                        ):
                            self.preview_path.emit(str(info["first_image"]))
                            preview_sent = True
                        if self.open_folder:
                            scraper_images._open_folder(folder)
                    except Exception as exc:  # noqa: BLE001
                        logger.error("%s", exc)
        except Exception as exc:  # noqa: BLE001
            logger.error("%s", exc)
        finally:
            logger.removeHandler(handler)
            self.finished.emit()


class ScrapDescriptionWorker(QThread):
    """Background worker to extract and save product descriptions."""

    log = Signal(str)
    finished = Signal()

    def __init__(self, url: str, selector: str, output: Path):
        super().__init__()
        self.url = url
        self.selector = selector
        self.output = output

    def run(self) -> None:
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        handler = QtLogHandler(self.log)
        formatter = logging.Formatter("%(levelname)s: %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        try:
            scrape_description(
                self.url, self.selector, self.output
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("%s", exc)
        finally:
            logger.removeHandler(handler)
            self.finished.emit()


class ScrapPriceWorker(QThread):
    """Background worker to extract and save product price."""

    log = Signal(str)
    finished = Signal()

    def __init__(self, url: str, selector: str, output: Path) -> None:
        super().__init__()
        self.url = url
        self.selector = selector
        self.output = output

    def run(self) -> None:
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        handler = QtLogHandler(self.log)
        formatter = logging.Formatter("%(levelname)s: %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        try:
            scrape_price(self.url, self.selector, self.output)
        except Exception as exc:  # noqa: BLE001
            logger.error("%s", exc)
        finally:
            logger.removeHandler(handler)
            self.finished.emit()


class ScrapVariantWorker(QThread):
    """Background worker to extract and save product variants."""

    log = Signal(str)
    finished = Signal()

    def __init__(self, url: str, selector: str, output: Path) -> None:
        super().__init__()
        self.url = url
        self.selector = selector
        self.output = output

    def run(self) -> None:
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        handler = QtLogHandler(self.log)
        formatter = logging.Formatter("%(levelname)s: %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        try:
            title, mapping = moteur_variante.extract_variants_with_images(self.url)
            moteur_variante.save_images_to_file(title, mapping, self.output)
        except Exception as exc:  # noqa: BLE001
            logger.error("%s", exc)
        finally:
            logger.removeHandler(handler)
            self.finished.emit()


class VariantFetchWorker(QThread):
    """Fetch product variants with images and emit results."""

    log = Signal(str)
    result = Signal(str, dict)
    finished = Signal()

    def __init__(self, url: str) -> None:
        super().__init__()
        self.url = url

    def run(self) -> None:
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        handler = QtLogHandler(self.log)
        formatter = logging.Formatter("%(levelname)s: %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        try:
            title, mapping = moteur_variante.extract_variants_with_images(self.url)
            self.result.emit(title, mapping)
        except Exception as exc:  # noqa: BLE001
            logger.error("%s", exc)
        finally:
            logger.removeHandler(handler)
            self.finished.emit()


class PageProfiles(QWidget):
    """Manage site profiles (selectors)."""

    def __init__(self, profile_manager: SiteProfileManager, main_window) -> None:
        super().__init__()
        self.profile_manager = profile_manager
        self.main_window = main_window

        layout = QVBoxLayout(self)

        self.combo_profiles = QComboBox()
        layout.addWidget(QLabel("Profils existants"))
        layout.addWidget(self.combo_profiles)

        self.input_name = QLineEdit()
        layout.addWidget(QLabel("Nom du profil"))
        layout.addWidget(self.input_name)

        self.input_images = QLineEdit()
        layout.addWidget(QLabel("Sélecteur Images"))
        layout.addWidget(self.input_images)

        self.input_desc = QLineEdit()
        layout.addWidget(QLabel("Sélecteur Description"))
        layout.addWidget(self.input_desc)

        self.input_collection = QLineEdit()
        layout.addWidget(QLabel("Sélecteur Collection"))
        layout.addWidget(self.input_collection)

        alt_json_layout = QHBoxLayout()
        self.input_alt_json = QLineEdit()
        alt_json_layout.addWidget(self.input_alt_json)
        self.button_alt_json = QPushButton("\U0001F4C1 Choisir un fichier json")
        self.button_alt_json.clicked.connect(self.browse_alt_json)
        alt_json_layout.addWidget(self.button_alt_json)
        layout.addWidget(QLabel("Fichier ALT JSON"))
        layout.addLayout(alt_json_layout)

        file_urls_layout = QHBoxLayout()
        self.input_urls_images = QLineEdit()
        file_urls_layout.addWidget(self.input_urls_images)
        self.button_urls_images = QPushButton("\U0001F4C1 Choisir un fichier txt")
        self.button_urls_images.clicked.connect(self.browse_urls_images)
        file_urls_layout.addWidget(self.button_urls_images)
        layout.addWidget(QLabel("Fichier URLs Images"))
        layout.addLayout(file_urls_layout)

        urls_desc_layout = QHBoxLayout()
        self.input_urls_desc = QLineEdit()
        urls_desc_layout.addWidget(self.input_urls_desc)
        self.button_urls_desc = QPushButton("\U0001F4C1 Choisir un fichier txt")
        self.button_urls_desc.clicked.connect(self.browse_urls_desc)
        urls_desc_layout.addWidget(self.button_urls_desc)
        layout.addWidget(QLabel("Fichier URLs Description"))
        layout.addLayout(urls_desc_layout)

        self.checkbox_auto = QCheckBox("Appliquer automatiquement après chargement")
        layout.addWidget(self.checkbox_auto)

        btn_layout = QHBoxLayout()
        self.button_new = QPushButton("Nouveau")
        self.button_save = QPushButton("Sauvegarder")
        self.button_load = QPushButton("Charger")
        self.button_delete = QPushButton("Supprimer")
        for b in [self.button_new, self.button_save, self.button_load, self.button_delete]:
            btn_layout.addWidget(b)
        layout.addLayout(btn_layout)
        layout.addStretch()

        self.button_new.clicked.connect(self.new_profile)
        self.button_save.clicked.connect(self.save_profile)
        self.button_load.clicked.connect(self.load_selected_profile)
        self.button_delete.clicked.connect(self.delete_profile)
        self.combo_profiles.currentIndexChanged.connect(self.populate_from_selected)

        self.refresh_profiles()

    # Utility methods
    def profile_path(self, name: str) -> Path:
        return self.profile_manager.dir / f"{name}.json"

    def refresh_profiles(self) -> None:
        self.combo_profiles.blockSignals(True)
        self.combo_profiles.clear()
        for f in sorted(self.profile_manager.dir.glob("*.json")):
            self.combo_profiles.addItem(f.stem)
        self.combo_profiles.blockSignals(False)
        if self.combo_profiles.count() > 0:
            self.combo_profiles.setCurrentIndex(0)
            self.populate_from_selected()

    def populate_from_selected(self) -> None:
        name = self.combo_profiles.currentText()
        if not name:
            return
        data = self.profile_manager.load_profile(self.profile_path(name))
        self.fill_fields(data)
        if self.checkbox_auto.isChecked():
            self.profile_manager.apply_profile_to_ui(data, self.main_window)

    def fill_fields(self, data: dict) -> None:
        self.input_name.setText(data.get("nom", ""))
        selectors = data.get("selectors", {})
        self.input_images.setText(selectors.get("images", ""))
        self.input_desc.setText(selectors.get("description", ""))
        self.input_collection.setText(selectors.get("collection", ""))
        self.input_alt_json.setText(data.get("sentences_file", ""))
        self.input_urls_images.setText(data.get("urls_file", ""))
        self.input_urls_desc.setText(data.get("desc_urls_file", ""))

    def new_profile(self) -> None:
        self.input_name.clear()
        self.input_images.clear()
        self.input_desc.clear()
        self.input_collection.clear()
        self.input_alt_json.clear()
        self.input_urls_images.clear()
        self.input_urls_desc.clear()

    def save_profile(self) -> None:
        name = self.input_name.text().strip()
        if not name:
            return
        data = {
            "nom": name,
            "selectors": {
                "images": self.input_images.text().strip(),
                "description": self.input_desc.text().strip(),
                "collection": self.input_collection.text().strip(),
            },
            "sentences_file": self.input_alt_json.text().strip(),
            "urls_file": self.input_urls_images.text().strip(),
            "desc_urls_file": self.input_urls_desc.text().strip(),
        }
        path = self.profile_path(name)
        self.profile_manager.save_profile(path, data)
        self.refresh_profiles()

    def load_selected_profile(self) -> None:
        name = self.combo_profiles.currentText()
        if not name:
            return
        data = self.profile_manager.load_profile(self.profile_path(name))
        self.fill_fields(data)
        self.profile_manager.apply_profile_to_ui(data, self.main_window)

    def delete_profile(self) -> None:
        name = self.combo_profiles.currentText()
        if not name:
            return
        path = self.profile_path(name)
        try:
            path.unlink()
        except Exception:
            pass
        self.refresh_profiles()

    def browse_urls_images(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Sélectionner un fichier", "", "Text Files (*.txt)"
        )
        if file_path:
            self.input_urls_images.setText(file_path)

    def browse_urls_desc(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Sélectionner un fichier", "", "Text Files (*.txt)"
        )
        if file_path:
            self.input_urls_desc.setText(file_path)

    def browse_alt_json(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Sélectionner un fichier", "", "JSON Files (*.json);;All Files (*)"
        )
        if file_path:
            self.input_alt_json.setText(file_path)


class PageScrapLienCollection(QWidget):
    def __init__(self, manager: SettingsManager):
        super().__init__()
        self.manager = manager
        layout = QVBoxLayout(self)

        self.input_url = QLineEdit(manager.settings.get("scrap_lien_url", ""))
        self.input_url.setPlaceholderText("URL de la collection")
        layout.addWidget(QLabel("URL de la collection"))
        layout.addWidget(self.input_url)

        self.input_output = QLineEdit(manager.settings.get("scrap_lien_output", "products.txt"))
        layout.addWidget(QLabel("Fichier de sortie"))
        layout.addWidget(self.input_output)

        self.combo_format = QComboBox()
        self.combo_format.addItems(["txt", "json", "csv"])
        self.combo_format.setCurrentText(manager.settings.get("scrap_lien_format", "txt"))
        layout.addWidget(QLabel("Format"))
        layout.addWidget(self.combo_format)

        self.input_selector = QLineEdit(
            manager.settings.get(
                "scrap_lien_selector", SLC_DEFAULT_SELECTOR
            )
        )
        # Champ géré via l'onglet Profils – non ajouté au layout
        label_selector = QLabel("Sélecteur CSS")
        self.input_selector.hide()
        label_selector.hide()

        self.combo_log = QComboBox()
        self.combo_log.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self.combo_log.setCurrentText("INFO")
        layout.addWidget(QLabel("Niveau de log"))
        layout.addWidget(self.combo_log)

        self.button_start = QPushButton("Lancer le scraping")
        layout.addWidget(self.button_start)
        self.button_start.clicked.connect(self.start_worker)

        self.button_toggle_console = QPushButton("Masquer la console")
        self.button_toggle_console.clicked.connect(self.toggle_console)
        layout.addWidget(self.button_toggle_console)


        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view)

        layout.addStretch()

        self.worker: ScrapLienWorker | None = None

        for widget in [self.input_url, self.input_output, self.input_selector]:
            widget.editingFinished.connect(self.save_fields)
        self.combo_format.currentIndexChanged.connect(self.save_fields)

    def start_worker(self) -> None:
        url = self.input_url.text().strip()
        output = Path(self.input_output.text().strip() or "products.txt")
        selector = self.input_selector.text().strip() or SLC_DEFAULT_SELECTOR
        log_level = self.combo_log.currentText()
        output_format = self.combo_format.currentText()

        if not url:
            self.log_view.appendPlainText("Veuillez renseigner l'URL.")
            return

        self.button_start.setEnabled(False)
        self.log_view.clear()

        self.save_fields()

        self.worker = ScrapLienWorker(url, output, selector, log_level, output_format)
        self.worker.log.connect(self.log_view.appendPlainText)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def on_finished(self) -> None:
        self.button_start.setEnabled(True)
        QMessageBox.information(self, "Terminé", "Le scraping des liens est terminé.")

    def toggle_console(self) -> None:
        visible = self.log_view.isVisible()
        self.log_view.setVisible(not visible)
        self.button_toggle_console.setText(
            "Afficher la console" if visible else "Masquer la console"
        )

    def save_fields(self) -> None:
        self.manager.save_setting("scrap_lien_url", self.input_url.text())
        self.manager.save_setting("scrap_lien_output", self.input_output.text())
        self.manager.save_setting("scrap_lien_selector", self.input_selector.text())
        self.manager.save_setting("scrap_lien_format", self.combo_format.currentText())


class PageScraperImages(QWidget):
    def __init__(self, manager: SettingsManager):
        super().__init__()
        self.manager = manager
        layout = QVBoxLayout(self)
        self.input_source = QLineEdit(manager.settings.get("images_url", ""))
        self.input_source.setPlaceholderText("URL unique")
        layout.addWidget(QLabel("URL unique"))
        layout.addWidget(self.input_source)

        file_layout = QHBoxLayout()
        self.input_urls_file = QLineEdit(manager.settings.get("images_file", ""))
        file_layout.addWidget(self.input_urls_file)
        self.button_file = QPushButton("\U0001F4C1 Choisir un fichier txt")
        self.button_file.clicked.connect(self.browse_file)
        file_layout.addWidget(self.button_file)
        # Champ géré via l'onglet Profils – non ajouté au layout
        label_urls = QLabel("Fichier d'URLs")
        self.input_urls_file.hide()
        self.button_file.hide()
        label_urls.hide()

        dir_layout = QHBoxLayout()
        self.input_dest = QLineEdit(manager.settings.get("images_dest", "images"))
        dir_layout.addWidget(self.input_dest)
        self.button_dir = QPushButton("\U0001F4C2 Choisir dossier")
        self.button_dir.clicked.connect(self.browse_dir)
        dir_layout.addWidget(self.button_dir)
        layout.addWidget(QLabel("Dossier parent"))
        layout.addLayout(dir_layout)

        self.input_options = QLineEdit(manager.settings.get("images_selector", ""))
        # Champ géré via l'onglet Profils – non ajouté au layout
        label_options = QLabel("Sélecteur CSS")
        self.input_options.hide()
        label_options.hide()

        self.input_alt_json = QLineEdit(
            manager.settings.get("images_alt_json", "product_sentences.json")
        )
        # Champ géré via l'onglet Profils – non ajouté au layout
        label_alt_json = QLabel("Fichier ALT JSON")
        self.input_alt_json.hide()
        label_alt_json.hide()

        self.spin_threads = QSpinBox()
        self.spin_threads.setRange(1, 32)
        self.spin_threads.setValue(manager.settings.get("images_max_threads", 4))
        layout.addWidget(QLabel("Threads parall\xc3\xa8les"))
        layout.addWidget(self.spin_threads)

        self.checkbox_preview = QCheckBox("Afficher le dossier après téléchargement")
        self.switch_preview = ToggleSwitch()
        switch_label = QLabel("Aperçu")

        checkbox_layout = QHBoxLayout()
        checkbox_layout.addWidget(self.checkbox_preview)
        checkbox_layout.addWidget(switch_label)
        checkbox_layout.addWidget(self.switch_preview)
        layout.addLayout(checkbox_layout)

        self.button_start = QPushButton("Scraper")
        layout.addWidget(self.button_start)

        self.button_delete = QPushButton("Supprimer dossiers")
        layout.addWidget(self.button_delete)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)

        self.label_timer = QLabel("Temps restant : ...")
        layout.addWidget(self.label_timer)

        self.images_done = 0
        self.total_images = 0

        self.label_preview = QLabel(alignment=Qt.AlignCenter)
        self.label_preview.setVisible(False)
        self.switch_preview.toggled.connect(self.label_preview.setVisible)
        layout.addWidget(self.label_preview)

        self.button_toggle_console = QPushButton("Masquer la console")
        self.button_toggle_console.clicked.connect(self.toggle_console)
        layout.addWidget(self.button_toggle_console)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view)
        layout.addStretch()

        self.worker: ScraperImagesWorker | None = None

        self.button_start.clicked.connect(self.start_worker)
        self.button_delete.clicked.connect(self.delete_folders)

        for widget in [
            self.input_source,
            self.input_urls_file,
            self.input_dest,
            self.input_options,
            self.input_alt_json,
        ]:
            widget.editingFinished.connect(self.save_fields)
        self.spin_threads.valueChanged.connect(self.save_fields)

    def start_worker(self) -> None:
        url = self.input_source.text().strip()
        file_path = self.input_urls_file.text().strip()
        dest = Path(self.input_dest.text().strip() or "images")
        selector = self.input_options.text().strip() or DEFAULT_CSS_SELECTOR

        urls_list: list[str] = []
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as fh:
                    urls_list = [line.strip() for line in fh if line.strip()]
            except OSError as exc:
                self.log_view.appendPlainText(f"Impossible de lire {file_path}: {exc}")
                return

        if not urls_list:
            if not url:
                self.log_view.appendPlainText("Veuillez renseigner l'URL ou choisir un fichier.")
                return
            urls_list = [url]

        self.button_start.setEnabled(False)
        self.progress.setValue(0)
        self.log_view.clear()

        self.save_fields()

        open_folder = self.checkbox_preview.isChecked()
        show_preview = self.switch_preview.isChecked()

        alt_json = self.input_alt_json.text().strip() or None
        self.worker = ScraperImagesWorker(
            urls_list,
            dest,
            selector,
            open_folder,
            show_preview,
            alt_json,
            self.spin_threads.value(),
        )
        self.worker.log.connect(self.log_view.appendPlainText)
        self.worker.progress.connect(self.update_progress)
        self.worker.preview_path.connect(self.display_preview)
        self.worker.finished.connect(self.on_finished)
        self.label_preview.clear()
        self.label_preview.setVisible(False)
        self.images_done = 0
        self.total_images = 0
        self.start_time = time.perf_counter()
        self.worker.start()

    def browse_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Sélectionner un fichier", "", "Text Files (*.txt)")
        if file_path:
            self.input_urls_file.setText(file_path)
            self.save_fields()

    def browse_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Sélectionner un dossier")
        if directory:
            self.input_dest.setText(directory)
            self.save_fields()

    def update_progress(self, done: int, total: int) -> None:
        self.images_done = done
        self.total_images = total
        value = int(done / total * 100) if total else 0
        self.progress.setValue(value)
        if done == 0 or total == 0:
            self.label_timer.setText("Temps restant : ...")
            return
        elapsed = time.perf_counter() - self.start_time
        average = elapsed / done
        remaining = (total - done) * average
        if remaining >= 60:
            minutes = int(remaining / 60 + 0.5)
            self.label_timer.setText(
                f"Temps restant : {minutes} minute(s)"
            )
        else:
            seconds = int(remaining + 0.5)
            self.label_timer.setText(
                f"Temps restant : {seconds} seconde(s)"
            )

    def toggle_console(self) -> None:
        visible = self.log_view.isVisible()
        self.log_view.setVisible(not visible)
        self.button_toggle_console.setText(
            "Afficher la console" if visible else "Masquer la console"
        )

    def on_finished(self) -> None:
        self.button_start.setEnabled(True)
        self.label_timer.setText("Temps restant : 0 seconde(s)")
        QMessageBox.information(
            self,
            "Terminé",
            "Le téléchargement des images est terminé.",
        )
        self.progress.setValue(0)

    def delete_folders(self) -> None:
        dest = Path(self.input_dest.text().strip() or "images")
        if not dest.exists():
            QMessageBox.information(self, "Info", "Le dossier spécifié n'existe pas.")
            return
        reply = QMessageBox.question(
            self,
            "Confirmer la suppression",
            f"Supprimer tout le contenu de {dest} ?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            for child in dest.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
            QMessageBox.information(self, "Supprimé", "Les dossiers ont été supprimés.")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Erreur", f"Erreur lors de la suppression : {exc}")

    def save_fields(self) -> None:
        self.manager.save_setting("images_url", self.input_source.text())
        self.manager.save_setting("images_file", self.input_urls_file.text())
        self.manager.save_setting("images_dest", self.input_dest.text())
        self.manager.save_setting("images_selector", self.input_options.text())
        self.manager.save_setting("images_alt_json", self.input_alt_json.text())
        self.manager.save_setting("images_max_threads", self.spin_threads.value())

    def display_preview(self, path: str) -> None:
        if not self.switch_preview.isChecked():
            return
        pix = QPixmap(path)
        if pix.isNull():
            return
        pix = pix.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.label_preview.setPixmap(pix)
        self.label_preview.setVisible(True)


class PageScrapDescription(QWidget):
    def __init__(self, manager: SettingsManager) -> None:
        super().__init__()
        self.manager = manager
        layout = QVBoxLayout(self)

        self.input_url = QLineEdit(manager.settings.get("desc_url", ""))
        self.input_url.setPlaceholderText("URL du produit")
        layout.addWidget(QLabel("URL du produit"))
        layout.addWidget(self.input_url)

        self.input_selector = QLineEdit(
            manager.settings.get("desc_selector", SDP_DEFAULT_SELECTOR)
        )
        # Champ géré via l'onglet Profils – non ajouté au layout
        label_selector = QLabel("Sélecteur CSS")
        self.input_selector.hide()
        label_selector.hide()

        self.input_output = QLineEdit(manager.settings.get("desc_output", "description.html"))
        layout.addWidget(QLabel("Fichier de sortie"))
        layout.addWidget(self.input_output)

        self.button_start = QPushButton("Extraire")
        layout.addWidget(self.button_start)

        self.button_toggle_console = QPushButton("Masquer la console")
        self.button_toggle_console.clicked.connect(self.toggle_console)
        layout.addWidget(self.button_toggle_console)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view)
        layout.addStretch()

        self.worker: ScrapDescriptionWorker | None = None
        self.button_start.clicked.connect(self.start_worker)

        for widget in [self.input_url, self.input_selector, self.input_output]:
            widget.editingFinished.connect(self.save_fields)

    def start_worker(self) -> None:
        url = self.input_url.text().strip()
        selector = self.input_selector.text().strip() or SDP_DEFAULT_SELECTOR
        output = Path(self.input_output.text().strip() or "description.html")

        if not url:
            self.log_view.appendPlainText("Veuillez renseigner l'URL.")
            return

        self.button_start.setEnabled(False)
        self.log_view.clear()

        self.save_fields()

        self.worker = ScrapDescriptionWorker(url, selector, output)
        self.worker.log.connect(self.log_view.appendPlainText)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def on_finished(self) -> None:
        self.button_start.setEnabled(True)
        QMessageBox.information(
            self,
            "Terminé",
            "L'extraction de la description est terminée.",
        )

    def toggle_console(self) -> None:
        visible = self.log_view.isVisible()
        self.log_view.setVisible(not visible)
        self.button_toggle_console.setText(
            "Afficher la console" if visible else "Masquer la console"
        )

    def save_fields(self) -> None:
        self.manager.save_setting("desc_url", self.input_url.text())
        self.manager.save_setting("desc_selector", self.input_selector.text())
        self.manager.save_setting("desc_output", self.input_output.text())


class PageScrapPrice(QWidget):
    def __init__(self, manager: SettingsManager) -> None:
        super().__init__()
        self.manager = manager
        layout = QVBoxLayout(self)

        self.input_url = QLineEdit(manager.settings.get("price_url", ""))
        self.input_url.setPlaceholderText("URL du produit")
        layout.addWidget(QLabel("URL du produit"))
        layout.addWidget(self.input_url)

        self.input_selector = QLineEdit(
            manager.settings.get("price_selector", SPP_DEFAULT_SELECTOR)
        )
        label_selector = QLabel("Sélecteur CSS")
        self.input_selector.hide()
        label_selector.hide()

        self.input_output = QLineEdit(manager.settings.get("price_output", "price.txt"))
        layout.addWidget(QLabel("Fichier de sortie"))
        layout.addWidget(self.input_output)

        self.button_start = QPushButton("Extraire")
        layout.addWidget(self.button_start)

        self.button_toggle_console = QPushButton("Masquer la console")
        self.button_toggle_console.clicked.connect(self.toggle_console)
        layout.addWidget(self.button_toggle_console)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view)
        layout.addStretch()

        self.worker: ScrapPriceWorker | None = None
        self.button_start.clicked.connect(self.start_worker)

        for widget in [self.input_url, self.input_selector, self.input_output]:
            widget.editingFinished.connect(self.save_fields)

    def start_worker(self) -> None:
        url = self.input_url.text().strip()
        selector = self.input_selector.text().strip() or SPP_DEFAULT_SELECTOR
        output = Path(self.input_output.text().strip() or "price.txt")

        if not url:
            self.log_view.appendPlainText("Veuillez renseigner l'URL.")
            return

        self.button_start.setEnabled(False)
        self.log_view.clear()

        self.save_fields()

        self.worker = ScrapPriceWorker(url, selector, output)
        self.worker.log.connect(self.log_view.appendPlainText)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def on_finished(self) -> None:
        self.button_start.setEnabled(True)
        QMessageBox.information(
            self,
            "Terminé",
            "L'extraction du prix est terminée.",
        )

    def toggle_console(self) -> None:
        visible = self.log_view.isVisible()
        self.log_view.setVisible(not visible)
        self.button_toggle_console.setText(
            "Afficher la console" if visible else "Masquer la console"
        )

    def save_fields(self) -> None:
        self.manager.save_setting("price_url", self.input_url.text())
        self.manager.save_setting("price_selector", self.input_selector.text())
        self.manager.save_setting("price_output", self.input_output.text())


class PageVariantScraper(QWidget):
    def __init__(self, manager: SettingsManager) -> None:
        super().__init__()
        self.manager = manager
        layout = QVBoxLayout(self)

        self.input_url = QLineEdit(manager.settings.get("variant_url", ""))
        self.input_url.setPlaceholderText("URL du produit")
        layout.addWidget(QLabel("URL du produit"))
        layout.addWidget(self.input_url)

        self.input_selector = QLineEdit(
            manager.settings.get("variant_selector", MV_DEFAULT_SELECTOR)
        )
        label_selector = QLabel("Sélecteur CSS")
        self.input_selector.hide()
        label_selector.hide()

        file_layout = QHBoxLayout()
        self.input_output = QLineEdit(manager.settings.get("variant_output", "variants.txt"))
        file_layout.addWidget(self.input_output)
        self.button_output = QPushButton("\U0001F4C1 Choisir fichier")
        self.button_output.clicked.connect(self.browse_output)
        file_layout.addWidget(self.button_output)
        layout.addWidget(QLabel("Fichier de sortie"))
        layout.addLayout(file_layout)

        self.button_start = QPushButton("Extraire variantes")
        layout.addWidget(self.button_start)

        self.button_toggle_console = QPushButton("Masquer la console")
        self.button_toggle_console.clicked.connect(self.toggle_console)
        layout.addWidget(self.button_toggle_console)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view)
        layout.addStretch()

        self.worker: ScrapVariantWorker | None = None
        self.button_start.clicked.connect(self.start_worker)

        for w in [self.input_url, self.input_selector, self.input_output]:
            w.editingFinished.connect(self.save_fields)

    def browse_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Fichier de sortie",
            "variants.txt",
            "Text Files (*.txt);;CSV Files (*.csv)",
        )
        if path:
            self.input_output.setText(path)

    def start_worker(self) -> None:
        url = self.input_url.text().strip()
        selector = self.input_selector.text().strip() or MV_DEFAULT_SELECTOR
        output = Path(self.input_output.text().strip() or "variants.txt")
        if not url:
            self.log_view.appendPlainText("Veuillez renseigner l'URL.")
            return
        self.button_start.setEnabled(False)
        self.log_view.clear()
        self.save_fields()
        self.worker = ScrapVariantWorker(url, selector, output)
        self.worker.log.connect(self.log_view.appendPlainText)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def on_finished(self) -> None:
        self.button_start.setEnabled(True)
        QMessageBox.information(self, "Terminé", "L'extraction des variantes est terminée.")

    def toggle_console(self) -> None:
        visible = self.log_view.isVisible()
        self.log_view.setVisible(not visible)
        self.button_toggle_console.setText(
            "Afficher la console" if visible else "Masquer la console"
        )

    def save_fields(self) -> None:
        self.manager.save_setting("variant_url", self.input_url.text())
        self.manager.save_setting("variant_selector", self.input_selector.text())
        self.manager.save_setting("variant_output", self.input_output.text())


class PageLinkGenerator(QWidget):
    """Generate image URLs for WooCommerce uploads from a local folder."""

    def __init__(self, manager: SettingsManager) -> None:
        super().__init__()
        self.manager = manager
        layout = QVBoxLayout(self)

        self.input_base_url = QLineEdit(manager.settings.get("linkgen_base_url", "https://www.planetebob.fr"))
        layout.addWidget(QLabel("Domaine WooCommerce"))
        layout.addWidget(self.input_base_url)

        self.input_date = QLineEdit(manager.settings.get("linkgen_date", "2025/07"))
        layout.addWidget(QLabel("Date (format YYYY/MM)"))
        layout.addWidget(self.input_date)

        self.button_folder = QPushButton("Choisir le dossier d'images")
        self.button_folder.clicked.connect(self.choose_folder)
        layout.addWidget(self.button_folder)

        self.output_links = QTextEdit()
        self.output_links.setPlaceholderText("Les URLs g\u00e9n\u00e9r\u00e9es s'afficheront ici.")
        layout.addWidget(self.output_links)

        actions = QHBoxLayout()
        self.button_generate = QPushButton("G\u00e9n\u00e9rer")
        self.button_generate.clicked.connect(self.generate_links)
        actions.addWidget(self.button_generate)

        self.button_copy = QPushButton("Copier les liens")
        self.button_copy.clicked.connect(self.copy_to_clipboard)
        actions.addWidget(self.button_copy)

        self.button_export = QPushButton("Exporter en .txt")
        self.button_export.clicked.connect(self.export_to_txt)
        actions.addWidget(self.button_export)

        layout.addLayout(actions)
        layout.addStretch()

        self.folder_path = manager.settings.get("linkgen_folder", "")
        if self.folder_path:
            self.button_folder.setText(f"Dossier : {os.path.basename(self.folder_path)}")

        for widget in [self.input_base_url, self.input_date]:
            widget.editingFinished.connect(self.save_fields)

    def choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "S\u00e9lectionner un dossier")
        if folder:
            self.folder_path = folder
            self.button_folder.setText(f"Dossier : {os.path.basename(folder)}")
            self.save_fields()

    def generate_links(self) -> None:
        if not self.folder_path:
            QMessageBox.warning(self, "Erreur", "Veuillez choisir un dossier.")
            return

        base_url = self.input_base_url.text().strip().rstrip("/")
        date_path = self.input_date.text().strip()

        links: list[str] = []
        for root, _, files in os.walk(self.folder_path):
            for fname in files:
                if fname.lower().endswith((
                    ".webp",
                    ".jpg",
                    ".jpeg",
                    ".png",
                )):
                    file_url = (
                        f"{base_url}/wp-content/uploads/{date_path}/{fname}"
                    )
                    links.append(file_url)

        if links:
            self.output_links.setText("\n".join(links))
        else:
            self.output_links.setText("Aucune image valide trouv\u00e9e dans le dossier.")
        QMessageBox.information(self, "Terminé", "La génération des liens est terminée.")

    def copy_to_clipboard(self) -> None:
        clipboard: QClipboard = QApplication.clipboard()
        clipboard.setText(self.output_links.toPlainText())
        QMessageBox.information(self, "Copi\u00e9", "Les liens ont \u00e9t\u00e9 copi\u00e9s dans le presse-papiers.")

    def export_to_txt(self) -> None:
        if not self.output_links.toPlainText():
            QMessageBox.warning(self, "Erreur", "Aucun lien \u00e0 exporter.")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Enregistrer sous", "liens_images.txt", "Fichier texte (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.output_links.toPlainText())
            QMessageBox.information(self, "Export\u00e9", "Les liens ont \u00e9t\u00e9 enregistr\u00e9s avec succ\u00e8s.")

    def save_fields(self) -> None:
        self.manager.save_setting("linkgen_base_url", self.input_base_url.text())
        self.manager.save_setting("linkgen_date", self.input_date.text())
        self.manager.save_setting("linkgen_folder", self.folder_path)


class Alpha2Widget(QWidget):
    """Scrape images then variants using a single URL."""

    def __init__(self, manager: SettingsManager) -> None:
        super().__init__()
        self.manager = manager
        self._export_rows: list[dict[str, str]] = []

        main_layout = QVBoxLayout(self)

        # --- Inputs -----------------------------------------------------
        group_inputs = QGroupBox("Entrées utilisateur")
        inputs_layout = QVBoxLayout(group_inputs)

        self.input_url = QLineEdit(manager.settings.get("alpha2_url", ""))
        self.input_url.setPlaceholderText("URL du produit")
        inputs_layout.addWidget(QLabel("URL du produit"))
        inputs_layout.addWidget(self.input_url)

        dir_layout = QHBoxLayout()
        self.input_dir = QLineEdit(manager.settings.get("alpha2_parent", "images"))
        dir_layout.addWidget(self.input_dir)
        self.button_dir = QPushButton("\U0001F4C2 Choisir dossier")
        self.button_dir.clicked.connect(self.browse_dir)
        dir_layout.addWidget(self.button_dir)
        inputs_layout.addWidget(QLabel("Dossier parent"))
        inputs_layout.addLayout(dir_layout)

        self.spin_threads = QSpinBox()
        self.spin_threads.setRange(1, 32)
        self.spin_threads.setValue(manager.settings.get("alpha2_threads", 3))
        inputs_layout.addWidget(QLabel("Threads parallèles"))
        inputs_layout.addWidget(self.spin_threads)
        inputs_layout.addStretch()

        # --- Actions ----------------------------------------------------
        group_actions = QGroupBox("Actions")
        actions_layout = QVBoxLayout(group_actions)
        self.button_start = QPushButton("Lancer le Scraping complet")
        self.button_start.clicked.connect(self.start_full_scraping)
        self.button_delete = QPushButton("Supprimer les dossiers")
        self.button_delete.clicked.connect(self.delete_folders)
        actions_layout.addWidget(self.button_start)
        actions_layout.addWidget(self.button_delete)
        actions_layout.addStretch()

        # --- State & Console -------------------------------------------
        group_state = QGroupBox("État & Console")
        state_layout = QVBoxLayout(group_state)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        state_layout.addWidget(self.progress)
        self.label_timer = QLabel("Temps restant : ...")
        state_layout.addWidget(self.label_timer)
        self.button_toggle_console = QPushButton("Masquer la console")
        self.button_toggle_console.clicked.connect(self.toggle_console)
        state_layout.addWidget(self.button_toggle_console)
        self.log_view = QPlainTextEdit(readOnly=True)
        state_layout.addWidget(self.log_view)
        state_layout.addStretch()

        # --- Export -----------------------------------------------------
        group_export = QGroupBox("Export")
        export_layout = QVBoxLayout(group_export)
        self.button_export = QPushButton("Exporter Excel")
        self.button_export.clicked.connect(self.export_excel)
        export_layout.addWidget(self.button_export)
        export_layout.addStretch()

        main_layout.addWidget(group_inputs)
        main_layout.addWidget(group_actions)
        main_layout.addWidget(group_state)
        main_layout.addWidget(group_export)
        main_layout.addStretch()

        self.images_worker: ScraperImagesWorker | None = None
        self.variant_worker: VariantFetchWorker | None = None

        for w in [self.input_url, self.input_dir]:
            w.editingFinished.connect(self.save_fields)
        self.spin_threads.valueChanged.connect(self.save_fields)

    # --- Slots ---------------------------------------------------------
    def browse_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Sélectionner un dossier")
        if directory:
            self.input_dir.setText(directory)
            self.save_fields()

    def start_full_scraping(self) -> None:
        url = self.input_url.text().strip()
        if not url:
            self.log_view.appendPlainText("Veuillez renseigner l'URL.")
            return

        dest = Path(self.input_dir.text().strip() or "images")
        selector = self.manager.settings.get(
            "images_selector",
            DEFAULT_CSS_SELECTOR,
        )

        self.button_start.setEnabled(False)
        self.progress.setValue(0)
        self.log_view.clear()

        self.save_fields()

        self.images_worker = ScraperImagesWorker(
            [url],
            dest,
            selector,
            False,
            False,
            None,
            self.spin_threads.value(),
        )
        self.images_worker.log.connect(self.log_view.appendPlainText)
        self.images_worker.progress.connect(self.update_progress)
        self.images_worker.finished.connect(self.start_variant_phase)

        self.images_done = 0
        self.total_images = 0
        self.start_time = time.perf_counter()
        self.images_worker.start()

    def start_variant_phase(self) -> None:
        url = self.input_url.text().strip()
        self.variant_worker = VariantFetchWorker(url)
        self.variant_worker.log.connect(self.log_view.appendPlainText)
        self.variant_worker.result.connect(self.process_variants)
        self.variant_worker.finished.connect(self.on_variant_finished)
        self.variant_worker.start()

    def process_variants(self, title: str, mapping: dict) -> None:
        domain = self.manager.settings.get("linkgen_base_url", "https://example.com")
        date_path = self.manager.settings.get("linkgen_date", "2025/07")
        self._export_rows = []
        self.log_view.appendPlainText(title)
        for name, img in mapping.items():
            wp_url = self._build_wp_url(domain, date_path, img)
            self.log_view.appendPlainText(f"{name} -> {wp_url}")
            self._export_rows.append({"Product": title, "Variant": name, "Image": wp_url})

    def update_progress(self, done: int, total: int) -> None:
        self.images_done = done
        self.total_images = total
        value = int(done / total * 100) if total else 0
        self.progress.setValue(value)
        if done == 0 or total == 0:
            self.label_timer.setText("Temps restant : ...")
            return
        elapsed = time.perf_counter() - self.start_time
        average = elapsed / done
        remaining = (total - done) * average
        if remaining >= 60:
            minutes = int(remaining / 60 + 0.5)
            self.label_timer.setText(f"Temps restant : {minutes} minute(s)")
        else:
            seconds = int(remaining + 0.5)
            self.label_timer.setText(f"Temps restant : {seconds} seconde(s)")

    def toggle_console(self) -> None:
        visible = self.log_view.isVisible()
        self.log_view.setVisible(not visible)
        self.button_toggle_console.setText(
            "Afficher la console" if visible else "Masquer la console"
        )

    def on_variant_finished(self) -> None:
        self.button_start.setEnabled(True)
        self.label_timer.setText("Temps restant : 0 seconde(s)")
        QMessageBox.information(self, "Terminé", "Le scraping complet est terminé.")
        self.progress.setValue(0)

    def delete_folders(self) -> None:
        dest = Path(self.input_dir.text().strip() or "images")
        if not dest.exists():
            QMessageBox.information(self, "Info", "Le dossier spécifié n'existe pas.")
            return
        reply = QMessageBox.question(
            self,
            "Confirmer la suppression",
            f"Supprimer tout le contenu de {dest} ?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            for child in dest.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
            QMessageBox.information(self, "Supprimé", "Les dossiers ont été supprimés.")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Erreur", f"Erreur lors de la suppression : {exc}")

    def export_excel(self) -> None:
        if not self._export_rows:
            QMessageBox.warning(self, "Erreur", "Aucune donnée à exporter.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer sous", "resultats.xlsx", "Excel (*.xlsx)"
        )
        if not path:
            return
        import pandas as pd

        df = pd.DataFrame(self._export_rows)
        try:
            df.to_excel(path, index=False)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Erreur", str(exc))
        else:
            QMessageBox.information(self, "Exporté", "Fichier enregistré")

    def save_fields(self) -> None:
        self.manager.save_setting("alpha2_url", self.input_url.text())
        self.manager.save_setting("alpha2_parent", self.input_dir.text())
        self.manager.save_setting("alpha2_threads", self.spin_threads.value())

    @staticmethod
    def _build_wp_url(domain: str, date_path: str, img_url: str) -> str:
        filename = img_url.split("/")[-1].split("?")[0]
        filename = re.sub(r"-\d+(?=\.\w+$)", "", filename)
        domain = domain.rstrip("/")
        date_path = date_path.strip("/")
        return f"{domain}/wp-content/uploads/{date_path}/{filename}"



class PageSettings(QWidget):
    """UI page allowing the user to customise the application."""

    def __init__(self, manager: SettingsManager, apply_cb) -> None:
        super().__init__()
        self.manager = manager
        self.apply_cb = apply_cb
        layout = QVBoxLayout(self)

        self.input_button_bg = QLineEdit(manager.settings["button_bg_color"])
        layout.addWidget(QLabel("Couleur de fond des boutons"))
        layout.addWidget(self.input_button_bg)

        self.input_button_text = QLineEdit(manager.settings["button_text_color"])
        layout.addWidget(QLabel("Couleur du texte des boutons"))
        layout.addWidget(self.input_button_text)

        self.combo_theme = QComboBox()
        self.combo_theme.addItems(["clair", "sombre"])
        self.combo_theme.setCurrentIndex(1 if manager.settings["theme"] == "dark" else 0)
        layout.addWidget(QLabel("Th\u00e8me global"))
        layout.addWidget(self.combo_theme)

        self.spin_radius_button = QSpinBox()
        self.spin_radius_button.setRange(0, 30)
        self.spin_radius_button.setValue(manager.settings["button_radius"])
        layout.addWidget(QLabel("Radius des boutons"))
        layout.addWidget(self.spin_radius_button)

        self.spin_radius_input = QSpinBox()
        self.spin_radius_input.setRange(0, 30)
        self.spin_radius_input.setValue(manager.settings["lineedit_radius"])
        layout.addWidget(QLabel("Radius des champs de saisie"))
        layout.addWidget(self.spin_radius_input)

        self.spin_radius_console = QSpinBox()
        self.spin_radius_console.setRange(0, 30)
        self.spin_radius_console.setValue(manager.settings["console_radius"])
        layout.addWidget(QLabel("Radius de la console"))
        layout.addWidget(self.spin_radius_console)

        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(QFont(manager.settings["font_family"]))
        layout.addWidget(QLabel("Police"))
        layout.addWidget(self.font_combo)

        self.spin_font_size = QSpinBox()
        self.spin_font_size.setRange(6, 30)
        self.spin_font_size.setValue(manager.settings["font_size"])
        layout.addWidget(QLabel("Taille de police"))
        layout.addWidget(self.spin_font_size)

        self.checkbox_anim = QCheckBox("Activer les animations")
        self.checkbox_anim.setChecked(manager.settings["animations"])
        layout.addWidget(self.checkbox_anim)

        self.checkbox_update = QCheckBox("Autoriser la mise à jour (git pull)")
        self.checkbox_update.setChecked(manager.settings.get("enable_update", True))
        layout.addWidget(self.checkbox_update)

        self.checkbox_headless = QCheckBox("Exécuter Selenium en mode headless")
        self.checkbox_headless.setChecked(manager.settings.get("headless", True))
        layout.addWidget(self.checkbox_headless)

        self.input_driver_path = QLineEdit(manager.settings.get("driver_path", ""))
        layout.addWidget(QLabel("Chemin ChromeDriver"))
        layout.addWidget(self.input_driver_path)

        self.input_user_agent = QLineEdit(
            manager.settings.get("user_agent", USER_AGENT)
        )
        layout.addWidget(QLabel("User-Agent"))
        layout.addWidget(self.input_user_agent)

        self.button_reset = QPushButton("R\u00e9initialiser les param\u00e8tres")
        layout.addWidget(self.button_reset)

        self.button_update = QPushButton("\ud83d\udd04 Mettre \u00e0 jour l'app (Git Pull)")
        layout.addWidget(self.button_update)

        layout.addStretch()

        for w in [
            self.input_button_bg,
            self.input_button_text,
            self.combo_theme,
            self.spin_radius_button,
            self.spin_radius_input,
            self.spin_radius_console,
            self.font_combo,
            self.spin_font_size,
            self.checkbox_anim,
            self.checkbox_update,
            self.checkbox_headless,
            self.input_driver_path,
            self.input_user_agent,
        ]:
            if isinstance(w, QLineEdit):
                w.editingFinished.connect(self.update_settings)
            elif isinstance(w, QComboBox):
                w.currentIndexChanged.connect(self.update_settings)
            elif isinstance(w, QSpinBox):
                w.valueChanged.connect(self.update_settings)
            elif isinstance(w, QCheckBox):
                w.stateChanged.connect(self.update_settings)
            elif isinstance(w, QFontComboBox):
                w.currentFontChanged.connect(self.update_settings)

        self.button_reset.clicked.connect(self.reset_settings)
        self.button_update.clicked.connect(self.update_and_restart)

    def update_settings(self) -> None:
        s = self.manager.settings
        s["button_bg_color"] = self.input_button_bg.text() or s["button_bg_color"]
        s["button_text_color"] = self.input_button_text.text() or s["button_text_color"]
        s["theme"] = "dark" if self.combo_theme.currentIndex() == 1 else "light"
        s["button_radius"] = self.spin_radius_button.value()
        s["lineedit_radius"] = self.spin_radius_input.value()
        s["console_radius"] = self.spin_radius_console.value()
        s["font_family"] = self.font_combo.currentFont().family()
        s["font_size"] = self.spin_font_size.value()
        s["animations"] = self.checkbox_anim.isChecked()
        s["enable_update"] = self.checkbox_update.isChecked()
        s["headless"] = self.checkbox_headless.isChecked()
        s["driver_path"] = self.input_driver_path.text().strip()
        s["user_agent"] = self.input_user_agent.text().strip() or USER_AGENT
        self.manager.save_setting("headless", s["headless"])
        self.manager.save_setting("user_agent", s["user_agent"])
        self.manager.save()
        self.apply_cb()

    def reset_settings(self) -> None:
        self.manager.reset()
        self.input_button_bg.setText(self.manager.settings["button_bg_color"])
        self.input_button_text.setText(self.manager.settings["button_text_color"])
        self.combo_theme.setCurrentIndex(1 if self.manager.settings["theme"] == "dark" else 0)
        self.spin_radius_button.setValue(self.manager.settings["button_radius"])
        self.spin_radius_input.setValue(self.manager.settings["lineedit_radius"])
        self.spin_radius_console.setValue(self.manager.settings["console_radius"])
        self.font_combo.setCurrentFont(QFont(self.manager.settings["font_family"]))
        self.spin_font_size.setValue(self.manager.settings["font_size"])
        self.checkbox_anim.setChecked(self.manager.settings["animations"])
        self.checkbox_update.setChecked(self.manager.settings.get("enable_update", True))
        self.checkbox_headless.setChecked(self.manager.settings.get("headless", True))
        self.input_driver_path.setText(self.manager.settings.get("driver_path", ""))
        self.input_user_agent.setText(
            self.manager.settings.get("user_agent", USER_AGENT)
        )
        self.manager.save()
        self.apply_cb()

    def update_and_restart(self) -> None:
        """Run git pull after confirmation and restart the app if successful."""
        if not self.manager.settings.get("enable_update", True):
            QMessageBox.information(
                self,
                "Mise \u00e0 jour d\u00e9sactiv\u00e9e",
                "La mise \u00e0 jour par git pull est d\u00e9sactiv\u00e9e dans les param\u00e8tres.",
            )
            return

        reply = QMessageBox.question(
            self,
            "Confirmer la mise \u00e0 jour",
            "Ex\u00e9cuter 'git pull' puis red\u00e9marrer l'application ?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            output = subprocess.check_output(
                ["git", "pull", "origin", "main"],
                stderr=subprocess.STDOUT,
                text=True,
            )
        except FileNotFoundError:
            QMessageBox.critical(
                self,
                "Erreur",
                "Git n'est pas install\u00e9 ou introuvable.",
            )
            return
        except subprocess.CalledProcessError as exc:
            msg = exc.output or str(exc)
            low = msg.lower()
            if "unable to access" in low or "could not resolve host" in low:
                msg = f"Erreur r\u00e9seau lors de la mise \u00e0 jour :\n{msg}"
            QMessageBox.critical(
                self,
                "Erreur lors de la mise \u00e0 jour",
                msg,
            )
            return

        QMessageBox.information(self, "Mise \u00e0 jour", output)
        QTimer.singleShot(1000, lambda: os.execv(sys.executable, [sys.executable] + sys.argv))


class MainWindow(QMainWindow):
    def __init__(self, settings: SettingsManager):
        super().__init__()
        self.settings = settings
        self.setWindowTitle("Interface Py")

        self.profile_manager = SiteProfileManager()

        # Sidebar buttons
        labels = [
            "Profils",
            "Scrap Liens Collection",
            "Scraper Images",
            "Scrap Description",
            "Scrap Prix",
            "Générateur de lien",
            "Moteur Variante",
            "Alpha",
            "Alpha 2",
            "Paramètres",
        ]

        icon_names = [
            "profile.svg",
            "links.svg",
            "images.svg",
            "description.svg",
            "variant.svg",
            "linkgen.svg",
            "variant.svg",
            "alpha.svg",
            "alpha.svg",
            "settings.svg",
        ]
        self.icon_paths = [ICONS_DIR / name for name in icon_names]

        self.sidebar = QWidget()
        side_layout = QVBoxLayout(self.sidebar)
        side_layout.setContentsMargins(0, 0, 0, 0)

        self.side_buttons: list[QToolButton] = []
        for i, (text, icon) in enumerate(zip(labels, self.icon_paths)):
            section = CollapsibleSection(
                text,
                QIcon(str(icon)),
                lambda checked=False, i=i: self.show_page(i),
            )
            side_layout.addWidget(section)
            self.side_buttons.append(section.header)
        side_layout.addStretch()

        for btn in self.side_buttons:
            btn.setIconSize(QSize(ICON_SIZE, ICON_SIZE))

        # Top bar
        self.toolbar = QToolBar()
        self.toolbar.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)

        self.toggle_sidebar_btn = QToolButton()
        self.toggle_sidebar_btn.setArrowType(Qt.LeftArrow)
        self.toggle_sidebar_btn.clicked.connect(self.toggle_sidebar)
        self.toolbar.addWidget(self.toggle_sidebar_btn)

        self.label_title = QToolButton()
        self.label_title.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.label_title.setIcon(QIcon(str(self.icon_paths[0])))
        self.label_title.setIconSize(QSize(24, 24))
        self.label_title.setText(labels[0])
        self.label_title.setEnabled(False)
        self.toolbar.addWidget(self.label_title)

        self.stack = QStackedWidget()
        self.page_profiles = PageProfiles(self.profile_manager, self)
        self.page_scrap = PageScrapLienCollection(settings)
        self.page_images = PageScraperImages(settings)
        self.page_desc = PageScrapDescription(settings)
        self.page_price = PageScrapPrice(settings)
        self.page_linkgen = PageLinkGenerator(settings)
        self.page_variants = PageVariantScraper(settings)
        self.page_alpha = AlphaEngine()
        self.page_alpha2 = Alpha2Widget(settings)
        self.page_settings = PageSettings(settings, self.apply_settings)
        self.stack.addWidget(self.page_profiles)
        self.stack.addWidget(self.page_scrap)
        self.stack.addWidget(self.page_images)
        self.stack.addWidget(self.page_desc)
        self.stack.addWidget(self.page_price)
        self.stack.addWidget(self.page_linkgen)
        self.stack.addWidget(self.page_variants)
        self.stack.addWidget(self.page_alpha)
        self.stack.addWidget(self.page_alpha2)
        self.stack.addWidget(self.page_settings)

        self.page_images.input_source.editingFinished.connect(
            lambda: self.profile_manager.detect_and_apply(
                self.page_images.input_source.text(), self
            )
        )
        self.page_scrap.input_url.editingFinished.connect(
            lambda: self.profile_manager.detect_and_apply(
                self.page_scrap.input_url.text(), self
            )
        )
        self.page_price.input_url.editingFinished.connect(
            lambda: self.profile_manager.detect_and_apply(
                self.page_price.input_url.text(), self
            )
        )

        self.stack.currentChanged.connect(self.update_title)

        # Layout central avec scroll
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        self.sidebar.setMinimumWidth(0)
        self.sidebar.setMaximumWidth(SIDEBAR_EXPANDED_WIDTH)
        self.scroll_area = QScrollArea()
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.stack)

        # Splitter to allow sidebar resizing
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.sidebar)
        self.splitter.addWidget(self.scroll_area)
        self.splitter.setStretchFactor(1, 1)
        layout.addWidget(self.splitter)
        self.setCentralWidget(container)

        self.sidebar_visible = True

        # Set initial page
        self.show_page(0)

        self.apply_settings()

    def show_page(self, index: int) -> None:
        """Display page at given index."""
        self.stack.setCurrentIndex(index)
        if 0 <= index < len(self.side_buttons):
            for i, btn in enumerate(self.side_buttons):
                btn.setChecked(i == index)
        self.update_title(index)

    def update_title(self, index: int) -> None:
        """Update title label when page changes."""
        if 0 <= index < len(self.side_buttons):
            self.label_title.setText(self.side_buttons[index].text())
            self.label_title.setIcon(QIcon(str(self.icon_paths[index])))

    def toggle_sidebar(self) -> None:
        start = self.sidebar.width()
        end = (
            SIDEBAR_COLLAPSED_WIDTH if self.sidebar_visible else SIDEBAR_EXPANDED_WIDTH
        )

        if not self.sidebar_visible:
            self.sidebar.setVisible(True)

        self._anim = QPropertyAnimation(self.sidebar, b"maximumWidth", self)
        self._anim.setDuration(200)
        self._anim.setStartValue(start)
        self._anim.setEndValue(end)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)
        self._anim.finished.connect(self._on_sidebar_toggled)
        self._anim.start()

    def _on_sidebar_toggled(self) -> None:
        self.sidebar_visible = not self.sidebar_visible

        if not self.sidebar_visible:
            for btn in self.side_buttons:
                btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
            self.sidebar.setMaximumWidth(SIDEBAR_COLLAPSED_WIDTH)
        else:
            for btn in self.side_buttons:
                btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            self.sidebar.setMaximumWidth(SIDEBAR_EXPANDED_WIDTH)

        arrow = Qt.LeftArrow if self.sidebar_visible else Qt.RightArrow
        self.toggle_sidebar_btn.setArrowType(arrow)

    def apply_settings(self) -> None:
        apply_settings(QApplication.instance(), self.settings.settings)


def main() -> None:
    app = QApplication(sys.argv)
    manager = SettingsManager()
    load_stylesheet()
    window = MainWindow(manager)
    window.resize(800, 600)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
