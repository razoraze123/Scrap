import sys
import logging
import io
import os
import subprocess
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
    QSpinBox,
    QFontComboBox,
    QTextEdit,
    QMessageBox,
)
from PySide6.QtCore import (
    QThread,
    Signal,
    Qt,
    QPropertyAnimation,
    Property,
    QRect,
    QTimer,
)
from PySide6.QtGui import QFont, QPainter, QColor, QPixmap, QClipboard

import scrap_lien_collection
import scraper_images
import scrap_description_produit
from settings_manager import SettingsManager, apply_settings
from site_profile_manager import SiteProfileManager


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
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(120)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(40, 20)
        QCheckBox.setChecked(self, False)
        self.setStyleSheet("QCheckBox::indicator { width:0; height:0; }")

    def offset(self) -> int:  # type: ignore[override]
        return self._offset

    def setOffset(self, value: int) -> None:  # type: ignore[override]
        self._offset = value
        self.update()

    offset = Property(int, offset, setOffset)

    def mouseReleaseEvent(self, event) -> None:  # noqa: D401
        super().mouseReleaseEvent(event)
        self.setChecked(not self.isChecked())

    def setChecked(self, checked: bool) -> None:  # type: ignore[override]
        start = self._offset
        end = self.width() - self.height() + 2 if checked else 2
        self._anim.stop()
        self._anim.setStartValue(start)
        self._anim.setEndValue(end)
        self._anim.start()
        super().setChecked(checked)

    def paintEvent(self, event) -> None:  # noqa: D401
        radius = self.height() / 2
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#4cd964" if self.isChecked() else "#bbbbbb"))
        painter.drawRoundedRect(0, 0, self.width(), self.height(), radius, radius)
        painter.setBrush(QColor("white"))
        painter.drawEllipse(QRect(self._offset, 2, self.height() - 4, self.height() - 4))


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
    preview_path = Signal(str)

    def __init__(self, urls: list[str], parent_dir: Path, selector: str, open_folder: bool, show_preview: bool):
        super().__init__()
        self.urls = urls
        self.parent_dir = parent_dir
        self.selector = selector
        self.open_folder = open_folder
        self.show_preview = show_preview

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

            preview_sent = False
            for idx, url in enumerate(self.urls):
                info = scraper_images.download_images(
                    url,
                    css_selector=self.selector,
                    parent_dir=self.parent_dir,
                    progress_callback=make_cb(idx),
                )
                folder = info["folder"]
                if self.show_preview and not preview_sent and info.get("first_image"):
                    self.preview_path.emit(str(info["first_image"]))
                    preview_sent = True
                if self.open_folder:
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

    def new_profile(self) -> None:
        self.input_name.clear()
        self.input_images.clear()
        self.input_desc.clear()
        self.input_collection.clear()

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

        self.input_selector = QLineEdit(
            manager.settings.get(
                "scrap_lien_selector", scrap_lien_collection.DEFAULT_SELECTOR
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


        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view)

        layout.addStretch()

        self.worker: ScrapLienWorker | None = None

        for widget in [self.input_url, self.input_output, self.input_selector]:
            widget.editingFinished.connect(self.save_fields)

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

        self.save_fields()

        self.worker = ScrapLienWorker(url, output, selector, log_level)
        self.worker.log.connect(self.log_view.appendPlainText)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def on_finished(self) -> None:
        self.button_start.setEnabled(True)

    def save_fields(self) -> None:
        self.manager.save_setting("scrap_lien_url", self.input_url.text())
        self.manager.save_setting("scrap_lien_output", self.input_output.text())
        self.manager.save_setting("scrap_lien_selector", self.input_selector.text())


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
        layout.addWidget(QLabel("Fichier d'URLs"))
        layout.addLayout(file_layout)

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

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)

        self.label_preview = QLabel(alignment=Qt.AlignCenter)
        self.label_preview.setVisible(False)
        self.switch_preview.toggled.connect(self.label_preview.setVisible)
        layout.addWidget(self.label_preview)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view)
        layout.addStretch()

        self.worker: ScraperImagesWorker | None = None

        self.button_start.clicked.connect(self.start_worker)

        for widget in [
            self.input_source,
            self.input_urls_file,
            self.input_dest,
            self.input_options,
        ]:
            widget.editingFinished.connect(self.save_fields)

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

        self.save_fields()

        open_folder = self.checkbox_preview.isChecked()
        show_preview = self.switch_preview.isChecked()

        self.worker = ScraperImagesWorker(urls_list, dest, selector, open_folder, show_preview)
        self.worker.log.connect(self.log_view.appendPlainText)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.preview_path.connect(self.display_preview)
        self.worker.finished.connect(self.on_finished)
        self.label_preview.clear()
        self.label_preview.setVisible(False)
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

    def on_finished(self) -> None:
        self.button_start.setEnabled(True)

    def save_fields(self) -> None:
        self.manager.save_setting("images_url", self.input_source.text())
        self.manager.save_setting("images_file", self.input_urls_file.text())
        self.manager.save_setting("images_dest", self.input_dest.text())
        self.manager.save_setting("images_selector", self.input_options.text())

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
            manager.settings.get("desc_selector", scrap_description_produit.DEFAULT_SELECTOR)
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
        selector = self.input_selector.text().strip() or scrap_description_produit.DEFAULT_SELECTOR
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

    def save_fields(self) -> None:
        self.manager.save_setting("desc_url", self.input_url.text())
        self.manager.save_setting("desc_selector", self.input_selector.text())
        self.manager.save_setting("desc_output", self.input_output.text())


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
        self.manager.save()
        self.apply_cb()

    def update_and_restart(self) -> None:
        """Run git pull and restart the application if successful."""
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
            QMessageBox.critical(
                self,
                "Erreur lors de la mise \u00e0 jour",
                exc.output or str(exc),
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

        self.menu = QListWidget()
        self.menu.setMaximumWidth(150)
        self.menu.addItem("Profils")
        self.menu.addItem("Scrap Liens Collection")
        self.menu.addItem("Scraper Images")
        self.menu.addItem("Scrap Description")
        self.menu.addItem("G\u00e9n\u00e9rateur de lien")
        self.menu.addItem("Param\u00e8tres")

        self.stack = QStackedWidget()
        self.page_profiles = PageProfiles(self.profile_manager, self)
        self.page_scrap = PageScrapLienCollection(settings)
        self.page_images = PageScraperImages(settings)
        self.page_desc = PageScrapDescription(settings)
        self.page_linkgen = PageLinkGenerator(settings)
        self.page_settings = PageSettings(settings, self.apply_settings)
        self.stack.addWidget(self.page_profiles)
        self.stack.addWidget(self.page_scrap)
        self.stack.addWidget(self.page_images)
        self.stack.addWidget(self.page_desc)
        self.stack.addWidget(self.page_linkgen)
        self.stack.addWidget(self.page_settings)

        self.menu.currentRowChanged.connect(self.stack.setCurrentIndex)

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.addWidget(self.menu)
        layout.addWidget(self.stack)
        self.setCentralWidget(container)
        self.menu.setCurrentRow(0)

        self.apply_settings()

    def apply_settings(self) -> None:
        apply_settings(QApplication.instance(), self.settings.settings)


def main() -> None:
    app = QApplication(sys.argv)
    manager = SettingsManager()
    window = MainWindow(manager)
    window.resize(800, 600)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
