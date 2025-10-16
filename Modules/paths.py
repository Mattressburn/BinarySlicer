import os, sys
def app_dir(): return os.path.dirname(os.path.abspath(sys.argv[0]))
def appdata_dir(): return os.path.join(os.getenv("APPDATA"), "BinarySlicer")
def config_path(name):
    p = os.path.join(app_dir(), "config", name)
    if os.path.exists(p): return p
    return os.path.join(appdata_dir(), name)
