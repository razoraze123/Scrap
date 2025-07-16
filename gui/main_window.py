from __future__ import annotations

import sys
import os
import shutil
import subprocess
import time
import re
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QApplication,
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
    QGroupBox,
    QMessageBox,
    QToolBar,
    QToolButton,
    QScrollArea,
    QFrame
)
from PySide6.QtCore import Qt, QRect, QTimer, QPropertyAnimation, QEasingCurve, QSize
from PySide6.QtGui import QFont, QPixmap, QIcon, QClipboard

from settings_manager import SettingsManager, apply_settings
from site_profile_manager import SiteProfileManager
from alpha_engine import AlphaEngine

from .utils import (
    ICON_SIZE,
    load_stylesheet,
    CollapsibleSection,
    ToggleSwitch,
)
from interface_py.constants import (
    ICONS_DIR,
    SIDEBAR_EXPANDED_WIDTH,
    SIDEBAR_COLLAPSED_WIDTH,
    COLLECTION_DEFAULT_SELECTOR as SLC_DEFAULT_SELECTOR,
    DESCRIPTION_DEFAULT_SELECTOR as SDP_DEFAULT_SELECTOR,
    PRICE_DEFAULT_SELECTOR as SPP_DEFAULT_SELECTOR,
    VARIANT_DEFAULT_SELECTOR as MV_DEFAULT_SELECTOR,
    IMAGES_DEFAULT_SELECTOR as DEFAULT_CSS_SELECTOR,
    USER_AGENT,
)
from .workers import (
    ScrapLienWorker,
    ScraperImagesWorker,
    ScrapDescriptionWorker,
    ScrapPriceWorker,
    ScrapVariantWorker,
    VariantFetchWorker,
)

from interface_py.ui import (
    PageProfiles,
    PageScrapLienCollection,
    PageScraperImages,
    PageScrapDescription,
    PageScrapPrice,
    PageVariantScraper,
    PageLinkGenerator,
    PageSettings,
)



