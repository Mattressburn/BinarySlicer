"""Launcher for BinarySlicer supporting Tkinter and Qt."""

from __future__ import annotations

import argparse
import sys

from binaryslicer.ui import main as tk_main


def main() -> None:
    parser = argparse.ArgumentParser(description="BinarySlicer launcher")
    parser.add_argument("--tk", action="store_true", help="Launch the legacy Tkinter interface")
    parser.add_argument("--qt", action="store_true", help="Launch the PySide6/Qt interface (default)")
    args = parser.parse_args()

    if args.tk:
        tk_main()
        return

    try:
        from binaryslicer.qt_app import launch_qt
    except ImportError:
        print(  # noqa: T201
            "PySide6 is required for the Qt interface. Install with `pip install PySide6` or run with --tk for legacy UI."
        )
        sys.exit(1)

    launch_qt()


if __name__ == "__main__":
    main()
