import sys
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QLabel,
    QPlainTextEdit,
    QLineEdit,
    QPushButton,
)

from find_css_selector import find_best_css_selector


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CSS Selector Tester")

        container = QWidget()
        layout = QVBoxLayout(container)
        self.setCentralWidget(container)

        layout.addWidget(QLabel("HTML input"))
        self.input_html = QPlainTextEdit()
        self.input_html.setPlaceholderText("Paste HTML snippet here...")
        layout.addWidget(self.input_html)

        self.button = QPushButton("Find selector")
        layout.addWidget(self.button)

        layout.addWidget(QLabel("Best selector"))
        self.output = QLineEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output)

        self.status = QLabel()
        layout.addWidget(self.status)

        self.button.clicked.connect(self.on_click)

    def on_click(self) -> None:
        html = self.input_html.toPlainText().strip()
        if not html:
            self.status.setText("Please provide HTML")
            self.output.clear()
            return
        try:
            selector = find_best_css_selector(html)
        except Exception as exc:  # noqa: BLE001
            self.status.setText(str(exc))
            self.output.clear()
        else:
            self.output.setText(selector)
            self.status.setText("")


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(600, 400)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
