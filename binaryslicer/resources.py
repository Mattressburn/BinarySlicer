"""Access to default BinarySlicer resource payloads."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

_PACKAGE = "binaryslicer.data"


def load_default_json(name: str) -> Any:
    with resources.files(_PACKAGE).joinpath(name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def default_theme() -> Any:
    return load_default_json("default_theme.json")


def default_formats() -> Any:
    return load_default_json("default_formats.json")


__all__ = ["default_theme", "default_formats", "load_default_json"]
