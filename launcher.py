"""Entry point for BinarySlicer."""

from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="BinarySlicer launcher")
    parser.add_argument("--qt", action="store_true", help="Launch the Qt interface (PySide6)")
    args = parser.parse_args()

    if args.qt:
        try:
            from binaryslicer.qtui import main as qt_main  # type: ignore
        except ImportError as exc:  # pragma: no cover - environment dependent
            sys.stderr.write(f"PySide6 is required for --qt: {exc}\n")
            sys.exit(1)
        qt_main()
        return

    from binaryslicer.ui import main as tk_main
    tk_main()


if __name__ == "__main__":
    main()
