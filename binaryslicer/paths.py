"""Utilities for resolving BinarySlicer data locations."""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Optional

APP_NAME = "BinarySlicer"


def _path_from_env(var: str) -> Optional[Path]:
    value = os.getenv(var)
    return Path(value).expanduser() if value else None


@lru_cache(maxsize=1)
def application_dir() -> Path:
    """Return the directory containing the running application."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    candidate = Path(sys.argv[0]).expanduser()
    try:
        return candidate.resolve().parent
    except FileNotFoundError:
        return Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def portable_config_dir() -> Path:
    """Configuration directory bundled with the application."""
    return application_dir() / "config"


@lru_cache(maxsize=1)
def user_config_dir() -> Path:
    """Compute a writable per-user configuration directory."""
    if sys.platform.startswith("win"):
        base = _path_from_env("APPDATA") or Path.home() / "AppData" / "Roaming"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = _path_from_env("XDG_CONFIG_HOME") or Path.home() / ".config"
    return base / APP_NAME


def ensure_user_config_dir() -> Path:
    path = user_config_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def bundled_resource_path(name: str) -> Path:
    """Return the path to a resource bundled with the source tree."""
    return portable_config_dir() / name


@lru_cache(maxsize=None)
def _resolve_config_path_cached(name: str) -> Path:
    """Memoized helper for locating a configuration file."""
    portable = bundled_resource_path(name)
    if portable.exists():
        return portable
    ensure_user_config_dir()
    return user_config_dir() / name


def resolve_config_path(name: str) -> Path:
    """Locate a configuration file, preferring user data when available."""
    user_path = user_config_dir() / name
    if user_path.exists():
        return user_path
    path = _resolve_config_path_cached(name)
    if path != user_path and user_path.exists():
        _resolve_config_path_cached.cache_clear()
        return resolve_config_path(name)
    return path


resolve_config_path.cache_clear = _resolve_config_path_cached.cache_clear


def writable_config_path(name: str) -> Path:
    """Return a path under the user config directory for saving data."""
    ensure_user_config_dir()
    return user_config_dir() / name


__all__ = [
    "APP_NAME",
    "application_dir",
    "portable_config_dir",
    "user_config_dir",
    "ensure_user_config_dir",
    "bundled_resource_path",
    "resolve_config_path",
    "writable_config_path",
]
