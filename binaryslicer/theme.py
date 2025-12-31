"""Theme tokens and persistence for BinarySlicer."""

from __future__ import annotations

from typing import Dict, Mapping

import tkinter as tk

from ttkbootstrap import Style

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
    "info": "#00B8E0",
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
    "info": "#00B8E0",
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


def _contrast_color(color: str) -> str:
    color = color.lstrip("#")
    r, g, b = (int(color[i : i + 2], 16) for i in (0, 2, 4))
    luma = 0.299 * r + 0.587 * g + 0.114 * b
    return "#000000" if luma > 186 else "#ffffff"


def apply_bootstrap_theme(style: Style, mode: str, tokens: ThemeTokens) -> None:
    """Create or refresh a ttk theme that matches the JCI palette."""

    parent = "superhero" if mode.startswith("dark") else "flatly"
    on_accent = _contrast_color(tokens.get("accent", "#0399CC"))
    on_select = _contrast_color(tokens.get("select", tokens.get("accent", "#0399CC")))

    settings: Dict[str, Dict] = {
        ".": {"configure": {"background": tokens["bg"], "foreground": tokens["text"]}},
        "TFrame": {"configure": {"background": tokens["bg"]}},
        "Panel.TFrame": {"configure": {"background": tokens["panel"]}},
        "TLabelframe": {"configure": {"background": tokens["panel"]}},
        "TLabelframe.Label": {
            "configure": {"background": tokens["panel"], "foreground": tokens["text"]}
        },
        "TLabel": {"configure": {"background": tokens["bg"], "foreground": tokens["text"]}},
        "Header.TLabel": {
            "configure": {
                "background": tokens["panel"],
                "foreground": tokens["text"],
                "font": ("Segoe UI Semibold", 11),
            }
        },
        "Muted.TLabel": {
            "configure": {
                "background": tokens["panel"],
                "foreground": tokens["muted"],
            }
        },
        "TCheckbutton": {
            "configure": {"background": tokens["panel"], "foreground": tokens["text"], "focuscolor": tokens["info"]},
            "map": {
                "focuscolor": [("active", tokens["info"]), ("!disabled", tokens["info"])],
                "indicatorcolor": [("selected", tokens["accent"]), ("active", tokens["info"])],
            },
        },
        "TRadiobutton": {
            "configure": {"background": tokens["panel"], "foreground": tokens["text"], "focuscolor": tokens["info"]},
            "map": {"indicatorcolor": [("selected", tokens["accent"]), ("active", tokens["info"])]},
        },
        "TNotebook": {"configure": {"background": tokens["panel"], "tabmargins": (4, 2, 4, 0)}},
        "TNotebook.Tab": {
            "configure": {
                "background": tokens["panel2"],
                "foreground": tokens["text"],
                "padding": (10, 6),
            },
            "map": {
                "background": [("selected", tokens["accent"]), ("active", tokens["accent2"])],
                "foreground": [("selected", on_accent)],
                "bordercolor": [("focus", tokens["info"]), ("active", tokens["info"])],
            },
        },
        "TEntry": {
            "configure": {
                "fieldbackground": tokens["panel2"],
                "foreground": tokens["text"],
                "insertcolor": tokens["text"],
                "bordercolor": tokens["border"],
                "lightcolor": tokens["info"],
                "selectbackground": tokens["select"],
                "selectforeground": on_select,
            },
            "map": {
                "fieldbackground": [("focus", tokens["panel"]), ("active", tokens["panel"])],
                "foreground": [("disabled", tokens["muted"])],
                "bordercolor": [("focus", tokens["info"]), ("active", tokens["info"])],
            },
        },
        "Primary.TButton": {
            "configure": {
                "background": tokens["accent"],
                "foreground": on_accent,
                "bordercolor": tokens["accent"],
                "focuscolor": tokens["info"],
                "padding": (12, 8),
                "font": ("Segoe UI Semibold", 10),
            },
            "map": {
                "background": [("active", tokens["accent2"]), ("pressed", tokens["select"])],
                "bordercolor": [("focus", tokens["info"]), ("active", tokens["info"])],
                "focuscolor": [("focus", tokens["info"])],
                "foreground": [("disabled", tokens["muted"])],
            },
        },
        "Secondary.TButton": {
            "configure": {
                "background": tokens["panel2"],
                "foreground": tokens["text"],
                "bordercolor": tokens["border"],
                "focuscolor": tokens["info"],
                "padding": (10, 8),
                "font": ("Segoe UI", 10),
            },
            "map": {
                "background": [("active", tokens["accent2"]), ("pressed", tokens["accent"])],
                "bordercolor": [("focus", tokens["accent2"]), ("active", tokens["accent2"])],
                "focuscolor": [("focus", tokens["info"])],
                "foreground": [("disabled", tokens["muted"])],
            },
        },
        "Results.Treeview": {
            "configure": {
                "background": tokens["panel"],
                "fieldbackground": tokens["panel"],
                "foreground": tokens["text"],
                "bordercolor": tokens["border"],
                "borderwidth": 1,
                "rowheight": 28,
            },
            "map": {
                "background": [("selected", tokens["select"])],
                "foreground": [("selected", on_select)],
                "bordercolor": [("focus", tokens["info"])],
            },
        },
        "Results.Treeview.Heading": {
            "configure": {
                "background": tokens["panel2"],
                "foreground": tokens["text"],
                "font": ("Segoe UI Semibold", 10),
                "relief": tk.FLAT,
            }
        },
    }

    if mode in style.theme_names():
        style.theme_settings(mode, settings)
    else:
        style.theme_create(mode, parent=parent, settings=settings)


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
    "apply_bootstrap_theme",
]
