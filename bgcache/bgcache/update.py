"""Updates, only when you ask (0.9.0b2): Help > Check for updates in the
player. Nothing checks by itself and nothing installs by itself.

Where it looks:
  - studio builds: the pipeline profile's "releases_folder", holding release
    zips (bgcache_<version>.zip, bgcache/ at the top, as build_studio.py
    makes them);
  - everyone else: the GitHub releases of the profile's "github_releases"
    repository (tags bgcache-v<version>, zips bgcache-<version>-<system>-
    <edition>.zip). That's bgcache's only network use, and only on that click.

"Update and restart" asks your Maya to:
  1. stop bgcache and switch off this copy's callbacks (controller.unload),
  2. copy the installed bgcache folder to .bgcache_backups beside it,
  3. put the new bgcache in its place (the profile.json goes with the zip;
     a zip without one keeps the installed one),
  4. forget the old code in this Maya and start the new copy.

No restart of Maya, no installer to drag.
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
        source = _package_in(tmp)
        if not source:
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


def _package_in(folder):
    """The bgcache package inside an unpacked release: bgcache/ at the top
    (releases folder zips) or <name>/module/scripts/bgcache (the downloads
    on GitHub, as build_release.py makes them). None if neither."""
    for path in [os.path.join(folder, "bgcache")] + sorted(
            glob.glob(os.path.join(folder, "*", "module", "scripts", "bgcache"))):
        if os.path.isfile(os.path.join(path, "controller.py")):
            return path
    return None


# ---------------------------------------------------------------- GitHub
TAG_PREFIX = "bgcache-v"


def _plain_network_error(error):
    """A network failure in words an artist can act on."""
    code = getattr(error, "code", None)
    text = str(getattr(error, "reason", "") or error)
    if code == 404:
        return "the releases page can't be found (it may not be public yet)"
    if code in (403, 429):
        return "GitHub is busy right now (too many checks); try again later"
    if "CERTIFICATE" in text.upper():
        return "this Maya's Python can't verify GitHub's certificate"
    if code:
        return "GitHub answered with an error (%s)" % code
    return "no connection to GitHub (%s)" % text[:80]


def _get(url, timeout, accept="application/vnd.github+json"):
    import urllib.request
    request = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": "bgcache"})
    return urllib.request.urlopen(request, timeout=timeout)


def github_releases(repo, timeout=8.0):
    """bgcache's published releases on GitHub, newest first: dicts with
    version, notes, page and assets {file name: download url}. Raises
    RuntimeError with a plain message when GitHub can't be reached."""
    import json
    try:
        with _get("https://api.github.com/repos/%s/releases?per_page=50" % repo, timeout) as answer:
            data = json.loads(answer.read().decode("utf-8"))
    except Exception as error:     # urllib's many error types: all become one plain message
        raise RuntimeError(_plain_network_error(error))
    out = []
    for release in data if isinstance(data, list) else []:
        tag = release.get("tag_name") or ""
        if release.get("draft") or not tag.startswith(TAG_PREFIX):
            continue                # drafts, and other tools' releases in the same repository
        out.append({"version": tag[len(TAG_PREFIX):], "notes": release.get("body") or "",
                    "page": release.get("html_url") or "",
                    "assets": {a.get("name"): a.get("browser_download_url")
                               for a in release.get("assets") or []}})
    out.sort(key=lambda r: version_key(r["version"]), reverse=True)
    return out


def check_github(repo, current, system_name, edition, timeout=8.0):
    """What Help > Check for updates shows, from GitHub: a dict with state
    "newer" (and version, notes, page, zip_url, zip_name), "latest" or
    "error" (and message, page)."""
    page = "https://github.com/%s/releases" % repo
    try:
        found = github_releases(repo, timeout)
    except RuntimeError as error:
        return {"state": "error", "message": str(error), "page": page}
    if not found:
        return {"state": "error", "message": "no bgcache releases there yet", "page": page}
    newest = found[0]
    if version_key(newest["version"]) <= version_key(current):
        return {"state": "latest", "version": current, "page": page}
    name = "bgcache-%s-%s-%s.zip" % (newest["version"], system_name, edition)
    url = newest["assets"].get(name)
    if not url:
        return {"state": "error", "page": newest["page"] or page,
                "message": "%s is out, but without a %s download" % (newest["version"], name)}
    return {"state": "newer", "version": newest["version"], "notes": newest["notes"],
            "page": newest["page"] or page, "zip_url": url, "zip_name": name}


def check_folder(folder, current):
    """The same answer as check_github, from a studio releases folder."""
    if not os.path.isdir(folder):
        return {"state": "error", "message": "can't see the releases folder %s" % folder}
    found = newer_release(folder, current)
    if not found:
        return {"state": "latest", "version": current}
    return {"state": "newer", "version": found[0], "zip": found[1], "notes": ""}


def download(url, dest_folder, name, timeout=60.0):
    """Save a release zip; returns its path. Raises RuntimeError (plain)."""
    os.makedirs(dest_folder, exist_ok=True)
    path = os.path.join(dest_folder, name)
    part = path + ".part"
    try:
        answer = _get(url, timeout, accept="application/octet-stream")
    except Exception as error:     # urllib's many error types: one plain message
        raise RuntimeError(_plain_network_error(error))
    try:
        with answer, open(part, "wb") as out:
            shutil.copyfileobj(answer, out)
        os.replace(part, path)
    except Exception as error:     # cut off or disk full: no half file left behind
        if os.path.exists(part):
            os.remove(part)
        raise RuntimeError("the download didn't finish (%s)" % error)
    with zipfile.ZipFile(path) as archive:
        if not any(n.endswith("bgcache/controller.py") for n in archive.namelist()):
            raise RuntimeError("the download isn't a bgcache release")
    return path


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
