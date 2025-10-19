"""Compatibility shim delegating to :mod:`binaryslicer.formats`."""

from binaryslicer.formats import (
    load_formats_document as load_formats,
    merge_formats,
    save_formats_document as save_formats,
)

__all__ = ["load_formats", "merge_formats", "save_formats"]
