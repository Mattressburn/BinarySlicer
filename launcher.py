# launcher.py (repo root)
from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="BinarySlicer launcher")
    parser.add_argument("--qt", action="store_true", help="Launch the PySide6/Qt interface")
    args = parser.parse_args(argv)

    if args.qt:
        from binaryslicer.qt import main as qt_main

        qt_main()
    else:
        from binaryslicer.ui import main as tk_main

        tk_main()


if __name__ == "__main__":
    main()
