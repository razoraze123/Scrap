from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QMessageBox

from settings_manager import SettingsManager
from gui.workers import ScrapDescriptionWorker
from interface_py.constants import DESCRIPTION_DEFAULT_SELECTOR as SDP_DEFAULT_SELECTOR

from .base_page import PageWithConsole


class PageScrapDescription(PageWithConsole):
    def __init__(self, manager: SettingsManager) -> None:
        super().__init__()
        self.manager = manager
        layout = self.body_layout

        self.input_url = QLineEdit(manager.settings.get("desc_url", ""))
        self.input_url.setPlaceholderText("URL du produit")
        layout.addWidget(QLabel("URL du produit"))
        layout.addWidget(self.input_url)

        self.input_selector = QLineEdit(
            manager.settings.get("desc_selector", SDP_DEFAULT_SELECTOR)
        )
        label_selector = QLabel("Sélecteur CSS")
        self.input_selector.hide()
        label_selector.hide()

        self.input_output = QLineEdit(manager.settings.get("desc_output", "description.html"))
        layout.addWidget(QLabel("Fichier de sortie"))
        layout.addWidget(self.input_output)

        self.button_start = QPushButton("Extraire")
        layout.addWidget(self.button_start)

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

    def save_fields(self) -> None:
        self.manager.save_setting("desc_url", self.input_url.text())
        self.manager.save_setting("desc_selector", self.input_selector.text())
        self.manager.save_setting("desc_output", self.input_output.text())
