"""Compatibility shim for legacy imports."""

from binaryslicer.paths import (
    application_dir as app_dir,
    user_config_dir as appdata_dir,
    resolve_config_path as config_path,
)

__all__ = ["app_dir", "appdata_dir", "config_path"]
