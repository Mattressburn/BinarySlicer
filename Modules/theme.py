import json
from modules.paths import config_path

THEME_FILENAME = "theme.json"
DEFAULT_MODE = "light"


def _read_theme_doc():
    try:
        with open(config_path(THEME_FILENAME), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_theme_doc(doc):
    path = config_path(THEME_FILENAME)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2)
    except Exception:
        pass


def load_theme(mode=None):
    data = _read_theme_doc()
    if mode is None:
        mode = data.get("active_mode", DEFAULT_MODE)
    theme = data.get(mode)
    if isinstance(theme, dict):
        return theme
    fallback = data.get("light")
    if isinstance(fallback, dict):
        return fallback
    return {}


def load_theme_mode(default=DEFAULT_MODE):
    data = _read_theme_doc()
    mode = data.get("active_mode", default)
    if isinstance(data.get(mode), dict):
        return mode
    if isinstance(data.get("light"), dict):
        return "light"
    return default


def save_theme_mode(mode):
    data = _read_theme_doc()
    if not isinstance(data, dict) or not data:
        return
    data["active_mode"] = mode
    _write_theme_doc(data)
