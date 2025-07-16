from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QMessageBox,
    QWidget,
    QVBoxLayout,
)
from PySide6.QtGui import QClipboard

from settings_manager import SettingsManager


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
        self.output_links.setPlaceholderText("Les URLs générées s'afficheront ici.")
        layout.addWidget(self.output_links)

        actions = QHBoxLayout()
        self.button_generate = QPushButton("Générer")
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
        folder = QFileDialog.getExistingDirectory(self, "Sélectionner un dossier")
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
                if fname.lower().endswith((".webp", ".jpg", ".jpeg", ".png")):
                    file_url = f"{base_url}/wp-content/uploads/{date_path}/{fname}"
                    links.append(file_url)

        if links:
            self.output_links.setText("\n".join(links))
        else:
            self.output_links.setText("Aucune image valide trouvée dans le dossier.")
        QMessageBox.information(self, "Terminé", "La génération des liens est terminée.")

    def copy_to_clipboard(self) -> None:
        clipboard: QClipboard = QApplication.clipboard()
        clipboard.setText(self.output_links.toPlainText())
        QMessageBox.information(self, "Copié", "Les liens ont été copiés dans le presse-papiers.")

    def export_to_txt(self) -> None:
        if not self.output_links.toPlainText():
            QMessageBox.warning(self, "Erreur", "Aucun lien à exporter.")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Enregistrer sous", "liens_images.txt", "Fichier texte (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.output_links.toPlainText())
            QMessageBox.information(self, "Exporté", "Les liens ont été enregistrés avec succès.")

    def save_fields(self) -> None:
        self.manager.save_setting("linkgen_base_url", self.input_base_url.text())
        self.manager.save_setting("linkgen_date", self.input_date.text())
        self.manager.save_setting("linkgen_folder", self.folder_path)
