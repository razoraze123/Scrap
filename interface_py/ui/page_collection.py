from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QComboBox, QLabel, QLineEdit, QPushButton, QMessageBox

from settings_manager import SettingsManager
from gui.workers import ScrapLienWorker
from interface_py.constants import COLLECTION_DEFAULT_SELECTOR as SLC_DEFAULT_SELECTOR

from .base_page import PageWithConsole


class PageScrapLienCollection(PageWithConsole):
    def __init__(self, manager: SettingsManager) -> None:
        super().__init__()
        self.manager = manager
        layout = self.body_layout

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
            manager.settings.get("scrap_lien_selector", SLC_DEFAULT_SELECTOR)
        )
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

    def save_fields(self) -> None:
        self.manager.save_setting("scrap_lien_url", self.input_url.text())
        self.manager.save_setting("scrap_lien_output", self.input_output.text())
        self.manager.save_setting("scrap_lien_selector", self.input_selector.text())
        self.manager.save_setting("scrap_lien_format", self.combo_format.currentText())
