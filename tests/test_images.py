import importlib
from pathlib import Path
import threading

si = importlib.import_module("interface_py.scraper_images")


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
    path, url = si._handle_image(elem, tmp_path, 1, "UA", set())
    assert path.exists()
    assert url is None
    assert path.read_bytes() == b"hello"


def test_handle_image_url(tmp_path):
    elem = ElementURL()
    path, url = si._handle_image(elem, tmp_path, 1, "UA", set())
    assert not path.exists()
    assert url == "https://example.com/img/test.png?x=1"
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
    monkeypatch.setattr("interface_py.driver_utils.setup_driver", lambda: driver)
    monkeypatch.setattr(si, "setup_driver", lambda: driver)
    monkeypatch.setattr(si, "_find_product_name", lambda d: "prod")

    def fake_download(url, dest, ua):
        dest.write_bytes(b"img")

    monkeypatch.setattr(si, "_download_binary", fake_download)

    calls = []

    res = si.download_images(
        "http://example.com",
        css_selector="img",
        parent_dir=tmp_path,
        progress_callback=lambda i, t: calls.append((i, t)),
        use_alt_json=False,
    )

    assert calls == [(1, 1)]
    files = list(res["folder"].iterdir())
    assert len(files) == 1


def test_download_images_parallel(tmp_path, monkeypatch):
    elems = [ElementDataSrc(), ElementDataSrc()]
    driver = DummyDriver(elems)

    monkeypatch.setattr(si, "WebDriverWait", DummyWait)
    monkeypatch.setattr(si, "EC", DummyEC)
    monkeypatch.setattr("interface_py.driver_utils.setup_driver", lambda: driver)
    monkeypatch.setattr(si, "setup_driver", lambda: driver)
    monkeypatch.setattr(si, "_find_product_name", lambda d: "prod")

    def fake_download(url, dest, ua):
        dest.write_bytes(b"img")

    monkeypatch.setattr(si, "_download_binary", fake_download)

    calls = []

    res = si.download_images(
        "http://example.com",
        css_selector="img",
        parent_dir=tmp_path,
        progress_callback=lambda i, t: calls.append((i, t)),
        use_alt_json=False,
        max_threads=2,
    )

    assert sorted(calls) == [(1, 2), (2, 2)]
    assert len(list(res["folder"].iterdir())) == 2


def test_load_alt_sentences_cache(tmp_path, monkeypatch):
    path = tmp_path / "sentences.json"
    path.write_text("{}", encoding="utf-8")

    calls = []

    def fake_load(fh):
        calls.append(1)
        return {}

    monkeypatch.setattr(si.json, "load", fake_load)
    si._ALT_SENTENCES_CACHE.clear()

    si._load_alt_sentences(path)
    si._load_alt_sentences(path)

    assert calls == [1]


def test_download_images_no_alt_when_empty_path(tmp_path, monkeypatch):
    elem = ElementDataSrc()

    driver = DummyDriver([elem])

    monkeypatch.setattr(si, "WebDriverWait", DummyWait)
    monkeypatch.setattr(si, "EC", DummyEC)
    monkeypatch.setattr("interface_py.driver_utils.setup_driver", lambda: driver)
    monkeypatch.setattr(si, "setup_driver", lambda: driver)
    monkeypatch.setattr(si, "_find_product_name", lambda d: "prod")
    monkeypatch.setattr(si, "_download_binary", lambda url, dest, ua: dest.write_bytes(b"img"))

    load_calls = []
    monkeypatch.setattr(si, "_load_alt_sentences", lambda p: load_calls.append(p) or {})
    rename_calls = []
    monkeypatch.setattr(si, "_rename_with_alt", lambda *a, **k: rename_calls.append(a) or a[0])

    res = si.download_images(
        "http://example.com",
        css_selector="img",
        parent_dir=tmp_path,
        use_alt_json=True,
        alt_json_path="",
    )

    assert load_calls == []
    assert rename_calls == []
    files = list(res["folder"].iterdir())
    assert len(files) == 1
    assert files[0].name == "ds.png"


def test_download_images_same_names_on_repeat(tmp_path, monkeypatch):
    elem = ElementDataSrc()

    monkeypatch.setattr(si, "WebDriverWait", DummyWait)
    monkeypatch.setattr(si, "EC", DummyEC)
    monkeypatch.setattr("interface_py.driver_utils.setup_driver", lambda: DummyDriver([elem]))
    monkeypatch.setattr(si, "setup_driver", lambda: DummyDriver([elem]))
    monkeypatch.setattr(si, "_find_product_name", lambda d: "prod")
    monkeypatch.setattr(si, "_download_binary", lambda url, dest, ua: dest.write_bytes(b"img"))

    res1 = si.download_images(
        "http://example.com",
        css_selector="img",
        parent_dir=tmp_path,
        use_alt_json=False,
    )
    files1 = sorted(p.name for p in res1["folder"].iterdir())

    for p in res1["folder"].iterdir():
        p.unlink()

    res2 = si.download_images(
        "http://example.com",
        css_selector="img",
        parent_dir=tmp_path,
        use_alt_json=False,
    )
    files2 = sorted(p.name for p in res2["folder"].iterdir())

    assert files1 == files2


def test_download_images_consistent_parallel_runs(tmp_path, monkeypatch):
    elem = ElementDataSrc()

    monkeypatch.setattr(si, "WebDriverWait", DummyWait)
    monkeypatch.setattr(si, "EC", DummyEC)
    monkeypatch.setattr("interface_py.driver_utils.setup_driver", lambda: DummyDriver([elem]))
    monkeypatch.setattr(si, "setup_driver", lambda: DummyDriver([elem]))
    monkeypatch.setattr(si, "_find_product_name", lambda d: "prod")
    monkeypatch.setattr(si, "_download_binary", lambda url, dest, ua: dest.write_bytes(b"img"))

    results = []

    def worker(dest):
        res = si.download_images(
            "http://example.com",
            css_selector="img",
            parent_dir=dest,
            use_alt_json=False,
        )
        results.append(sorted(p.name for p in res["folder"].iterdir()))

    t1 = threading.Thread(target=worker, args=(tmp_path / "a",))
    t2 = threading.Thread(target=worker, args=(tmp_path / "b",))
    t1.start(); t2.start(); t1.join(); t2.join()

    assert len(results) == 2
    assert results[0] == results[1]
