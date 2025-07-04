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
)
from PySide6.QtCore import QThread, Signal

import scrap_lien_collection
import scraper_images


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

    def __init__(self, url: str, dest: Path, selector: str):
        super().__init__()
        self.url = url
        self.dest = dest
        self.selector = selector

    def run(self) -> None:
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        handler = QtLogHandler(self.log)
        formatter = logging.Formatter("%(levelname)s: %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        try:
            scraper_images.download_images(
                self.url,
                css_selector=self.selector,
                dest_dir=self.dest,
                progress_callback=lambda i, t: self.progress.emit(int(i / t * 100)),
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
        layout.addWidget(self.button_start)
        self.button_start.clicked.connect(self.start_worker)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
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
        self.input_source.setPlaceholderText("URL ou dossier source")
        layout.addWidget(QLabel("Source"))
        layout.addWidget(self.input_source)

        self.input_dest = QLineEdit()
        layout.addWidget(QLabel("Destination"))
        layout.addWidget(self.input_dest)

        self.input_options = QLineEdit()
        layout.addWidget(QLabel("Sélecteur CSS"))
        layout.addWidget(self.input_options)

        self.button_start = QPushButton("Scraper")
        layout.addWidget(self.button_start)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view)
        layout.addStretch()

        self.worker: ScraperImagesWorker | None = None

        self.button_start.clicked.connect(self.start_worker)

    def start_worker(self) -> None:
        url = self.input_source.text().strip()
        dest = Path(self.input_dest.text().strip() or "images")
        selector = self.input_options.text().strip() or scraper_images.DEFAULT_CSS_SELECTOR

        if not url:
            self.log_view.appendPlainText("Veuillez renseigner l'URL.")
            return

        self.button_start.setEnabled(False)
        self.progress.setValue(0)
        self.log_view.clear()

        self.worker = ScraperImagesWorker(url, dest, selector)
        self.worker.log.connect(self.log_view.appendPlainText)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def on_finished(self) -> None:
        self.button_start.setEnabled(True)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Interface Py")

        self.menu = QListWidget()
        self.menu.addItem("Scrap Liens Collection")
        self.menu.addItem("Scraper Images")

        self.stack = QStackedWidget()
        self.page_scrap = PageScrapLienCollection()
        self.page_images = PageScraperImages()
        self.stack.addWidget(self.page_scrap)
        self.stack.addWidget(self.page_images)

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
