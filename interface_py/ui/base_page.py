from __future__ import annotations

from PySide6.QtWidgets import QWidget, QVBoxLayout, QPlainTextEdit, QPushButton


class PageWithConsole(QWidget):
    """Base page widget providing a log console with a toggle button."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.main_layout = QVBoxLayout(self)
        self.body_layout = QVBoxLayout()
        self.main_layout.addLayout(self.body_layout)

        self.button_toggle_console = QPushButton("Masquer la console")
        self.button_toggle_console.clicked.connect(self.toggle_console)
        self.main_layout.addWidget(self.button_toggle_console)

        self.log_view = QPlainTextEdit(readOnly=True)
        self.main_layout.addWidget(self.log_view)

    def toggle_console(self) -> None:
        visible = self.log_view.isVisible()
        self.log_view.setVisible(not visible)
        self.button_toggle_console.setText(
            "Afficher la console" if visible else "Masquer la console"
        )
