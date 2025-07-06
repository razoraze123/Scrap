from importlib import util
from pathlib import Path

spec = util.spec_from_file_location(
    "scraper_images",
    Path(__file__).resolve().parents[1] / "scraper_images.py",
)
si = util.module_from_spec(spec)
spec.loader.exec_module(si)


class ElementBase64:
    def get_attribute(self, name):
        if name == "src":
            return "data:image/png;base64,aGVsbG8="
        return None


class ElementURL:
    def get_attribute(self, name):
        if name == "src":
            return "https://example.com/img/test.png?x=1"
        return None


def test_handle_image_base64(tmp_path):
    elem = ElementBase64()
    path = si._handle_image(elem, tmp_path, 1, "UA")
    assert path.exists()
    assert path.read_bytes() == b"hello"


def test_handle_image_url(tmp_path, monkeypatch):
    elem = ElementURL()

    def fake_download(url, dest, ua):
        dest.write_bytes(b"data")

    monkeypatch.setattr(si, "_download_binary", fake_download)
    path = si._handle_image(elem, tmp_path, 1, "UA")
    assert path.exists()
    assert path.name == "test.png"


class ElementDataSrc:
    def get_attribute(self, name):
        if name == "data-src":
            return "https://example.com/img/ds.png"
        return None


class DummyDriver:
    def __init__(self, elems):
        self.elems = elems

    def get(self, url):
        self.url = url

    def find_elements(self, by, selector):
        return self.elems

    def quit(self):
        self.closed = True


class DummyWait:
    def __init__(self, driver, timeout):
        self.driver = driver

    def until(self, condition):
        return condition(self.driver)


class DummyEC:
    @staticmethod
    def presence_of_element_located(locator):
        return lambda d: True


def test_download_images_datasrc_progress(tmp_path, monkeypatch):
    elem = ElementDataSrc()
    driver = DummyDriver([elem])

    monkeypatch.setattr(si, "WebDriverWait", DummyWait)
    monkeypatch.setattr(si, "EC", DummyEC)
    monkeypatch.setattr("driver_utils.setup_driver", lambda: driver)
    monkeypatch.setattr(si, "setup_driver", lambda: driver)
    monkeypatch.setattr(si, "_find_product_name", lambda d: "prod")

    def fake_download(url, dest, ua):
        dest.write_bytes(b"img")

    monkeypatch.setattr(si, "_download_binary", fake_download)

    calls = []

    si.download_images(
        "http://example.com",
        css_selector="img",
        parent_dir=tmp_path,
        progress_callback=lambda i, t: calls.append((i, t)),
        use_alt_json=False,
    )

    assert calls == [(1, 1)]
