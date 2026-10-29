"""Read bgcache's source text for tests that check the code itself.

controller.py was split in 0.8.0b21; source("controller") returns the
Controller's files and scene.py together, so those checks don't care which
file a piece of code lives in."""
import glob
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(REPO, "bgcache")


def files(name):
    if name == "controller":
        return ([os.path.join(PKG, "controller.py")] + sorted(glob.glob(os.path.join(PKG, "controller_*.py")))
                + [os.path.join(PKG, "scene.py")])
    return [os.path.join(PKG, name + ".py")]


def source(name):
    out = []
    for path in files(name):
        with open(path) as handle:
            out.append(handle.read())
    return "\n".join(out)
