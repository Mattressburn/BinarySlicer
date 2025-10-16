import json
from modules.paths import config_path

def load_theme(mode="light"):
    with open(config_path("theme.json"), "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get(mode, data["light"])
