#!/usr/bin/env python3
"""Build the release downloads from this source folder.

    python3 tools/build_release.py [out_folder]

Makes, for each system (windows, macos, linux) and edition:
    bgcache-<version>-<system>-simple.zip   playback + drawing
    bgcache-<version>-<system>-full.zip     + the continuity add-on, example
                                            profiles and tools/check_profile.py
Each holds install_bgcache.py (drag into Maya), README.txt and module/
(module/scripts/bgcache, module/icons). The code is the same in all three
systems' zips; each picks its own bgcache/system/ file when it runs. Never
includes studio_private/ or a profile.json.
"""
import os
import re
import shutil
import sys
import tempfile
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYSTEMS = {"windows": "Windows", "macos": "macOS", "linux": "Linux"}
SKIP = shutil.ignore_patterns("__pycache__", "*.pyc", "profile.json")


def version():
    text = open(os.path.join(REPO, "bgcache", "__init__.py")).read()
    return re.search(r'__version__\s*=\s*"([^"]+)"', text).group(1)


def stage(root, full, system_name):
    module = os.path.join(root, "module")
    skip = SKIP if full else shutil.ignore_patterns("__pycache__", "*.pyc", "profile.json", "continuity")
    shutil.copytree(os.path.join(REPO, "bgcache"), os.path.join(module, "scripts", "bgcache"), ignore=skip)
    shutil.copytree(os.path.join(REPO, "bgcache", "icons"), os.path.join(module, "icons"))
    shutil.copy2(os.path.join(REPO, "tools", "dragdrop", "install_bgcache.py"), root)
    readme = open(os.path.join(REPO, "tools", "dragdrop", "README.txt")).read()
    edition = "Full (with the continuity add-on)" if full else "Simple (playback and drawing)"
    head = "bgcache %s for %s, %s\n\n" % (version(), SYSTEMS[system_name], edition)
    if full:
        readme += ("\nContinuity (the strip of shots around yours): in the player, click Continuity, or\n"
                   "bgcache > Set up continuity..., and show it one movie of your shot. It learns where your\n"
                   "footage lives. Pipeline TDs can write the settings by hand instead: extras/profiles.\n")
    if system_name == "macos":
        readme += "\nmacOS: tested on Apple Silicon with Maya 2025. Please report what you find on other Macs.\n"
    open(os.path.join(root, "README.txt"), "w").write(head + readme)
    if full:
        shutil.copytree(os.path.join(REPO, "profiles"), os.path.join(root, "extras", "profiles"))
        os.makedirs(os.path.join(root, "extras", "tools"))
        shutil.copy2(os.path.join(REPO, "tools", "check_profile.py"), os.path.join(root, "extras", "tools"))


def build(out):
    os.makedirs(out, exist_ok=True)
    made = []
    for system_name in SYSTEMS:
        for full in (False, True):
            name = "bgcache-%s-%s-%s" % (version(), system_name, "full" if full else "simple")
            tmp = tempfile.mkdtemp()
            root = os.path.join(tmp, name)
            os.makedirs(root)
            stage(root, full, system_name)
            path = os.path.join(out, name + ".zip")
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
                for folder, _dirs, files in os.walk(root):
                    for f in files:
                        full_path = os.path.join(folder, f)
                        z.write(full_path, os.path.relpath(full_path, tmp))
            shutil.rmtree(tmp)
            made.append(path)
    return made


if __name__ == "__main__":
    for path in build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "dist")):
        print(path)
