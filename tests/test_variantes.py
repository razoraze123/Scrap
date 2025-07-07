from pathlib import Path
import importlib.util as util

spec = util.spec_from_file_location("moteur_variante", Path(__file__).resolve().parents[1] / "moteur_variante.py")
mv = util.module_from_spec(spec)
spec.loader.exec_module(mv)

class DummyElem:
    def __init__(self, text="v1"):
        self.text = text

class DummyDriver:
    def __init__(self):
        self.closed = False
    def get(self, url):
        self.url = url
    def find_element(self, by, value):
        return DummyElem("Title")
    def find_elements(self, by, value):
        return [DummyElem("Red"), DummyElem("Blue")]
    def quit(self):
        self.closed = True

class DummyWait:
    def __init__(self, driver, timeout):
        pass
    def until(self, cond):
        return True

class DummyEC:
    @staticmethod
    def presence_of_element_located(locator):
        return lambda d: True


def test_extract_variants(monkeypatch):
    monkeypatch.setattr(mv, "WebDriverWait", DummyWait)
    monkeypatch.setattr(mv, "EC", DummyEC)
    monkeypatch.setattr("driver_utils.setup_driver", lambda: DummyDriver())
    monkeypatch.setattr(mv, "setup_driver", lambda: DummyDriver())

    title, variants = mv.extract_variants("https://example.com")
    assert title == "Title"
    assert variants == ["Red", "Blue"]

    tmp = Path("tmp_variants.txt")
    mv.save_to_file(title, variants, tmp)
    assert tmp.read_text(encoding="utf-8").strip() == "Title\tRed, Blue"
    tmp.unlink()
