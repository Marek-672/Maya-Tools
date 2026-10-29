#!/usr/bin/env python3
"""Install (or update) bgcache for Maya, from your home directory.

    python3 install_bgcache.py                  # the newest build in releases/ (next to
                                                # this script); without releases/, a
                                                # bgcache*.zip next to it, in your home
                                                # folder or in ~/Downloads
    python3 install_bgcache.py /path/to/bgcache.zip
    python3 install_bgcache.py --maya 2025      # a different Maya version (default 2024)
    python3 install_bgcache.py --list           # archived versions, and which one you have
    python3 install_bgcache.py --version 0.6.2  # install an exact version from releases/
    python3 install_bgcache.py --rollback       # put back what you had before your last install

What it does:
  - copies bgcache into ~/maya/<version>/scripts/bgcache
    (an existing copy is moved to ~/maya/<version>/scripts/.bgcache_backups/ first)
  - copies the shelf icon into ~/maya/<version>/prefs/icons
  - prints the one line to run in Maya for the shelf button

Nothing outside your own Maya folders is touched. No Maya needed to run this.
"""
import argparse
import glob
import os
import re
import shutil
import sys
import tempfile
import time
import zipfile

HOME = os.path.expanduser("~")


RELEASES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "releases")


def releases():
    """{version: zip path} for every archived release next to this script."""
    out = {}
    for path in glob.glob(os.path.join(RELEASES, "bgcache_*.zip")):
        m = re.search(r"bgcache_(.+)\.zip$", os.path.basename(path))
        if m:
            out[m.group(1)] = path
    return out


def version_key(v):
    """Sort key: 0.7.5 < 0.8.0b1 < 0.8.0b2 < 0.8.0 (test builds before the release)."""
    m = re.match(r"(\d+)\.(\d+)(?:\.(\d+))?(?:(a|b|rc)(\d+))?", v)
    if not m:
        return (-1, -1, -1, -1, -1, v)
    major, minor, patch, tag, n = m.groups()
    stage = {"a": 0, "b": 1, "rc": 2}.get(tag, 3)
    return (int(major), int(minor), int(patch or 0), stage, int(n or 0), v)


def find_zip(given, version=None):
    if version:
        return releases().get(version)
    if given:
        return os.path.abspath(os.path.expanduser(given))
    found = releases()
    if found:                              # the newest build in releases/
        return found[max(found, key=version_key)]
    here = os.path.dirname(os.path.abspath(__file__))
    for folder in (here, HOME, os.path.join(HOME, "Downloads"), os.getcwd()):
        candidates = sorted(glob.glob(os.path.join(folder, "bgcache*.zip")), key=os.path.getmtime)
        if candidates:
            return candidates[-1]          # newest if there are several
    return None


def maya_dir(version):
    base = os.environ.get("MAYA_APP_DIR") or os.path.join(HOME, "maya")
    return os.path.join(base, version)


def version_of(package_dir):
    try:
        with open(os.path.join(package_dir, "__init__.py")) as handle:
            m = re.search(r'__version__\s*=\s*"([^"]+)"', handle.read())
            return m.group(1) if m else "unknown"
    except (IOError, OSError):
        return None


def backup_path(backups, name):
    """A new, unused folder name in `backups` (two installs in the same second
    must never share one, or the second would land inside the first)."""
    base = os.path.join(backups, "%s_%s" % (name, time.strftime("%Y%m%d_%H%M%S")))
    path, n = base, 2
    while os.path.exists(path):
        path, n = "%s_%d" % (base, n), n + 1
    return path


def backups_of(root):
    """Your earlier installs kept for rollback, oldest first."""
    return sorted(glob.glob(os.path.join(root, "scripts", ".bgcache_backups", "bgcache_*")), key=os.path.getmtime)


def rollback(root, log=print):
    """Put back the install before the last one. Returns (from, to) versions;
    raises RuntimeError when there's nothing to roll back to."""
    target = os.path.join(root, "scripts", "bgcache")
    backups = os.path.join(root, "scripts", ".bgcache_backups")
    mine = backups_of(root)
    if not mine:
        raise RuntimeError("Nothing to roll back to: no earlier install was backed up.")
    previous = mine[-1]
    current = version_of(target)
    if os.path.isdir(target):
        shutil.move(target, backup_path(backups, "bgcache_%s_rolledback" % current))
    shutil.move(previous, target)
    log("Rolled back from %s to %s." % (current, version_of(target)))
    return current, version_of(target)


