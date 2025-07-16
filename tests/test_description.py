import importlib

sdp = importlib.import_module("interface_py.scrap_description")


class DummyElement:
    def get_attribute(self, name):
        return "  <p>desc</p>  " if name == "innerHTML" else None


class DummyDriver:
    def get(self, url):
        self.url = url

    def find_element(self, by, value):
        return DummyElement()

    def quit(self):
        self.closed = True


class DummyWait:
    def __init__(self, driver, timeout):
        pass

    def until(self, condition):
        return True


class DummyEC:
    @staticmethod
    def presence_of_element_located(locator):
        return lambda d: True


def test_extract_html_description(monkeypatch):
    monkeypatch.setattr(sdp, "WebDriverWait", DummyWait)
    monkeypatch.setattr(sdp, "EC", DummyEC)
    monkeypatch.setattr("interface_py.driver_utils.setup_driver", lambda: DummyDriver())
    monkeypatch.setattr(sdp, "setup_driver", lambda: DummyDriver())

    html = sdp.extract_html_description("https://example.com", "div")
    assert html == "<p>desc</p>"


def test_save_html_to_file_creates_parent(tmp_path):
    dest = tmp_path / "sub" / "desc.html"
    sdp.save_html_to_file("<p>test</p>", dest)
    assert dest.exists()
    assert dest.read_text(encoding="utf-8") == "<p>test</p>"
