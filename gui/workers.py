from __future__ import annotations

import io
import logging
import threading
from pathlib import Path
from typing import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from PySide6.QtCore import Signal

from .utils import QtLogHandler
from interface_py.ui.base_worker import BaseWorker
from interface_py.scrap_collection import scrape_collection
from interface_py.constants import DEFAULT_NEXT_SELECTOR as SLC_DEFAULT_NEXT_SELECTOR
from interface_py import scraper_images
from interface_py.scrap_description import scrape_description
from interface_py.scrap_price import scrape_price
from interface_py import moteur_variante

class ScrapLienWorker(BaseWorker):

    def __init__(
        self,
        url: str,
        output: Path,
        selector: str,
        log_level: str,
        output_format: str,
    ):
        super().__init__(log_level)
        self.url = url
        self.output = output
        self.selector = selector
        self.output_format = output_format

    def _setup_logger(self) -> tuple[logging.Logger, logging.Handler]:
        logger, handler = super()._setup_logger()
        self._stream_handler = logging.StreamHandler(io.StringIO())
        self._stream_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logger.addHandler(self._stream_handler)
        return logger, handler

    def _cleanup_logger(self, logger: logging.Logger, handler: logging.Handler) -> None:
        logger.removeHandler(self._stream_handler)
        super()._cleanup_logger(logger, handler)

    def work(self) -> None:
        scrape_collection(
            self.url,
            self.output,
            self.selector,
            SLC_DEFAULT_NEXT_SELECTOR,
            self.output_format,
        )


class ScraperImagesWorker(BaseWorker):
    """Background worker to download images using scraper_images."""

    progress = Signal(int, int)
    preview_path = Signal(str)

    def __init__(
        self,
        urls: list[str],
        parent_dir: Path,
        selector: str,
        open_folder: bool,
        show_preview: bool,
        alt_json: str | None,
        max_threads: int = 4,
        max_jobs: int = 1,
    ):
        super().__init__()
        self.urls = urls
        self.parent_dir = parent_dir
        self.selector = selector
        self.open_folder = open_folder
        self.show_preview = show_preview
        self.alt_json = alt_json
        self.max_threads = max_threads
        self.max_jobs = max_jobs

    def work(self) -> None:
        logger = logging.getLogger()
        images_done = 0
        total_images = 0
        lock = threading.Lock()

        def make_cb() -> Callable[[int, int], None]:
            first = True

            def cb(i: int, t: int) -> None:
                nonlocal first, images_done, total_images
                with lock:
                    if first:
                        total_images += t
                        first = False
                    images_done += 1
                    self.progress.emit(images_done, total_images)

            return cb

        self.progress.emit(0, 0)

        preview_sent = False
        with ThreadPoolExecutor(max_workers=self.max_jobs) as executor:
            future_to_url = {
                executor.submit(
                    scraper_images.download_images,
                    url,
                    css_selector=self.selector,
                    parent_dir=self.parent_dir,
                    progress_callback=make_cb(),
                    alt_json_path=self.alt_json,
                    max_threads=self.max_threads,
                ): url
                for url in self.urls
            }

            for fut in as_completed(future_to_url):
                url = future_to_url[fut]
                try:
                    info = fut.result()
                    folder = info["folder"]
                    if (
                        self.show_preview
                        and not preview_sent
                        and info.get("first_image")
                    ):
                        self.preview_path.emit(str(info["first_image"]))
                        preview_sent = True
                    if self.open_folder:
                        scraper_images._open_folder(folder)
                except Exception as exc:  # noqa: BLE001
                    logger.error("%s", exc)


class ScrapDescriptionWorker(BaseWorker):
    """Background worker to extract and save product descriptions."""

    def __init__(self, url: str, selector: str, output: Path):
        super().__init__()
        self.url = url
        self.selector = selector
        self.output = output

    def work(self) -> None:
        scrape_description(self.url, self.selector, self.output)


class ScrapPriceWorker(BaseWorker):
    """Background worker to extract and save product price."""

    def __init__(self, url: str, selector: str, output: Path) -> None:
        super().__init__()
        self.url = url
        self.selector = selector
        self.output = output

    def work(self) -> None:
        scrape_price(self.url, self.selector, self.output)


class ScrapVariantWorker(BaseWorker):
    """Background worker to extract and save product variants."""

    def __init__(self, url: str, selector: str, output: Path) -> None:
        super().__init__()
        self.url = url
        self.selector = selector
        self.output = output

    def work(self) -> None:
        title, mapping = moteur_variante.extract_variants_with_images(self.url)
        moteur_variante.save_images_to_file(title, mapping, self.output)


class VariantFetchWorker(BaseWorker):
    """Fetch product variants with images and emit results."""

    result = Signal(str, dict)

    def __init__(self, url: str) -> None:
        super().__init__()
        self.url = url

    def work(self) -> None:
        title, mapping = moteur_variante.extract_variants_with_images(self.url)
        self.result.emit(title, mapping)

