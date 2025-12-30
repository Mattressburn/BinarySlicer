"""Theme loading and persistence helpers."""

from __future__ import annotations

from typing import Dict

from .config import load_json, save_json
from .resources import default_theme

THEME_FILENAME = "theme.json"

ThemeDocument = Dict[str, Dict]


def load_theme_document() -> ThemeDocument:
    return load_json(THEME_FILENAME, default_theme)


def load_theme(mode: str = "light") -> Dict:
    doc = load_theme_document()
    return doc.get(mode, doc.get("light", {}))


def save_theme_document(doc: ThemeDocument) -> None:
    save_json(THEME_FILENAME, doc)


__all__ = ["THEME_FILENAME", "load_theme", "load_theme_document", "save_theme_document"]
