from __future__ import annotations

import shutil
import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QProgressBar,
)

from settings_manager import SettingsManager
from gui.workers import ScraperImagesWorker
from interface_py.constants import IMAGES_DEFAULT_SELECTOR as DEFAULT_CSS_SELECTOR

from .base_page import PageWithConsole
from .widgets import ToggleSwitch


class PageScraperImages(PageWithConsole):
    def __init__(self, manager: SettingsManager) -> None:
        super().__init__()
        self.manager = manager
        layout = self.body_layout

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
        label_options = QLabel("Sélecteur CSS")
        self.input_options.hide()
        label_options.hide()

        self.input_alt_json = QLineEdit(
            manager.settings.get("images_alt_json", "product_sentences.json")
        )
        label_alt_json = QLabel("Fichier ALT JSON")
        self.input_alt_json.hide()
        label_alt_json.hide()

        self.spin_threads = QSpinBox()
        self.spin_threads.setRange(1, 32)
        self.spin_threads.setValue(manager.settings.get("images_max_threads", 4))
        layout.addWidget(QLabel("Threads parallèles"))
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

        self.main_layout.addStretch()

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