def install_zip(zip_path, root, log=print):
    """Install the bgcache in `zip_path` into <root>/scripts/bgcache (the old
    copy moved to .bgcache_backups first) and its icons into <root>/prefs/icons.
    Returns (old version or None, new version, icons copied). Raises
    RuntimeError for a zip that isn't bgcache."""
    scripts = os.path.join(root, "scripts")
    icons = os.path.join(root, "prefs", "icons")
    target = os.path.join(scripts, "bgcache")
    # Unpack to a temporary folder first, so a bad zip never leaves a half install.
    tmp = tempfile.mkdtemp(prefix="bgcache_install_")
    try:
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(tmp)
        source = os.path.join(tmp, "bgcache")
        if not os.path.isfile(os.path.join(source, "controller.py")):
            raise RuntimeError("%s doesn't look like a bgcache zip (no bgcache/controller.py inside)." % zip_path)
        new_version = version_of(source)
        log("Installing bgcache %s from %s" % (new_version, zip_path))

        os.makedirs(scripts, exist_ok=True)
        old_version = version_of(target)
        if os.path.isdir(target):
            backups = os.path.join(scripts, ".bgcache_backups")
            os.makedirs(backups, exist_ok=True)
            backup = backup_path(backups, "bgcache_%s" % old_version)
            shutil.move(target, backup)
            log("Previous version %s moved to %s" % (old_version, backup))
        shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

        os.makedirs(icons, exist_ok=True)
        copied = 0
        for png in glob.glob(os.path.join(source, "icons", "*.png")):
            shutil.copy2(png, icons)
            copied += 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return old_version, new_version, copied


def main():
    parser = argparse.ArgumentParser(description="Install bgcache for Maya.")
    parser.add_argument("zip", nargs="?", help="path to bgcache.zip")
    parser.add_argument("--maya", default="2024", help="Maya version folder (default 2024)")
    parser.add_argument("--list", action="store_true", help="list archived versions and the installed one")
    parser.add_argument("--version", help="install this archived version (from releases/)")
    parser.add_argument("--rollback", action="store_true",
                        help="restore the version you had before your last install")
    args = parser.parse_args()

    root = maya_dir(args.maya)
    target = os.path.join(root, "scripts", "bgcache")
    backups = os.path.join(root, "scripts", ".bgcache_backups")

    if args.list:
        print("installed: %s" % (version_of(target) or "none"))
        found = releases()
        print("archived in %s:" % RELEASES)
        for v in sorted(found, key=version_key):
            print("  %s" % v)
        if not found:
            print("  (none)")
        mine = sorted(glob.glob(os.path.join(backups, "bgcache_*")))
        if mine:
            print("your previous installs (for --rollback): %s" % ", ".join(os.path.basename(m) for m in mine[-5:]))
        return

    if args.rollback:
        try:
            rollback(root, log=lambda text: print(text + " Restart Maya."))
        except RuntimeError as error:
            sys.exit(str(error))
        return

    zip_path = find_zip(args.zip, args.version)
    if args.version and not zip_path:
        sys.exit("Version %s isn't archived. Available: %s"
                 % (args.version, ", ".join(sorted(releases(), key=version_key)) or "none"))
    if not zip_path or not os.path.isfile(zip_path):
        sys.exit("Couldn't find a bgcache zip. Put it in releases/ next to this script "
                 "(as bgcache_<version>.zip), or pass its path:\n"
                 "    python3 install_bgcache.py /path/to/bgcache.zip")

    target = os.path.join(root, "scripts", "bgcache")
    icons = os.path.join(root, "prefs", "icons")
    if not os.path.isdir(root):
        print("Note: %s doesn't exist yet (has Maya %s been opened on this account?). "
              "Creating it." % (root, args.maya))
    try:
        old_version, new_version, copied = install_zip(zip_path, root)
    except RuntimeError as error:
        sys.exit(str(error))

    print("")
    print("bgcache %s installed to %s" % (new_version, target))
    print("Shelf icon%s copied to %s" % ("s" if copied != 1 else "", icons))
    print("")
    if old_version:
        print("Updated from %s. Restart Maya so it loads the new version." % old_version)
    else:
        print("Next steps:")
        print("  1. Start (or restart) Maya %s." % args.maya)
        print("  2. In the Script Editor, Python tab, run this once to add the shelf button:")
        print("")
        print("         import bgcache.install; bgcache.install.shelf()")
        print("")
        print("  3. Click the new bgcache button on your shelf, then Start.")


if __name__ == "__main__":
    main()
