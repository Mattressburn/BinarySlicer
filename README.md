# BinarySlicer

BinarySlicer is a Tkinter desktop tool for decoding physical access control payloads. It loads
format definitions and theming information from JSON documents so the app can be extended without
modifying the source code.

## Running the application

```bash
python "Binary Slicer.py"
```

The script launches the Tkinter UI from the `binaryslicer.ui` module. When building a frozen
executable (e.g. with PyInstaller) include the `binaryslicer/`, `icons/`, and `config/` directories
so the runtime resources are available.

## Configuration and data files

* **Portable defaults** – The repository ships JSON defaults in `binaryslicer/data/`. These values
  are copied to the user configuration directory the first time the application runs.
* **User configuration** – Writable copies live in the OS specific configuration directory:
  * Windows: `%APPDATA%/BinarySlicer`
  * macOS: `~/Library/Application Support/BinarySlicer`
  * Linux: `${XDG_CONFIG_HOME:-~/.config}/BinarySlicer`

The files of interest are:

| File | Purpose |
| ---- | ------- |
| `theme.json` | Stores light/dark palettes and remembers the last selected theme. |
| `formats.json` | Describes card formats, field ranges, and parity coverage. |
| `logs/logs.txt` | Contains a startup log entry for troubleshooting distribution issues. |

You can edit the JSON files directly or use **Tools → Manage Formats** inside the UI to add, clone,
or delete formats.

## Tests

Unit tests can be executed with:

```bash
pytest
```

The suite focuses on the binary parsing helpers (`binaryslicer.formats`) to guard against regressions
when new formats are introduced.