class Alpha2Widget(QWidget):
    """Scrape images then variants using a single URL."""

    def __init__(self, manager: SettingsManager) -> None:
        super().__init__()
        self.manager = manager
        self._export_rows: list[dict[str, str]] = []

        main_layout = QVBoxLayout(self)

        # --- Inputs -----------------------------------------------------
        group_inputs = QGroupBox("Entrées utilisateur")
        inputs_layout = QVBoxLayout(group_inputs)

        self.input_url = QLineEdit(manager.settings.get("alpha2_url", ""))
        self.input_url.setPlaceholderText("URL du produit")
        inputs_layout.addWidget(QLabel("URL du produit"))
        inputs_layout.addWidget(self.input_url)

        dir_layout = QHBoxLayout()
        self.input_dir = QLineEdit(manager.settings.get("alpha2_parent", "images"))
        dir_layout.addWidget(self.input_dir)
        self.button_dir = QPushButton("\U0001F4C2 Choisir dossier")
        self.button_dir.clicked.connect(self.browse_dir)
        dir_layout.addWidget(self.button_dir)
        inputs_layout.addWidget(QLabel("Dossier parent"))
        inputs_layout.addLayout(dir_layout)

        self.spin_threads = QSpinBox()
        self.spin_threads.setRange(1, 32)
        self.spin_threads.setValue(manager.settings.get("alpha2_threads", 3))
        inputs_layout.addWidget(QLabel("Threads parallèles"))
        inputs_layout.addWidget(self.spin_threads)
        inputs_layout.addStretch()

        # --- Actions ----------------------------------------------------
        group_actions = QGroupBox("Actions")
        actions_layout = QVBoxLayout(group_actions)
        self.button_start = QPushButton("Lancer le Scraping complet")
        self.button_start.clicked.connect(self.start_full_scraping)
        self.button_delete = QPushButton("Supprimer les dossiers")
        self.button_delete.clicked.connect(self.delete_folders)
        actions_layout.addWidget(self.button_start)
        actions_layout.addWidget(self.button_delete)
        actions_layout.addStretch()

        # --- State & Console -------------------------------------------
        group_state = QGroupBox("État & Console")
        state_layout = QVBoxLayout(group_state)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        state_layout.addWidget(self.progress)
        self.label_timer = QLabel("Temps restant : ...")
        state_layout.addWidget(self.label_timer)
        self.button_toggle_console = QPushButton("Masquer la console")
        self.button_toggle_console.clicked.connect(self.toggle_console)
        state_layout.addWidget(self.button_toggle_console)
        self.log_view = QPlainTextEdit(readOnly=True)
        state_layout.addWidget(self.log_view)
        state_layout.addStretch()

        # --- Export -----------------------------------------------------
        group_export = QGroupBox("Export")
        export_layout = QVBoxLayout(group_export)
        self.button_export = QPushButton("Exporter Excel")
        self.button_export.clicked.connect(self.export_excel)
        export_layout.addWidget(self.button_export)
        export_layout.addStretch()

        main_layout.addWidget(group_inputs)
        main_layout.addWidget(group_actions)
        main_layout.addWidget(group_state)
        main_layout.addWidget(group_export)
        main_layout.addStretch()

        self.images_worker: ScraperImagesWorker | None = None
        self.variant_worker: VariantFetchWorker | None = None

        for w in [self.input_url, self.input_dir]:
            w.editingFinished.connect(self.save_fields)
        self.spin_threads.valueChanged.connect(self.save_fields)

    # --- Slots ---------------------------------------------------------
    def browse_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Sélectionner un dossier")
        if directory:
            self.input_dir.setText(directory)
            self.save_fields()

    def start_full_scraping(self) -> None:
        url = self.input_url.text().strip()
        if not url:
            self.log_view.appendPlainText("Veuillez renseigner l'URL.")
            return

        dest = Path(self.input_dir.text().strip() or "images")
        selector = self.manager.settings.get(
            "images_selector",
            DEFAULT_CSS_SELECTOR,
        )

        self.button_start.setEnabled(False)
        self.progress.setValue(0)
        self.log_view.clear()

        self.save_fields()

        self.images_worker = ScraperImagesWorker(
            [url],
            dest,
            selector,
            False,
            False,
            None,
            self.spin_threads.value(),
        )
        self.images_worker.log.connect(self.log_view.appendPlainText)
        self.images_worker.progress.connect(self.update_progress)
        self.images_worker.finished.connect(self.start_variant_phase)

        self.images_done = 0
        self.total_images = 0
        self.start_time = time.perf_counter()
        self.images_worker.start()

    def start_variant_phase(self) -> None:
        url = self.input_url.text().strip()
        self.variant_worker = VariantFetchWorker(url)
        self.variant_worker.log.connect(self.log_view.appendPlainText)
        self.variant_worker.result.connect(self.process_variants)
        self.variant_worker.finished.connect(self.on_variant_finished)
        self.variant_worker.start()

    def process_variants(self, title: str, mapping: dict) -> None:
        domain = self.manager.settings.get("linkgen_base_url", "https://example.com")
        date_path = self.manager.settings.get("linkgen_date", "2025/07")
        self._export_rows = []
        self.log_view.appendPlainText(title)
        for name, img in mapping.items():
            wp_url = self._build_wp_url(domain, date_path, img)
            self.log_view.appendPlainText(f"{name} -> {wp_url}")
            self._export_rows.append({"Product": title, "Variant": name, "Image": wp_url})

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
            self.label_timer.setText(f"Temps restant : {minutes} minute(s)")
        else:
            seconds = int(remaining + 0.5)
            self.label_timer.setText(f"Temps restant : {seconds} seconde(s)")

    def toggle_console(self) -> None:
        visible = self.log_view.isVisible()
        self.log_view.setVisible(not visible)
        self.button_toggle_console.setText(
            "Afficher la console" if visible else "Masquer la console"
        )

    def on_variant_finished(self) -> None:
        self.button_start.setEnabled(True)
        self.label_timer.setText("Temps restant : 0 seconde(s)")
        QMessageBox.information(self, "Terminé", "Le scraping complet est terminé.")
        self.progress.setValue(0)

    def delete_folders(self) -> None:
        dest = Path(self.input_dir.text().strip() or "images")
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

    def export_excel(self) -> None:
        if not self._export_rows:
            QMessageBox.warning(self, "Erreur", "Aucune donnée à exporter.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer sous", "resultats.xlsx", "Excel (*.xlsx)"
        )
        if not path:
            return
        import pandas as pd

        df = pd.DataFrame(self._export_rows)
        try:
            df.to_excel(path, index=False)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Erreur", str(exc))
        else:
            QMessageBox.information(self, "Exporté", "Fichier enregistré")

    def save_fields(self) -> None:
        self.manager.save_setting("alpha2_url", self.input_url.text())
        self.manager.save_setting("alpha2_parent", self.input_dir.text())
        self.manager.save_setting("alpha2_threads", self.spin_threads.value())

    @staticmethod
    def _build_wp_url(domain: str, date_path: str, img_url: str) -> str:
        filename = img_url.split("/")[-1].split("?")[0]
        filename = re.sub(r"-\d+(?=\.\w+$)", "", filename)
        domain = domain.rstrip("/")
        date_path = date_path.strip("/")
        return f"{domain}/wp-content/uploads/{date_path}/{filename}"



