import json, os
from modules.paths import config_path

def load_formats():
    with open(config_path("formats.json"), "r", encoding="utf-8") as f:
        return json.load(f)

def merge_formats(base, incoming):
    names = {f["name"]: i for i, f in enumerate(base.get("formats", []))}
    for f in incoming.get("formats", []):
        if f["name"] in names: base["formats"][names[f["name"]]] = f
        else: base["formats"].append(f)
    return base

def save_formats(doc):
    p = config_path("formats.json")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if os.path.exists(p): os.replace(p, p + ".bak")
    with open(p, "w", encoding="utf-8") as f: json.dump(doc, f, indent=2)
