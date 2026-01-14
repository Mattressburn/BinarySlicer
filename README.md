# BinarySlicer

BinarySlicer is a desktop tool for decoding physical access control payloads. It supports a modern Qt UI (PySide6) and a legacy Tkinter UI. Format definitions and theming are stored as JSON so the app can be extended without modifying source code.

## Download (Windows)

Grab the latest standalone Windows executable from GitHub Releases:

- Latest release: https://github.com/Mattressburn/BinarySlicer/releases/latest

Current Windows EXE (2026.01.06)
- Version: v2026.01.06
- SHA256: 0C214C1CDEA3A202A8595F0F14B1F8F652F8B0552CAAC9134C9F5AE76CBD314F

Note: The EXE is currently unsigned, so Windows SmartScreen may warn. Use More info -> Run anyway.

## Running the application

Launch the Qt UI (default):

```bash
py launcher.py
```

Launch the legacy Tkinter UI:

```bash
py launcher.py --tk
```

When building a frozen executable (for example with PyInstaller) include runtime resources so icons/config/data are available at runtime.

## Configuration and data files

BinarySlicer ships JSON defaults in `binaryslicer/data/`. These defaults are copied to the user configuration directory the first time the application runs.

User configuration directory:
- Windows: `%APPDATA%\BinarySlicer`
- macOS: `~/Library/Application Support/BinarySlicer`
- Linux: `${XDG_CONFIG_HOME:-~/.config}/BinarySlicer`

Common files:

| File | Purpose |
| ---- | ------- |
| `theme.json` | Stores light/dark palettes and remembers the last selected theme. |
| `formats.json` | Describes card formats, field ranges, and parity coverage. |
| `logs/logs.txt` | Startup logs for troubleshooting distribution issues. |

You can edit the JSON files directly or use Tools -> Manage Formats inside the UI to add, clone, or delete formats.

## Building a Windows executable (PyInstaller)

When building a frozen executable, include runtime resources so icons/config/data are available at runtime.

Required folders:
- `binaryslicer/`
- `binaryslicer/data/`
- `icons/`
- `config/`

Build command (Windows, one-file):

```bash
py -m PyInstaller --clean -F -w -n BinarySlicer --paths . -i icons\jci_globe.ico --hidden-import binaryslicer.data --collect-data binaryslicer --collect-data binaryslicer.data --add-data "icons;icons" --add-data "config;config" launcher.py
```

If using one-file mode, PyInstaller extracts bundled files to a temporary directory at runtime and exposes it via `sys._MEIPASS`.

## Tests

Run unit tests with:

```bash
py -m pytest
```

## Format detection notes

BinarySlicer reports matches as **Exact** when the working bits align to a format's canonical window (bit-length match or a zero-offset window with only benign trailing zero padding) and all gated parity checks pass. It reports **Compatible** when the input is longer and a non-zero offset or framing/padding is required to find a passing window, preserving visibility into ambiguous payloads without claiming a definitive format.

The suite focuses on binary parsing helpers (`binaryslicer.formats`) to guard against regressions when new formats are introduced.
