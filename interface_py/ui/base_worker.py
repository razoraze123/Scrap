from __future__ import annotations

import logging

from PySide6.QtCore import QThread, Signal

from .widgets import QtLogHandler


class BaseWorker(QThread):
    """Thread worker providing basic logging setup and cleanup."""

    log = Signal(str)
    finished = Signal()

    def __init__(self, log_level: str = "INFO") -> None:
        super().__init__()
        self.log_level = log_level

    def run(self) -> None:  # noqa: D401
        logger, handler = self._setup_logger()
        try:
            self.work()
        except Exception as exc:  # noqa: BLE001
            logger.error("%s", exc)
        finally:
            self._cleanup_logger(logger, handler)
            self.finished.emit()

    def _setup_logger(self) -> tuple[logging.Logger, logging.Handler]:
        logger = logging.getLogger()
        logger.setLevel(getattr(logging, self.log_level, logging.INFO))
        handler = QtLogHandler(self.log)
        formatter = logging.Formatter("%(levelname)s: %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        return logger, handler

    def _cleanup_logger(self, logger: logging.Logger, handler: logging.Handler) -> None:
        logger.removeHandler(handler)

    def work(self) -> None:
        """Override in subclasses to perform actual processing."""
        raise NotImplementedError
