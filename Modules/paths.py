import os, sys


def app_dir():
    return os.path.dirname(os.path.abspath(sys.argv[0]))


def appdata_dir():
    env_root = os.getenv("APPDATA")
    if env_root:
        candidate = os.path.join(env_root, "BinarySlicer")
    else:
        candidate = os.path.join(os.path.expanduser("~"), ".binaryslicer")
    try:
        os.makedirs(candidate, exist_ok=True)
    except Exception:
        # Last resort: keep configs beside the executable
        candidate = os.path.join(app_dir(), "config")
        os.makedirs(candidate, exist_ok=True)
    return candidate


def config_path(name):
    portable_dir = os.path.join(app_dir(), "config")
    portable = os.path.join(portable_dir, name)
    if os.path.exists(portable):
        return portable
    base = appdata_dir()
    return os.path.join(base, name)
