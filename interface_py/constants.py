"""Common constants for the interface package."""
from pathlib import Path

# Default CSS selectors used across scrapers
IMAGES_DEFAULT_SELECTOR = ".product-gallery__media-list img"
COLLECTION_DEFAULT_SELECTOR = "div.product-card__info h3.product-card__title a"
DEFAULT_NEXT_SELECTOR = "a[rel=\"next\"]"
DESCRIPTION_DEFAULT_SELECTOR = ".rte"
PRICE_DEFAULT_SELECTOR = ".price"
VARIANT_DEFAULT_SELECTOR = ".variant-picker__option-values span.sr-only"

# User agent string for HTTP requests
USER_AGENT = "ScrapImageBot/1.0"

# Sidebar layout constants
ICONS_DIR = Path(__file__).resolve().parents[1] / "icons"
SIDEBAR_EXPANDED_WIDTH = 180
SIDEBAR_COLLAPSED_WIDTH = 40
