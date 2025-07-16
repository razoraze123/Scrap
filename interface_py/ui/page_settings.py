from __future__ import annotations

import os
import subprocess
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QSpinBox,
    QFontComboBox,
    QCheckBox,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)

from settings_manager import SettingsManager
from interface_py.constants import USER_AGENT


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
        layout.addWidget(QLabel("Thème global"))
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

        self.checkbox_update = QCheckBox("Autoriser la mise à jour (git pull)")
        self.checkbox_update.setChecked(manager.settings.get("enable_update", True))
        layout.addWidget(self.checkbox_update)

        self.checkbox_headless = QCheckBox("Exécuter Selenium en mode headless")
        self.checkbox_headless.setChecked(manager.settings.get("headless", True))
        layout.addWidget(self.checkbox_headless)

        self.input_driver_path = QLineEdit(manager.settings.get("driver_path", ""))
        layout.addWidget(QLabel("Chemin ChromeDriver"))
        layout.addWidget(self.input_driver_path)

        self.input_user_agent = QLineEdit(
            manager.settings.get("user_agent", USER_AGENT)
        )
        layout.addWidget(QLabel("User-Agent"))
        layout.addWidget(self.input_user_agent)

        self.button_reset = QPushButton("Réinitialiser les paramètres")
        layout.addWidget(self.button_reset)

        self.button_update = QPushButton("🔄 Mettre à jour l'app (Git Pull)")
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
            self.checkbox_update,
            self.checkbox_headless,
            self.input_driver_path,
            self.input_user_agent,
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
        s["enable_update"] = self.checkbox_update.isChecked()
        s["headless"] = self.checkbox_headless.isChecked()
        s["driver_path"] = self.input_driver_path.text().strip()
        s["user_agent"] = self.input_user_agent.text().strip() or USER_AGENT
        self.manager.save_setting("headless", s["headless"])
        self.manager.save_setting("user_agent", s["user_agent"])
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
        self.checkbox_update.setChecked(self.manager.settings.get("enable_update", True))
        self.checkbox_headless.setChecked(self.manager.settings.get("headless", True))
        self.input_driver_path.setText(self.manager.settings.get("driver_path", ""))
        self.input_user_agent.setText(
            self.manager.settings.get("user_agent", USER_AGENT)
        )
        self.manager.save()
        self.apply_cb()

    def update_and_restart(self) -> None:
        """Run git pull after confirmation and restart the app if successful."""
        if not self.manager.settings.get("enable_update", True):
            QMessageBox.information(
                self,
                "Mise à jour désactivée",
                "La mise à jour par git pull est désactivée dans les paramètres.",
            )
            return

        reply = QMessageBox.question(
            self,
            "Confirmer la mise à jour",
            "Exécuter 'git pull' puis redémarrer l'application ?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

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
                "Git n'est pas installé ou introuvable.",
            )
            return
        except subprocess.CalledProcessError as exc:
            msg = exc.output or str(exc)
            low = msg.lower()
            if "unable to access" in low or "could not resolve host" in low:
                msg = f"Erreur réseau lors de la mise à jour :\n{msg}"
            QMessageBox.critical(
                self,
                "Erreur lors de la mise à jour",
                msg,
            )
            return

        QMessageBox.information(self, "Mise à jour", output)
        QTimer.singleShot(1000, lambda: os.execv(sys.executable, [sys.executable] + sys.argv))
