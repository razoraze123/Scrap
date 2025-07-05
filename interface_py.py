import sys
import logging
import io
from pathlib import Path

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
)
from PySide6.QtCore import QThread, Signal

import scrap_lien_collection
import scraper_images
import scrap_description_produit


class QtLogHandler(logging.Handler):
    """Forward logging records to a Qt signal."""

    def __init__(self, signal):
        super().__init__()
        self._signal = signal

    def emit(self, record):
        msg = self.format(record)
        self._signal.emit(msg)


class ScrapLienWorker(QThread):
    log = Signal(str)
    finished = Signal()

    def __init__(self, url: str, output: Path, selector: str, log_level: str):
        super().__init__()
        self.url = url
        self.output = output
        self.selector = selector
        self.log_level = log_level

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
            scrap_lien_collection.scrape_collection(
                self.url, self.output, self.selector
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
    progress = Signal(int)
    finished = Signal()

    def __init__(self, urls: list[str], parent_dir: Path, selector: str, preview: bool):
        super().__init__()
        self.urls = urls
        self.parent_dir = parent_dir
        self.selector = selector
        self.preview = preview

    def run(self) -> None:
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        handler = QtLogHandler(self.log)
        formatter = logging.Formatter("%(levelname)s: %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        try:
            total_urls = len(self.urls)

            def make_cb(url_index: int):
                return lambda i, t: self.progress.emit(
                    int(((url_index + i / t) / total_urls) * 100)
                )

            for idx, url in enumerate(self.urls):
                folder = scraper_images.download_images(
                    url,
                    css_selector=self.selector,
                    parent_dir=self.parent_dir,
                    progress_callback=make_cb(idx),
                )
                if self.preview:
                    scraper_images._open_folder(folder)
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
            scrap_description_produit.scrape_description(
                self.url, self.selector, self.output
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("%s", exc)
        finally:
            logger.removeHandler(handler)
            self.finished.emit()


class PageScrapLienCollection(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        self.input_url = QLineEdit()
        self.input_url.setPlaceholderText("URL de la collection")
        layout.addWidget(QLabel("URL de la collection"))
        layout.addWidget(self.input_url)

        self.input_output = QLineEdit("products.txt")
        layout.addWidget(QLabel("Fichier de sortie"))
        layout.addWidget(self.input_output)

        self.input_selector = QLineEdit(scrap_lien_collection.DEFAULT_SELECTOR)
        layout.addWidget(QLabel("Sélecteur CSS"))
        layout.addWidget(self.input_selector)

        self.combo_log = QComboBox()
        self.combo_log.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self.combo_log.setCurrentText("INFO")
        layout.addWidget(QLabel("Niveau de log"))
        layout.addWidget(self.combo_log)

        self.button_start = QPushButton("Lancer le scraping")
        self.button_start.setStyleSheet(
            """
            QPushButton {
                background-color: #007BFF;
                color: white;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 14px;
                border: none;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
            QPushButton:pressed {
                background-color: #003d80;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
            """
        )
        layout.addWidget(self.button_start)
        self.button_start.clicked.connect(self.start_worker)


        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet(
            """
            QPlainTextEdit {
                background-color: #fdfdfd;
                color: #222222;
                font-family: Consolas, \"Courier New\", monospace;
                font-size: 13px;
                border: 1px solid #cccccc;
                border-radius: 6px;
                padding: 6px;
            }
            """
        )
        layout.addWidget(self.log_view)

        layout.addStretch()

        self.worker: ScrapLienWorker | None = None

    def start_worker(self) -> None:
        url = self.input_url.text().strip()
        output = Path(self.input_output.text().strip() or "products.txt")
        selector = self.input_selector.text().strip() or scrap_lien_collection.DEFAULT_SELECTOR
        log_level = self.combo_log.currentText()

        if not url:
            self.log_view.appendPlainText("Veuillez renseigner l'URL.")
            return

        self.button_start.setEnabled(False)
        self.log_view.clear()

        self.worker = ScrapLienWorker(url, output, selector, log_level)
        self.worker.log.connect(self.log_view.appendPlainText)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def on_finished(self) -> None:
        self.button_start.setEnabled(True)


class PageScraperImages(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.input_source = QLineEdit()
        self.input_source.setPlaceholderText("URL unique")
        layout.addWidget(QLabel("URL unique"))
        layout.addWidget(self.input_source)

        file_layout = QHBoxLayout()
        self.input_urls_file = QLineEdit()
        file_layout.addWidget(self.input_urls_file)
        self.button_file = QPushButton("\U0001F4C1 Choisir un fichier txt")
        self.button_file.clicked.connect(self.browse_file)
        file_layout.addWidget(self.button_file)
        layout.addWidget(QLabel("Fichier d'URLs"))
        layout.addLayout(file_layout)

        dir_layout = QHBoxLayout()
        self.input_dest = QLineEdit("images")
        dir_layout.addWidget(self.input_dest)
        self.button_dir = QPushButton("\U0001F4C2 Choisir dossier")
        self.button_dir.clicked.connect(self.browse_dir)
        dir_layout.addWidget(self.button_dir)
        layout.addWidget(QLabel("Dossier parent"))
        layout.addLayout(dir_layout)

        self.input_options = QLineEdit()
        layout.addWidget(QLabel("Sélecteur CSS"))
        layout.addWidget(self.input_options)

        self.checkbox_preview = QCheckBox("Afficher le dossier après téléchargement")
        layout.addWidget(self.checkbox_preview)

        self.button_start = QPushButton("Scraper")
        self.button_start.setStyleSheet(
            """
            QPushButton {
                background-color: #007BFF;
                color: white;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 14px;
                border: none;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
            QPushButton:pressed {
                background-color: #003d80;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
            """
        )
        layout.addWidget(self.button_start)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setStyleSheet(
            """
            QProgressBar {
                border: 2px solid #555;
                border-radius: 5px;
                text-align: center;
                font-weight: bold;
                height: 20px;
                background-color: #f0f0f0;
            }

            QProgressBar::chunk {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #00c6ff,
                    stop: 1 #0072ff
                );
                border-radius: 5px;
                margin: 1px;
            }
            """
        )
        layout.addWidget(self.progress)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet(
            """
            QPlainTextEdit {
                background-color: #fdfdfd;
                color: #222222;
                font-family: Consolas, "Courier New", monospace;
                font-size: 13px;
                border: 1px solid #cccccc;
                border-radius: 6px;
                padding: 6px;
            }
            """
        )
        layout.addWidget(self.log_view)
        layout.addStretch()

        self.worker: ScraperImagesWorker | None = None

        self.button_start.clicked.connect(self.start_worker)

    def start_worker(self) -> None:
        url = self.input_source.text().strip()
        file_path = self.input_urls_file.text().strip()
        dest = Path(self.input_dest.text().strip() or "images")
        selector = self.input_options.text().strip() or scraper_images.DEFAULT_CSS_SELECTOR

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

        preview = self.checkbox_preview.isChecked()

        self.worker = ScraperImagesWorker(urls_list, dest, selector, preview)
        self.worker.log.connect(self.log_view.appendPlainText)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def browse_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Sélectionner un fichier", "", "Text Files (*.txt)")
        if file_path:
            self.input_urls_file.setText(file_path)

    def browse_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Sélectionner un dossier")
        if directory:
            self.input_dest.setText(directory)

    def on_finished(self) -> None:
        self.button_start.setEnabled(True)


class PageScrapDescription(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)

        self.input_url = QLineEdit()
        self.input_url.setPlaceholderText("URL du produit")
        layout.addWidget(QLabel("URL du produit"))
        layout.addWidget(self.input_url)

        self.input_selector = QLineEdit(scrap_description_produit.DEFAULT_SELECTOR)
        layout.addWidget(QLabel("Sélecteur CSS"))
        layout.addWidget(self.input_selector)

        self.input_output = QLineEdit("description.html")
        layout.addWidget(QLabel("Fichier de sortie"))
        layout.addWidget(self.input_output)

        self.button_start = QPushButton("Extraire")
        self.button_start.setStyleSheet(
            """
            QPushButton {
                background-color: #007BFF;
                color: white;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 14px;
                border: none;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
            QPushButton:pressed {
                background-color: #003d80;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
            """
        )
        layout.addWidget(self.button_start)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet(
            """
            QPlainTextEdit {
                background-color: #fdfdfd;
                color: #222222;
                font-family: Consolas, "Courier New", monospace;
                font-size: 13px;
                border: 1px solid #cccccc;
                border-radius: 6px;
                padding: 6px;
            }
            """
        )
        layout.addWidget(self.log_view)
        layout.addStretch()

        self.worker: ScrapDescriptionWorker | None = None
        self.button_start.clicked.connect(self.start_worker)

    def start_worker(self) -> None:
        url = self.input_url.text().strip()
        selector = self.input_selector.text().strip() or scrap_description_produit.DEFAULT_SELECTOR
        output = Path(self.input_output.text().strip() or "description.html")

        if not url:
            self.log_view.appendPlainText("Veuillez renseigner l'URL.")
            return

        self.button_start.setEnabled(False)
        self.log_view.clear()

        self.worker = ScrapDescriptionWorker(url, selector, output)
        self.worker.log.connect(self.log_view.appendPlainText)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def on_finished(self) -> None:
        self.button_start.setEnabled(True)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Interface Py")

        self.menu = QListWidget()
        self.menu.setMaximumWidth(150)
        self.menu.addItem("Scrap Liens Collection")
        self.menu.addItem("Scraper Images")
        self.menu.addItem("Scrap Description")

        self.stack = QStackedWidget()
        self.page_scrap = PageScrapLienCollection()
        self.page_images = PageScraperImages()
        self.page_desc = PageScrapDescription()
        self.stack.addWidget(self.page_scrap)
        self.stack.addWidget(self.page_images)
        self.stack.addWidget(self.page_desc)

        self.menu.currentRowChanged.connect(self.stack.setCurrentIndex)

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.addWidget(self.menu)
        layout.addWidget(self.stack)
        self.setCentralWidget(container)
        self.menu.setCurrentRow(0)


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(800, 600)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
