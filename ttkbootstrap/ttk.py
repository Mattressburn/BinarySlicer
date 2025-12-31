"""ttk widget wrappers that accept a ``bootstyle`` keyword.

The wrappers delegate to the standard ``tkinter.ttk`` widgets while translating
``bootstyle`` into the appropriate ``style`` name (e.g., ``primary`` ->
``Primary.TButton``). Any unsupported bootstyle text is ignored so callers can
fall back to the default ttk rendering without errors.
"""

from __future__ import annotations

import tkinter.ttk as _ttk
from typing import Any

_STYLE_WIDGETS = {
    "Button",
    "Checkbutton",
    "Combobox",
    "Entry",
    "Frame",
    "Label",
    "Labelframe",
    "Notebook",
    "Panedwindow",
    "Progressbar",
    "Radiobutton",
    "Scale",
    "Scrollbar",
    "Separator",
    "Sizegrip",
    "Spinbox",
    "Treeview",
}


def _bootstrap_class(cls_name: str) -> type:
    base_cls = getattr(_ttk, cls_name)

    class Wrapper(base_cls):  # type: ignore[misc,valid-type]
        def __init__(self, *args: Any, bootstyle: str | None = None, **kwargs: Any) -> None:
            style = kwargs.pop("style", None)
            if bootstyle:
                bootstyle_clean = bootstyle.split()[0].strip()
                if bootstyle_clean:
                    style = f"{bootstyle_clean.capitalize()}.T{cls_name}"
            if style:
                kwargs["style"] = style
            super().__init__(*args, **kwargs)

    Wrapper.__name__ = cls_name
    Wrapper.__qualname__ = cls_name
    return Wrapper


globals().update({name: _bootstrap_class(name) for name in _STYLE_WIDGETS})

__all__ = sorted(_STYLE_WIDGETS)
