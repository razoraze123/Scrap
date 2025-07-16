from __future__ import annotations

"""Utility helpers for Selenium WebDriver management."""

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from pathlib import Path

from settings_manager import SettingsManager, DEFAULT_SETTINGS


def setup_driver(
    headless: bool | None = None,
    driver_path: str | None = None,
    *,
    settings: SettingsManager | None = None,
) -> webdriver.Chrome:
    """Return a configured Chrome WebDriver.

    Parameters
    ----------
    headless: bool | None
        Run Chrome in headless mode if True. If ``None``, the value is
        loaded from ``settings`` and defaults to ``True``.
    driver_path: optional str
        Path to a ChromeDriver binary to use. If absent or invalid,
        ``webdriver_manager`` is used to download a driver.
    settings: SettingsManager | None
        Optional settings manager used to retrieve ``headless`` and ``driver_path``
        when not provided explicitly.
    """
    settings = settings or SettingsManager()

    driver_path = driver_path or settings.settings.get("driver_path")
    if headless is None:
        headless = settings.settings.get("headless", DEFAULT_SETTINGS["headless"])

    options = Options()
    if headless:
        options.add_argument("--headless")
    options.add_argument("--disable-logging")
    options.add_argument("--log-level=3")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--disable-blink-features=AutomationControlled")

    if driver_path and Path(driver_path).is_file():
        service = Service(str(driver_path))
    else:
        service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    # Hide webdriver flag
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    return driver


def _load_headless_from_settings(manager: SettingsManager | None = None) -> bool:
    """Return the ``headless`` setting using :class:`SettingsManager`."""
    manager = manager or SettingsManager()
    return bool(manager.settings.get("headless", DEFAULT_SETTINGS["headless"]))


def _load_driver_path_from_settings(manager: SettingsManager | None = None) -> str | None:
    """Return ChromeDriver path using :class:`SettingsManager`."""
    manager = manager or SettingsManager()
    return manager.settings.get("driver_path")
