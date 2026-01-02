"""Launcher for BinarySlicer supporting Tkinter and Qt."""

from __future__ import annotations

import argparse
import sys

from binaryslicer.ui import main as tk_main


def main() -> None:
    parser = argparse.ArgumentParser(description="BinarySlicer launcher")
    parser.add_argument("--qt", action="store_true", help="Launch the PySide6/Qt interface")
    args = parser.parse_args()

    if args.qt:
        try:
            from binaryslicer.qt_app import launch_qt
        except ImportError:
            print("PySide6 is required for the Qt interface. Install with `pip install PySide6`.")  # noqa: T201
            sys.exit(1)
        launch_qt()
    else:
        tk_main()


if __name__ == "__main__":
    main()
