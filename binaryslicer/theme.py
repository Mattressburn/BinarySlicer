"""Theme tokens and persistence for BinarySlicer."""

from __future__ import annotations

from typing import Dict, Mapping

from .config import load_json, save_json
from .resources import default_theme

THEME_FILENAME = "theme.json"

ThemeTokens = Dict[str, str]
ThemeDocument = Dict[str, Dict]

dark_charcoal_jci: ThemeTokens = {
    "bg": "#0f1116",
    "panel": "#171a21",
    "panel2": "#1f232d",
    "border": "#2b313b",
    "text": "#f3f5fa",
    "muted": "#b5bcc9",
    "accent": "#0399CC",
    "accent2": "#00B8E0",
    "select": "#0554A3",
    "ok": "#29B582",
    "warn": "#7DBA00",
    "error": "#E2555D",
}

light_jci: ThemeTokens = {
    "bg": "#f5f6fb",
    "panel": "#ffffff",
    "panel2": "#eef0f8",
    "border": "#d9dce5",
    "text": "#1d2230",
    "muted": "#4b5364",
    "accent": "#0399CC",
    "accent2": "#00B8E0",
    "select": "#0554A3",
    "ok": "#29B582",
    "warn": "#7DBA00",
    "error": "#C43E44",
}

THEMES: Mapping[str, ThemeTokens] = {
    "dark_charcoal_jci": dark_charcoal_jci,
    "light_jci": light_jci,
}

DEFAULT_THEME_DOCUMENT: ThemeDocument = {
    "schema_version": 2,
    "theme_pack_version": "2025.10.15",
    "last_mode": "light_jci",
    "themes": {},
}


def load_theme_document() -> ThemeDocument:
    """Return persisted theme preferences."""
    document = load_json(THEME_FILENAME, default_theme)
    if "schema_version" not in document:
        document = DEFAULT_THEME_DOCUMENT | {"themes": {}, "last_mode": "light_jci"}
    document.setdefault("themes", {})
    document.setdefault("last_mode", "light_jci")
    return document


def save_theme_document(doc: ThemeDocument) -> None:
    """Persist theme preferences."""
    save_json(THEME_FILENAME, doc)


def resolve_theme(mode: str, doc: ThemeDocument | None = None) -> ThemeTokens:
    """Merge built-in tokens with any persisted overrides."""
    document = doc or {}
    base = THEMES.get(mode) or THEMES["light_jci"]

    # Support legacy documents that stored themes at the top level.
    overrides = {}
    themes_section = document.get("themes") or {}
    if mode in themes_section:
        overrides = themes_section.get(mode, {})
    elif mode in document:
        overrides = document.get(mode, {})

    tokens = dict(base)
    tokens.update(overrides)
    return tokens


def available_themes() -> tuple[str, ...]:
    return tuple(THEMES.keys())


__all__ = [
    "THEME_FILENAME",
    "THEMES",
    "available_themes",
    "dark_charcoal_jci",
    "light_jci",
    "load_theme_document",
    "resolve_theme",
    "save_theme_document",
    "ThemeTokens",
    "ThemeDocument",
]
