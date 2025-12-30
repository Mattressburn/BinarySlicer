import json

import pytest

import binaryslicer.paths as paths
import binaryslicer.config as config


@pytest.fixture(autouse=True)
def reset_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    paths.user_config_dir.cache_clear()
    paths.resolve_config_path.cache_clear()
    yield
    paths.user_config_dir.cache_clear()
    paths.resolve_config_path.cache_clear()


def test_load_json_prefers_user_copy(tmp_path):
    user_file = paths.user_config_dir() / "custom.json"
    user_file.parent.mkdir(parents=True, exist_ok=True)
    user_file.write_text(json.dumps({"value": 5}), encoding="utf-8")

    data = config.load_json("custom.json", lambda: {"value": 1})
    assert data["value"] == 5


def test_load_json_copies_portable_default(tmp_path, monkeypatch):
    portable_dir = tmp_path / "portable"
    portable_dir.mkdir()
    portable_file = portable_dir / "portable.json"
    portable_file.write_text(json.dumps({"value": 9}), encoding="utf-8")

    monkeypatch.setattr(config, "bundled_resource_path", lambda name: portable_dir / name)

    data = config.load_json("portable.json", lambda: {"value": 1})
    assert data["value"] == 9

    user_file = paths.user_config_dir() / "portable.json"
    with user_file.open("r", encoding="utf-8") as handle:
        saved = json.load(handle)
    assert saved == data


