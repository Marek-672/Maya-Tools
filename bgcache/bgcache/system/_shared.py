"""Small helpers the system files share. No Maya imports."""
import os
import shutil


def executable(path):
    """An existing file we may run."""
    if not path or not os.path.isfile(path):
        return False
    return os.name == "nt" or os.access(path, os.X_OK)


def first(paths):
    for path in paths:
        if executable(path):
            return path
    return None


def on_path(names):
    return [shutil.which(n) for n in names]


def maya_location():
    return os.environ.get("MAYA_LOCATION", "")
