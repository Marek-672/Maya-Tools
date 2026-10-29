"""0.8.0b15 installers: Maya runs a dropped .py with its folder put first on
sys.path and removes the first entry afterwards. The installers put bgcache's
scripts folder first, so Maya removed THAT, and later imports (Update and
restart) failed with "No module named 'bgcache'" (studio, 2026-10-27). Both
installers now put it back once Maya has finished the drop."""
import os, sys, types, importlib.util
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
later = []
maya = types.ModuleType("maya"); cmds = types.ModuleType("maya.cmds")
cmds.evalDeferred = lambda f, lowestPriority=False: later.append(f)
maya.cmds = cmds
sys.modules.update({"maya": maya, "maya.cmds": cmds})

def dropped(run):
    """What Maya does with a dropped file."""
    sys.path.insert(0, "/shared/BGCache/bgcache-studio")      # the dropped file's folder
    run()
    sys.path.pop(0)                                          # Maya: take the first entry off
    for f in later:
        f()
    del later[:]

for name, rel, call in (("dragdrop", ("tools", "dragdrop", "install_bgcache.py"),
                         lambda m, d: m._forget_loaded_bgcache(d)),
                        ("drag_into_maya", ("tools", "drag_into_maya.py"),
                         lambda m, d: m._scripts_on_path(d))):
    spec = importlib.util.spec_from_file_location("inst_" + name, os.path.join(REPO, *rel))
    m = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(m)
    except Exception as error:
        raise AssertionError("%s didn't load: %s" % (name, error))
    scripts = "/u/someone/maya/modules/bgcache/scripts" if name == "dragdrop" else "/u/someone/maya/scripts"
    dropped(lambda: call(m, scripts))
    assert scripts in sys.path, (name, sys.path[:3])
    sys.path.remove(scripts)
    print("ok: %s: bgcache's folder is still on Maya's search list after the drop" % name)
