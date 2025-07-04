"""Utility to find a CSS selector for product links in an HTML snippet."""

from __future__ import annotations

import re
import sys
from typing import Iterable

from bs4 import BeautifulSoup

# Patterns of classes considered too generic or dynamic to use in a selector
_BLACKLIST_PATTERNS = [
    re.compile(pattern)
    for pattern in (
        r"^v-stack$",
        r"^h-stack$",
        r"^gap-",
        r"^grid$",
        r"^grid-",
        r"^w-full$",
        r"^h-full$",
    )
]


def _clean_classes(classes: Iterable[str] | None) -> list[str]:
    if not classes:
        return []
    return [c for c in classes if not any(pat.search(c) for pat in _BLACKLIST_PATTERNS)]


def _build_selector(a_tag) -> str:
    parts: list[str] = ["a"]
    for parent in a_tag.parents:
        if parent.name == "[document]":
            break
        classes = _clean_classes(parent.get("class"))
        if parent.get("id"):
            parts.append(f"{parent.name}#{parent['id']}")
            break
        if classes:
            parts.append(f"{parent.name}." + ".".join(classes))
            break
    return " ".join(reversed(parts))


def find_best_css_selector(html: str) -> str:
    """Return a CSS selector to locate product links in *html*.

    The selector targets ``<a>`` elements that contain text and an ``href``
    attribute. The function tries to keep the selector short while avoiding
    overly generic classes.
    """

    soup = BeautifulSoup(html, "html.parser")
    anchors = [
        a
        for a in soup.find_all("a")
        if a.get("href") and a.get_text(strip=True)
    ]
    if not anchors:
        raise ValueError("No valid <a> tags found")

    candidates = { _build_selector(a) for a in anchors }
    return sorted(candidates, key=len)[0]


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Generate a CSS selector for product links from HTML input"
    )
    parser.add_argument("file", nargs="?", help="Path to an HTML file")
    args = parser.parse_args()

    if args.file:
        with open(args.file, "r", encoding="utf-8") as fh:
            content = fh.read()
    else:
        content = sys.stdin.read()
    print(find_best_css_selector(content))

