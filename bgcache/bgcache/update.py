"""Studio updates (0.8.0b13): the pipeline profile's "releases_folder" holds
release zips (bgcache_<version>.zip, bgcache/ at the top, as build_release.py
makes them). The player looks there when it opens and from bgcache > Check
for updates; "Update and restart" asks your Maya to:

  1. stop bgcache and switch off this copy's callbacks (controller.unload),
  2. copy the installed bgcache folder to .bgcache_backups beside it,
  3. put the new bgcache in its place (the profile.json goes with the zip;
     a zip without one keeps the installed one),
  4. forget the old code in this Maya and start the new copy.

No restart of Maya, no installer to drag. Nothing here runs unless the
profile names a releases folder.
"""
import glob
import os
import re
import shutil
import sys
import tempfile
import time
import zipfile

ZIP_RE = re.compile(r"^bgcache_(\d[\w.]*)\.zip$")


def version_key(v):
    """Sort key: 0.7.5 < 0.8.0b1 < 0.8.0b2 < 0.8.0 (test builds before the release)."""
    m = re.match(r"(\d+)\.(\d+)(?:\.(\d+))?(?:(a|b|rc)(\d+))?", v or "")
    if not m:
        return (-1, -1, -1, -1, -1, v or "")
    major, minor, patch, tag, n = m.groups()
    stage = {"a": 0, "b": 1, "rc": 2}.get(tag, 3)
    return (int(major), int(minor), int(patch or 0), stage, int(n or 0), v)


def releases(folder):
    """{version: zip path} in the releases folder, or its releases/ subfolder
    (the install folder's layout). Unreadable folder: {}."""
    out = {}
    if not folder:
        return out
    for where in (os.path.join(folder, "releases"), folder):
        try:
            names = os.listdir(where)
        except (OSError, TypeError):
            continue
        for name in names:
            m = ZIP_RE.match(name)
            if m:
                out[m.group(1)] = os.path.join(where, name)
    return out


def newer_release(folder, current):
    """(version, zip path) of the newest release newer than `current`, else None."""
    found = releases(folder)
    if not found:
        return None
    best = max(found, key=version_key)
    if version_key(best) <= version_key(current):
        return None
    return best, found[best]


def _version_of(package_dir):
    try:
        with open(os.path.join(package_dir, "__init__.py")) as handle:
            m = re.search(r"__version__\s*=\s*['\"]([^'\"]+)", handle.read())
        return m.group(1) if m else "unknown"
    except (IOError, OSError):
        return "unknown"


def install_over(zip_path, package_dir, log=print):
    """Replace the bgcache folder `package_dir` with the one in `zip_path`.
    Returns (old version, new version, backup folder). Raises RuntimeError
    with a plain message when it can't (and then nothing has changed)."""
    package_dir = os.path.abspath(package_dir)
    parent = os.path.dirname(package_dir)
    if not os.access(parent, os.W_OK) or not os.access(package_dir, os.W_OK):
        raise RuntimeError("bgcache is installed in %s and you can't write there. "
                           "Ask the pipeline team to install %s." % (parent, os.path.basename(zip_path)))
    stamp = time.strftime("%Y%m%d_%H%M%S")
    tmp = tempfile.mkdtemp(prefix="bgcache_update_")
    try:
        try:
            with zipfile.ZipFile(zip_path) as archive:
                archive.extractall(tmp)
        except (IOError, OSError, zipfile.BadZipfile) as error:
            raise RuntimeError("Couldn't read %s: %s" % (zip_path, error))
        source = os.path.join(tmp, "bgcache")
        if not os.path.isfile(os.path.join(source, "controller.py")):
            raise RuntimeError("%s doesn't look like a bgcache release (no bgcache/controller.py inside)."
                               % zip_path)
        old, new = _version_of(package_dir), _version_of(source)
        old_profile = os.path.join(package_dir, "profile.json")
        if os.path.isfile(old_profile) and not os.path.isfile(os.path.join(source, "profile.json")):
            shutil.copy2(old_profile, source)              # a zip without a profile keeps yours
        backups = os.path.join(parent, ".bgcache_backups")
        os.makedirs(backups, exist_ok=True)
        backup = os.path.join(backups, "bgcache_%s_%s" % (old, stamp))
        shutil.copytree(package_dir, backup, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        log("bgcache update: %s backed up to %s" % (old, backup))
        # Swap by renaming, so a failure halfway leaves the old copy in place.
        aside = package_dir + ".old_" + stamp
        os.rename(package_dir, aside)
        try:
            shutil.copytree(source, package_dir, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        except Exception:
            shutil.rmtree(package_dir, ignore_errors=True)
            os.rename(aside, package_dir)
            raise
        shutil.rmtree(aside, ignore_errors=True)
        return old, new, backup
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _copy_icons(package_dir):
    try:
        import maya.cmds as cmds
        icons = cmds.internalVar(userBitmapsDir=True)
        os.makedirs(icons, exist_ok=True)
        for png in glob.glob(os.path.join(package_dir, "icons", "*.png")):
            shutil.copy2(png, icons)
    except Exception as error:                 # icons are cosmetic
        print("bgcache update: icons not copied: %s" % error)


def _forget_loaded_code():
    for name in [n for n in sys.modules if n == "bgcache" or n.startswith("bgcache.")]:
        sys.modules.pop(name, None)


def update_and_restart(zip_path):
    """Runs in your Maya (the player's "Update and restart")."""
    import importlib
    import maya.cmds as cmds
    import maya.api.OpenMaya as om
    import bgcache
    old = sys.modules.get("bgcache.controller")
    package_dir = os.path.dirname(os.path.abspath(bgcache.__file__))
    kwargs = dict(getattr(old, "_start_kwargs", None) or {})
    if old is not None and hasattr(old, "unload"):
        old.unload()                           # stops bgcache: the player closes
    try:
        before, after, backup = install_over(zip_path, package_dir)
    except Exception as error:
        om.MGlobal.displayWarning("bgcache update failed: %s" % error)
        try:
            cmds.confirmDialog(title="bgcache update", message="The update didn't install:\n\n%s\n\n"
                               "bgcache %s is still installed." % (error, bgcache.__version__), button=["OK"])
        except Exception:  # no UI (batch Maya): the warning above is enough
            pass
        if old is not None:                    # carry on with the copy you had
            cmds.evalDeferred(lambda: old.shelf_click(**kwargs), lowestPriority=True)
        return False
    _copy_icons(package_dir)
    _forget_loaded_code()
    # Python remembers each folder's contents; it may have looked while the
    # old copy was moved aside (b13 -> b14 at the studio: "No module named
    # 'bgcache'" with the new copy in place). Make it look again.
    importlib.invalidate_caches()
    parent = os.path.dirname(package_dir)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    try:
        new = importlib.import_module("bgcache.controller")
    except Exception as error:
        message = ("bgcache %s is installed, but this Maya couldn't load it (%s). "
                   "Restart Maya to finish the update." % (after, error))
        om.MGlobal.displayWarning("bgcache: " + message)
        try:
            cmds.confirmDialog(title="bgcache update", message=message, button=["OK"])
        except Exception:  # no UI (batch Maya): the warning above is enough
            pass
        return False
    print("bgcache: updated %s -> %s (the old copy is in %s). Starting it." % (before, after, backup))
    om.MGlobal.displayInfo("bgcache updated to %s" % after)
    cmds.evalDeferred(lambda: new.shelf_click(**kwargs), lowestPriority=True)
    return True
