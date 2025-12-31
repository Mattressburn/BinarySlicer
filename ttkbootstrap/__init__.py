"""Lightweight ttkbootstrap shim for offline environments.

This module provides a minimal subset of the public API used by the
BinarySlicer application. It wraps the standard Tk/ttk classes so widgets
accept a ``bootstyle`` keyword and exposes ``Window`` and ``Style`` helpers
compatible with ttkbootstrap usage.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk as _ttk

# Re-export a ttk module that understands ``bootstyle``.
from . import ttk  # noqa: E402  # isort:skip


class Style(_ttk.Style):
    """Wrapper around ``tkinter.ttk.Style`` with basic theme conveniences."""

    def __init__(self, theme: str | None = None, master: tk.Misc | None = None) -> None:
        super().__init__(master)
        self._ensure_base_themes()
        if theme:
            try:
                self.theme_use(theme)
            except tk.TclError:
                # Fallback gracefully if the theme does not exist yet.
                pass

    def _ensure_base_themes(self) -> None:
        """Guarantee a couple of base themes for downstream customization."""
        if "flatly" not in self.theme_names():
            self.theme_create(
                "flatly",
                parent="clam",
                settings={"TFrame": {"configure": {"background": "#f5f5f5"}}},
            )
        if "superhero" not in self.theme_names():
            self.theme_create(
                "superhero",
                parent="clam",
                settings={"TFrame": {"configure": {"background": "#1b1e26"}}},
            )


class Window(tk.Tk):
    """Root window that pairs with the custom ``Style`` class."""

    def __init__(self, themename: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.style = Style(themename, master=self)
        if themename:
            try:
                self.style.theme_use(themename)
            except tk.TclError:
                pass


__all__ = ["Style", "Window", "ttk"]
