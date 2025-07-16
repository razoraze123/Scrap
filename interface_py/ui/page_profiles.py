from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from site_profile_manager import SiteProfileManager


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

        alt_json_layout = QHBoxLayout()
        self.input_alt_json = QLineEdit()
        alt_json_layout.addWidget(self.input_alt_json)
        self.button_alt_json = QPushButton("\U0001F4C1 Choisir un fichier json")
        self.button_alt_json.clicked.connect(self.browse_alt_json)
        alt_json_layout.addWidget(self.button_alt_json)
        layout.addWidget(QLabel("Fichier ALT JSON"))
        layout.addLayout(alt_json_layout)

        file_urls_layout = QHBoxLayout()
        self.input_urls_images = QLineEdit()
        file_urls_layout.addWidget(self.input_urls_images)
        self.button_urls_images = QPushButton("\U0001F4C1 Choisir un fichier txt")
        self.button_urls_images.clicked.connect(self.browse_urls_images)
        file_urls_layout.addWidget(self.button_urls_images)
        layout.addWidget(QLabel("Fichier URLs Images"))
        layout.addLayout(file_urls_layout)

        urls_desc_layout = QHBoxLayout()
        self.input_urls_desc = QLineEdit()
        urls_desc_layout.addWidget(self.input_urls_desc)
        self.button_urls_desc = QPushButton("\U0001F4C1 Choisir un fichier txt")
        self.button_urls_desc.clicked.connect(self.browse_urls_desc)
        urls_desc_layout.addWidget(self.button_urls_desc)
        layout.addWidget(QLabel("Fichier URLs Description"))
        layout.addLayout(urls_desc_layout)

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
        self.input_alt_json.setText(data.get("sentences_file", ""))
        self.input_urls_images.setText(data.get("urls_file", ""))
        self.input_urls_desc.setText(data.get("desc_urls_file", ""))

    def new_profile(self) -> None:
        self.input_name.clear()
        self.input_images.clear()
        self.input_desc.clear()
        self.input_collection.clear()
        self.input_alt_json.clear()
        self.input_urls_images.clear()
        self.input_urls_desc.clear()

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
            "sentences_file": self.input_alt_json.text().strip(),
            "urls_file": self.input_urls_images.text().strip(),
            "desc_urls_file": self.input_urls_desc.text().strip(),
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

    def browse_urls_images(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Sélectionner un fichier", "", "Text Files (*.txt)"
        )
        if file_path:
            self.input_urls_images.setText(file_path)

    def browse_urls_desc(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Sélectionner un fichier", "", "Text Files (*.txt)"
        )
        if file_path:
            self.input_urls_desc.setText(file_path)

    def browse_alt_json(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Sélectionner un fichier", "", "JSON Files (*.json);;All Files (*)"
        )
        if file_path:
            self.input_alt_json.setText(file_path)
