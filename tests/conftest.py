import sys
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def temp_config_dir(tmp_path, monkeypatch):
    """Isolate user config to a temp directory for tests."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    # Clear cached paths
    import binaryslicer.paths as paths

    paths.resolve_config_path.cache_clear()
    try:
        paths.user_config_dir.cache_clear()  # type: ignore[attr-defined]
    except Exception:
        pass
    yield
    paths.resolve_config_path.cache_clear()
    try:
        paths.user_config_dir.cache_clear()  # type: ignore[attr-defined]
    except Exception:
        pass
