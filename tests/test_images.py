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
