from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QMessageBox,
    QFileDialog,
)
from PySide6.QtCore import Qt

import pandas as pd


class AlphaEngine(QWidget):
    """Combined engine to fetch variants and generate WordPress links."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)

        self.input_url = QLineEdit()
        self.input_url.setPlaceholderText("URL du produit")
        layout.addWidget(QLabel("URL du produit"))
        layout.addWidget(self.input_url)

        self.input_domain = QLineEdit("https://planetebob.fr")
        layout.addWidget(QLabel("Domaine WP"))
        layout.addWidget(self.input_domain)

        self.input_date = QLineEdit("2025/07")
        layout.addWidget(QLabel("Date du chemin WP"))
        layout.addWidget(self.input_date)

        self.button_start = QPushButton("Lancer l'analyse")
        self.button_start.clicked.connect(self.start_analysis)
        layout.addWidget(self.button_start)

        self.result_view = QTextEdit(readOnly=True)
        layout.addWidget(self.result_view)

        export_layout = QHBoxLayout()
        self.button_excel = QPushButton("Exporter Excel")
        self.button_excel.clicked.connect(self.export_excel)
        export_layout.addWidget(self.button_excel)

        self.button_csv = QPushButton("Exporter CSV")
        self.button_csv.clicked.connect(self.export_csv)
        export_layout.addWidget(self.button_csv)
        layout.addLayout(export_layout)

    # --- Slots -------------------------------------------------------------
    def start_analysis(self) -> None:
        """Placeholder method for the scraping logic."""
        # TODO: insert scraping logic here
        self.result_view.append("Analyse en cours ...")

    def export_excel(self) -> None:
        """Export the current results to an Excel file."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer sous", "resultats.xlsx", "Excel (*.xlsx)"
        )
        if not path:
            return
        df = pd.DataFrame({"data": [self.result_view.toPlainText()]})
        try:
            df.to_excel(path, index=False)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Erreur", str(exc))
        else:
            QMessageBox.information(self, "Exporté", "Fichier enregistré")

    def export_csv(self) -> None:
        """Export the current results to a CSV file."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer sous", "resultats.csv", "CSV (*.csv)"
        )
        if not path:
            return
        df = pd.DataFrame({"data": [self.result_view.toPlainText()]})
        try:
            df.to_csv(path, index=False)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Erreur", str(exc))
        else:
            QMessageBox.information(self, "Exporté", "Fichier enregistré")


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication, QTabWidget
    import sys

    app = QApplication(sys.argv)
    tabs = QTabWidget()
    tabs.addTab(AlphaEngine(), "Alpha")
    tabs.resize(600, 400)
    tabs.show()
    sys.exit(app.exec())
