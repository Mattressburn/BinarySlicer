"""JSON configuration helpers with safe fallbacks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict

from .paths import (
    bundled_resource_path,
    ensure_user_config_dir,
    user_config_dir,
    writable_config_path,
)

JSONDict = Dict[str, Any]


class ConfigError(RuntimeError):
    pass


def _read_json(path: Path) -> JSONDict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: JSONDict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    tmp.replace(path)


def load_json(name: str, default_factory: Callable[[], JSONDict]) -> JSONDict:
    """Load a JSON document, copying defaults into the user config when needed."""

    ensure_user_config_dir()
    user_path = user_config_dir() / name

    try:
        return _read_json(user_path)
    except FileNotFoundError:
        pass
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {user_path}") from exc

    portable_path = bundled_resource_path(name)
    try:
        payload = _read_json(portable_path)
    except FileNotFoundError:
        payload = default_factory()
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {portable_path}") from exc

    save_json(name, payload)
    return payload


def save_json(name: str, payload: JSONDict) -> Path:
    path = writable_config_path(name)
    _write_json(path, payload)
    return path


__all__ = ["ConfigError", "load_json", "save_json"]
