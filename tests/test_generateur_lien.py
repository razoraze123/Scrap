import sys
import types
from importlib import util
from pathlib import Path


class DummyClipboard:
    def __init__(self):
        self.data = ""

    def setText(self, text):
        self.data = text

    def text(self):
        return self.data


class DummySignal:
    def connect(self, cb):
        self.cb = cb


class DummyButton:
    def __init__(self, text=""):
        self._text = text
        self.clicked = DummySignal()

    def setText(self, text):
        self._text = text

    def text(self):
        return self._text


class DummyLineEdit:
    def __init__(self, text=""):
        self._text = text

    def text(self):
        return self._text

    def setText(self, val):
        self._text = val


class DummyTextEdit:
    def __init__(self):
        self._text = ""

    def setPlaceholderText(self, text):
        pass

    def setText(self, text):
        self._text = text

    def toPlainText(self):
        return self._text


class DummyLayout:
    def addWidget(self, widget):
        pass

    def addLayout(self, layout):
        pass


class DummyMessageBox:
    @staticmethod
    def warning(*a, **k):
        pass

    @staticmethod
    def information(*a, **k):
        pass


class DummyFileDialog:
    @staticmethod
    def getExistingDirectory(*a, **k):
        return ""

    @staticmethod
    def getSaveFileName(*a, **k):
        return "", ""


class DummyApp:
    _clipboard = DummyClipboard()

    def __init__(self, *a, **k):
        pass

    @staticmethod
    def clipboard():
        return DummyApp._clipboard


class DummyWidget:
    def __init__(self, *a, **k):
        pass

    def setWindowTitle(self, title):
        self.title = title

    def setLayout(self, layout):
        pass


def setup_pyside(monkeypatch):
    qtwidgets = types.ModuleType("PySide6.QtWidgets")
    qtwidgets.QApplication = DummyApp
    qtwidgets.QWidget = DummyWidget
    qtwidgets.QPushButton = DummyButton
    qtwidgets.QLabel = type("QLabel", (), {"__init__": lambda self, t="": None})
    qtwidgets.QVBoxLayout = DummyLayout
    qtwidgets.QFileDialog = DummyFileDialog
    qtwidgets.QLineEdit = DummyLineEdit
    qtwidgets.QTextEdit = DummyTextEdit
    qtwidgets.QMessageBox = DummyMessageBox
    qtwidgets.QHBoxLayout = DummyLayout

    qtgui = types.ModuleType("PySide6.QtGui")
    qtgui.QClipboard = DummyClipboard

    pyside = types.ModuleType("PySide6")
    pyside.QtWidgets = qtwidgets
    pyside.QtGui = qtgui

    monkeypatch.setitem(sys.modules, "PySide6", pyside)
    monkeypatch.setitem(sys.modules, "PySide6.QtWidgets", qtwidgets)
    monkeypatch.setitem(sys.modules, "PySide6.QtGui", qtgui)

    return qtwidgets, qtgui


def load_module(monkeypatch):
    setup_pyside(monkeypatch)
    import importlib

    return importlib.import_module("interface_py.link_generator")


def test_generate_links(tmp_path, monkeypatch):
    gl = load_module(monkeypatch)
    gen = gl.WooImageURLGenerator()
    gen.folder_path = str(tmp_path)
    (tmp_path / "a.jpg").write_text("data")
    (tmp_path / "b.PNG").write_text("data")
    (tmp_path / "c.txt").write_text("data")

    gen.input_base_url.setText("https://example.com")
    gen.input_date.setText("2024/01")
    gen.generate_links()

    links = gen.output_links.toPlainText().splitlines()
    expected = {
        "https://example.com/wp-content/uploads/2024/01/a.jpg",
        "https://example.com/wp-content/uploads/2024/01/b.PNG",
    }
    assert set(links) == expected


def test_copy_to_clipboard(monkeypatch):
    gl = load_module(monkeypatch)
    gen = gl.WooImageURLGenerator()
    gen.output_links.setText("one\ntwo")
    clip = gl.QApplication.clipboard()
    gen.copy_to_clipboard()
    assert clip.data == "one\ntwo"


def test_export_to_txt(tmp_path, monkeypatch):
    gl = load_module(monkeypatch)
    gen = gl.WooImageURLGenerator()
    gen.output_links.setText("x\ny")
    dest = tmp_path / "out.txt"
    monkeypatch.setattr(gl.QFileDialog, "getSaveFileName", lambda *a, **k: (str(dest), "txt"))
    gen.export_to_txt()
    assert dest.read_text(encoding="utf-8") == "x\ny"
