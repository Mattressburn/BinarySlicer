# launcher.py (repo root)
import argparse
from importlib import import_module

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BinarySlicer launcher")
    parser.add_argument("--qt", action="store_true", help="Launch the PySide6/Qt interface")
    args = parser.parse_args()

    if args.qt:
        qt_app = import_module("binaryslicer.qt_app")
        qt_app.main()
    else:
        tk_ui = import_module("binaryslicer.ui")
        tk_ui.main()