class MainWindow(QMainWindow):
    def __init__(self, settings: SettingsManager):
        super().__init__()
        self.settings = settings
        self.setWindowTitle("Interface Py")

        self.profile_manager = SiteProfileManager()

        # Sidebar buttons
        labels = [
            "Profils",
            "Scrap Liens Collection",
            "Scraper Images",
            "Scrap Description",
            "Scrap Prix",
            "Générateur de lien",
            "Moteur Variante",
            "Alpha",
            "Alpha 2",
            "Paramètres",
        ]

        icon_names = [
            "profile.svg",
            "links.svg",
            "images.svg",
            "description.svg",
            "variant.svg",
            "linkgen.svg",
            "variant.svg",
            "alpha.svg",
            "alpha.svg",
            "settings.svg",
        ]
        self.icon_paths = [ICONS_DIR / name for name in icon_names]

        self.sidebar = QWidget()
        side_layout = QVBoxLayout(self.sidebar)
        side_layout.setContentsMargins(0, 0, 0, 0)

        self.side_buttons: list[QToolButton] = []
        for i, (text, icon) in enumerate(zip(labels, self.icon_paths)):
            section = CollapsibleSection(
    ToggleSwitch,
                text,
                QIcon(str(icon)),
                lambda checked=False, i=i: self.show_page(i),
            )
            side_layout.addWidget(section)
            self.side_buttons.append(section.header)
        side_layout.addStretch()

        for btn in self.side_buttons:
            btn.setIconSize(QSize(ICON_SIZE, ICON_SIZE))

        # Top bar
        self.toolbar = QToolBar()
        self.toolbar.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)

        self.toggle_sidebar_btn = QToolButton()
        self.toggle_sidebar_btn.setArrowType(Qt.LeftArrow)
        self.toggle_sidebar_btn.clicked.connect(self.toggle_sidebar)
        self.toolbar.addWidget(self.toggle_sidebar_btn)

        self.label_title = QToolButton()
        self.label_title.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.label_title.setIcon(QIcon(str(self.icon_paths[0])))
        self.label_title.setIconSize(QSize(24, 24))
        self.label_title.setText(labels[0])
        self.label_title.setEnabled(False)
        self.toolbar.addWidget(self.label_title)

        self.stack = QStackedWidget()
        self.page_profiles = PageProfiles(self.profile_manager, self)
        self.page_scrap = PageScrapLienCollection(settings)
        self.page_images = PageScraperImages(settings)
        self.page_desc = PageScrapDescription(settings)
        self.page_price = PageScrapPrice(settings)
        self.page_linkgen = PageLinkGenerator(settings)
        self.page_variants = PageVariantScraper(settings)
        self.page_alpha = AlphaEngine()
        self.page_alpha2 = Alpha2Widget(settings)
        self.page_settings = PageSettings(settings, self.apply_settings)
        self.stack.addWidget(self.page_profiles)
        self.stack.addWidget(self.page_scrap)
        self.stack.addWidget(self.page_images)
        self.stack.addWidget(self.page_desc)
        self.stack.addWidget(self.page_price)
        self.stack.addWidget(self.page_linkgen)
        self.stack.addWidget(self.page_variants)
        self.stack.addWidget(self.page_alpha)
        self.stack.addWidget(self.page_alpha2)
        self.stack.addWidget(self.page_settings)

        self.page_images.input_source.editingFinished.connect(
            lambda: self.profile_manager.detect_and_apply(
                self.page_images.input_source.text(), self
            )
        )
        self.page_scrap.input_url.editingFinished.connect(
            lambda: self.profile_manager.detect_and_apply(
                self.page_scrap.input_url.text(), self
            )
        )
        self.page_price.input_url.editingFinished.connect(
            lambda: self.profile_manager.detect_and_apply(
                self.page_price.input_url.text(), self
            )
        )

        self.stack.currentChanged.connect(self.update_title)

        # Layout central avec scroll
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        self.sidebar.setMinimumWidth(0)
        self.sidebar.setMaximumWidth(SIDEBAR_EXPANDED_WIDTH)
        self.scroll_area = QScrollArea()
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.stack)

        # Splitter to allow sidebar resizing
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.sidebar)
        self.splitter.addWidget(self.scroll_area)
        self.splitter.setStretchFactor(1, 1)
        layout.addWidget(self.splitter)
        self.setCentralWidget(container)

        self.sidebar_visible = True

        # Set initial page
        self.show_page(0)

        self.apply_settings()

    def show_page(self, index: int) -> None:
        """Display page at given index."""
        self.stack.setCurrentIndex(index)
        if 0 <= index < len(self.side_buttons):
            for i, btn in enumerate(self.side_buttons):
                btn.setChecked(i == index)
        self.update_title(index)

    def update_title(self, index: int) -> None:
        """Update title label when page changes."""
        if 0 <= index < len(self.side_buttons):
            self.label_title.setText(self.side_buttons[index].text())
            self.label_title.setIcon(QIcon(str(self.icon_paths[index])))

    def toggle_sidebar(self) -> None:
        start = self.sidebar.width()
        end = (
            SIDEBAR_COLLAPSED_WIDTH if self.sidebar_visible else SIDEBAR_EXPANDED_WIDTH
        )

        if not self.sidebar_visible:
            self.sidebar.setVisible(True)

        self._anim = QPropertyAnimation(self.sidebar, b"maximumWidth", self)
        self._anim.setDuration(200)
        self._anim.setStartValue(start)
        self._anim.setEndValue(end)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)
        self._anim.finished.connect(self._on_sidebar_toggled)
        self._anim.start()

    def _on_sidebar_toggled(self) -> None:
        self.sidebar_visible = not self.sidebar_visible

        if not self.sidebar_visible:
            for btn in self.side_buttons:
                btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
            self.sidebar.setMaximumWidth(SIDEBAR_COLLAPSED_WIDTH)
        else:
            for btn in self.side_buttons:
                btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            self.sidebar.setMaximumWidth(SIDEBAR_EXPANDED_WIDTH)

        arrow = Qt.LeftArrow if self.sidebar_visible else Qt.RightArrow
        self.toggle_sidebar_btn.setArrowType(arrow)

    def apply_settings(self) -> None:
        apply_settings(QApplication.instance(), self.settings.settings)


def main() -> None:
    app = QApplication(sys.argv)
    manager = SettingsManager()
    load_stylesheet()
    window = MainWindow(manager)
    window.resize(800, 600)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
