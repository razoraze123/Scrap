from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QPushButton,
    QHBoxLayout,
    QFileDialog,
    QMessageBox,
)

from settings_manager import SettingsManager
from gui.workers import ScrapVariantWorker
from interface_py.constants import VARIANT_DEFAULT_SELECTOR as MV_DEFAULT_SELECTOR

from .base_page import PageWithConsole


class PageVariantScraper(PageWithConsole):
    def __init__(self, manager: SettingsManager) -> None:
        super().__init__()
        self.manager = manager
        layout = self.body_layout

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

    def save_fields(self) -> None:
        self.manager.save_setting("variant_url", self.input_url.text())
        self.manager.save_setting("variant_selector", self.input_selector.text())
        self.manager.save_setting("variant_output", self.input_output.text())
