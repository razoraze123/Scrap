from __future__ import annotations

import logging
import re

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


from gui.workers import VariantFetchWorker

from interface_py import moteur_variante


class AlphaEngine(QWidget):
    """Combined engine to fetch variants and generate WordPress links."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        self._export_rows: list[dict[str, str]] = []

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

    @staticmethod
    def _build_wp_url(domain: str, date_path: str, img_url: str) -> str:
        """Return WordPress URL for *img_url* using domain and date."""
        filename = img_url.split("/")[-1].split("?")[0]
        filename = re.sub(r"-\d+(?=\.\w+$)", "", filename)
        domain = domain.rstrip("/")
        date_path = date_path.strip("/")
        return f"{domain}/wp-content/uploads/{date_path}/{filename}"

    # --- Slots -------------------------------------------------------------
    def start_analysis(self) -> None:
        """Fetch variants asynchronously using a worker thread."""
        url = self.input_url.text().strip()
        if not url:
            QMessageBox.warning(self, "Erreur", "Aucune URL fournie")
            return

        self.button_start.setEnabled(False)
        self.result_view.clear()
        self.result_view.append("Analyse en cours...")

        self._worker = VariantFetchWorker(url)
        self._worker.result.connect(self._display_result)
        self._worker.log.connect(self._handle_log)
        self._worker.finished.connect(self._analysis_finished)
        self._worker.start()

    def _display_result(self, title: str, variants: dict) -> None:
        domain = self.input_domain.text().strip()
        date_path = self.input_date.text().strip()

        self.result_view.clear()
        self._export_rows = []
        self.result_view.append(title)
        for name, img in variants.items():
            wp_url = self._build_wp_url(domain, date_path, img)
            self.result_view.append(f"{name} -> {wp_url}")
            self._export_rows.append(
                {"Product": title, "Variant": name, "Image": wp_url}
            )

    def _handle_log(self, msg: str) -> None:
        if msg.startswith("ERROR:"):
            self._show_error(msg.split(":", 1)[1].strip())

    def _show_error(self, msg: str) -> None:
        QMessageBox.critical(self, "Erreur", msg)

    def _analysis_finished(self) -> None:
        self.result_view.append("Analyse terminée.")
        self.button_start.setEnabled(True)

    def export_excel(self) -> None:
        """Export the current results to an Excel file."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer sous", "resultats.xlsx", "Excel (*.xlsx)"
        )
        if not path:
            return
        import pandas as pd  # Imported lazily to avoid mandatory dependency

        df = pd.DataFrame(self._export_rows)
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
        import pandas as pd  # Imported lazily to avoid mandatory dependency

        df = pd.DataFrame(self._export_rows)
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
