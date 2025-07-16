from __future__ import annotations

import logging
from pathlib import Path

from interface_py.constants import (
    ICONS_DIR,
    SIDEBAR_EXPANDED_WIDTH,
    SIDEBAR_COLLAPSED_WIDTH,
)

try:
    from PySide6.QtWidgets import (
        QApplication,
        QWidget,
        QToolButton,
        QVBoxLayout,
        QCheckBox,
    )
    from PySide6.QtCore import Qt, QRect, QSize
    from PySide6.QtGui import QPainter, QColor, QIcon
except Exception:  # pragma: no cover - fallback for tests
    QApplication = type('QApplication', (), {'instance': staticmethod(lambda: None)})
    QWidget = QToolButton = QVBoxLayout = QCheckBox = object  # type: ignore

    class Qt:
        NoPen = 0
        PointingHandCursor = 0

    class QRect:  # type: ignore
        def __init__(self, *a, **kw) -> None:
            pass

    class QSize:  # type: ignore
        def __init__(self, *a, **kw) -> None:
            pass

    class QPainter:  # type: ignore
        def __init__(self, *a, **kw) -> None:
            pass

        def setRenderHint(self, *a, **kw) -> None:
            pass

        def setPen(self, *a, **kw) -> None:
            pass

        def setBrush(self, *a, **kw) -> None:
            pass

        def drawRoundedRect(self, *a, **kw) -> None:
            pass

        def drawEllipse(self, *a, **kw) -> None:
            pass

    class QColor:  # type: ignore
        def __init__(self, *a, **kw) -> None:
            pass

    class QIcon:  # type: ignore
        def __init__(self, *a, **kw) -> None:
            pass


# Sidebar sizing constants
ICON_SIZE = 24


def load_stylesheet(path: str = "style.qss") -> None:
    """Apply the application's stylesheet if available."""
    app = QApplication.instance()
    if app is None:
        return
    qss_path = Path(path)
    if qss_path.exists():
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))


class QtLogHandler(logging.Handler):
    """Forward logging records to a Qt signal."""

    def __init__(self, signal):
        super().__init__()
        self._signal = signal

    def emit(self, record):
        msg = self.format(record)
        self._signal.emit(msg)


class ToggleSwitch(QCheckBox):
    """Simple ON/OFF switch widget."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._offset = 2
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(40, 20)
        QCheckBox.setChecked(self, False)
        self.setStyleSheet("QCheckBox::indicator { width:0; height:0; }")

    def mouseReleaseEvent(self, event) -> None:  # noqa: D401
        super().mouseReleaseEvent(event)
        self.setChecked(not self.isChecked())

    def setChecked(self, checked: bool) -> None:  # type: ignore[override]
        self._offset = self.width() - self.height() + 2 if checked else 2
        super().setChecked(checked)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: D401
        radius = self.height() / 2
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#4cd964" if self.isChecked() else "#bbbbbb"))
        painter.drawRoundedRect(0, 0, self.width(), self.height(), radius, radius)
        painter.setBrush(QColor("white"))
        painter.drawEllipse(QRect(self._offset, 2, self.height() - 4, self.height() - 4))


class CollapsibleSection(QWidget):
    """Simple collapsible section used for the sidebar."""

    def __init__(self, title: str, icon: QIcon, callback) -> None:
        super().__init__()
        self._title = title
        self._callback = callback
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.header = QToolButton()
        self.header.setText(self._title)
        self.header.setIcon(icon)
        self.header.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.header.setCheckable(True)
        self.header.clicked.connect(callback)
        layout.addWidget(self.header)

