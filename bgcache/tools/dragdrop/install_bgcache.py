"""Drag this file into a Maya viewport to install, update or uninstall bgcache.

It installs bgcache as a Maya module, for every Maya from 2024 up on this
computer, in your own Maya folder (the one Maya itself reports, wherever it
is: another drive, a custom MAYA_APP_DIR):

    <your Maya folder>/modules/bgcache.mod     one line telling Maya where bgcache is
    <your Maya folder>/modules/bgcache/        scripts/bgcache/ (the tool), icons/

and puts a bgcache button on your shelf. It works straight away, no restart,
also for updates (an old version's bgcache panel is closed: everything is in the player now).
Nothing else is touched: not userSetup.py, not Maya.env.

Already installed: Update (your old copy is kept in modules/.bgcache_backups,
so you can go back) or Uninstall (removes the folder, the .mod file and the
shelf button). An older copy in <version>/scripts/bgcache (from the Linux
command-line installer) would hide the new one, so it is moved to that
scripts folder's .bgcache_backups as well.

Without dialogs (e.g. from a script):
    import install_bgcache; install_bgcache.install(quiet=True)
    install_bgcache.uninstall(quiet=True)
"""
import os
import re
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, "module")          # module/scripts/bgcache, module/icons
NAME = "bgcache"


def _forget_self():
    """Since Maya 2022, dropping the same file again runs the copy cached from
    the first drop; forget it so the next drop runs this file afresh."""
    sys.modules.pop(os.path.splitext(os.path.basename(__file__))[0], None)


def _version(package_dir):
    try:
        with open(os.path.join(package_dir, "__init__.py")) as handle:
            m = re.search(r'__version__\s*=\s*"([^"]+)"', handle.read())
        return m.group(1) if m else "unknown"
    except (IOError, OSError):
        return None


def _places():
    import maya.cmds as cmds
    user = os.path.normpath(cmds.internalVar(userAppDir=True))
    modules = os.path.join(user, "modules")
    return {"user": user, "modules": modules,
            "target": os.path.join(modules, NAME),
            "mod": os.path.join(modules, NAME + ".mod"),
            "backups": os.path.join(modules, ".bgcache_backups")}


def _old_script_copies(user):
    """bgcache copies in <user>/<version>/scripts/bgcache or <user>/scripts/bgcache
    (the Linux ./install puts them there); they would be found before the module."""
    out = []
    candidates = [os.path.join(user, "scripts", NAME)]
    try:
        candidates += [os.path.join(user, d, "scripts", NAME) for d in os.listdir(user)]
    except OSError:
        pass
    for path in candidates:
        if os.path.isfile(os.path.join(path, "controller.py")) and path not in out:
            out.append(path)
    return out


def _stamp():
    return time.strftime("%Y%m%d_%H%M%S")


def _unused(path):
    """`path`, or path_2, path_3... so two backups never share a folder."""
    out, n = path, 2
    while os.path.exists(out):
        out, n = "%s_%d" % (path, n), n + 1
    return out


PANEL = "bgcacheWorkspaceControl"
PANEL_LAYOUT = "bgcacheLayout"


def _retire_loaded_bgcache(close_panel=False):
    """Before swapping the code: switch off what the old copy left running in
    this Maya (its Maya callbacks and the panel's buttons point at the old
    code). The panel's contents are removed, so they're rebuilt from the new
    copy; with close_panel (uninstall) the panel goes too."""
    old = sys.modules.get(NAME + ".controller")
    if old is not None:
        if hasattr(old, "unload"):
            try:
                old.unload()
            except Exception as error:
                print("bgcache install: the old copy's unload failed: %s" % error)
        else:                                  # copies before 0.8.0b11
            import maya.cmds as cmds
            try:
                job = getattr(old, "_quit_job", None)
                if job is not None and cmds.scriptJob(exists=job):
                    cmds.scriptJob(kill=job, force=True)
            except Exception:
                pass
            try:
                import maya.api.OpenMaya as om
                for cb in list(getattr(old, "_panel_scene_cbs", [])):
                    om.MMessage.removeCallback(cb)
                del old._panel_scene_cbs[:]
            except Exception:
                pass
    try:
        import maya.cmds as cmds
        if close_panel:
            if cmds.workspaceControl(PANEL, exists=True):
                cmds.deleteUI(PANEL)
            if cmds.workspaceControlState(PANEL, exists=True):
                cmds.workspaceControlState(PANEL, remove=True)
        elif cmds.layout(PANEL_LAYOUT, exists=True):
            cmds.deleteUI(PANEL_LAYOUT)
    except Exception:
        pass


def _refresh_panel():
    """After an update: a panel that's on screen is rebuilt at once from the
    new copy, in the same place (docked stays docked)."""
    try:
        import maya.cmds as cmds
        if (cmds.workspaceControl(PANEL, exists=True)
                and cmds.workspaceControl(PANEL, query=True, visible=True)):
            import bgcache.controller
            bgcache.controller.show_ui()
            return True
    except Exception as error:
        print("bgcache install: panel not rebuilt (%s): click the shelf button" % error)
    return False


def _forget_loaded_bgcache(scripts_dir=None):
    """Make the running Maya use the newly installed copy (or none)."""
    for name in [m for m in sys.modules if m == NAME or m.startswith(NAME + ".")]:
        del sys.modules[name]
    for path in list(sys.path):
        if os.path.isdir(path) and os.path.normcase(os.path.abspath(path)).endswith(
                os.path.normcase(os.path.join("modules", NAME, "scripts"))):
            sys.path.remove(path)
    if scripts_dir:
        sys.path.insert(0, scripts_dir)
        _keep_on_path(scripts_dir)


def _keep_on_path(scripts_dir):
    """Maya runs a dropped file with its folder put first on sys.path and
    takes the FIRST entry off afterwards: that was this folder (inserted just
    above), so bgcache vanished from the path for the rest of the session and
    Update and restart then failed with "No module named 'bgcache'" (studio,
    2026-10-27). Check again once Maya has finished the drop."""
    def again():
        if os.path.normcase(scripts_dir) not in [os.path.normcase(p) for p in sys.path]:
            sys.path.insert(0, scripts_dir)
    try:
        import maya.cmds as cmds
        cmds.evalDeferred(again, lowestPriority=True)
    except Exception:
        pass


def _ask(title, message, buttons, quiet, default):
    if quiet:
        return default
    import maya.cmds as cmds
    return cmds.confirmDialog(title=title, message=message, button=buttons,
                              defaultButton=buttons[0], cancelButton=buttons[-1], dismissString=buttons[-1])


def _tell(message, quiet):
    print("bgcache install: " + message.replace("\n", "\n    "))
    if not quiet:
        import maya.cmds as cmds
        cmds.confirmDialog(title="bgcache", message=message, button=["OK"])


def _running():
    """True if bgcache is running in this Maya (Start pressed, not stopped)."""
    controller = sys.modules.get(NAME + ".controller")
    try:
        return bool(controller and controller.get().running)
    except Exception:
        return False


def install(quiet=False, shelf=True):
    """Install or update. Returns a short report (also printed)."""
    if _running():
        message = "bgcache is running in this Maya: press Stop first, then drag the installer in again."
        _tell(message, quiet)
        return message
    package = os.path.join(SOURCE, "scripts", NAME)
    if not os.path.isfile(os.path.join(package, "controller.py")):
        raise RuntimeError("no bgcache found next to this installer (expected %s)" % package)
    new = _version(package)
    p = _places()
    old = _version(os.path.join(p["target"], "scripts", NAME))
    stale = _old_script_copies(p["user"])
    report = []
    if old or stale:
        what = "bgcache %s is installed." % (old or "(an older copy)")
        choice = _ask("bgcache", "%s\n\nInstall %s over it, or uninstall bgcache?" % (what, new),
                      ["Update", "Uninstall", "Cancel"], quiet, "Update")
        if choice == "Uninstall":
            return uninstall(quiet=quiet)
        if choice != "Update":
            return "cancelled"
    os.makedirs(p["modules"], exist_ok=True)
    kept_profile = None
    if os.path.isdir(p["target"]):
        old_profile = os.path.join(p["target"], "scripts", NAME, "profile.json")
        if os.path.isfile(old_profile) and not os.path.isfile(os.path.join(package, "profile.json")):
            kept_profile = open(old_profile, "rb").read()      # a studio's settings: keep them
        os.makedirs(p["backups"], exist_ok=True)
        backup = _unused(os.path.join(p["backups"], "%s_%s_%s" % (NAME, old, _stamp())))
        shutil.move(p["target"], backup)
        report.append("Previous %s kept in %s" % (old, backup))
    for path in stale:
        backups = os.path.join(os.path.dirname(path), ".bgcache_backups")
        os.makedirs(backups, exist_ok=True)
        moved = _unused(os.path.join(backups, "%s_%s_%s" % (NAME, _version(path), _stamp())))
        shutil.move(path, moved)
        report.append("Older copy %s moved to %s (it would hide the new one)" % (path, moved))
    shutil.copytree(SOURCE, p["target"], ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    if kept_profile is not None:
        with open(os.path.join(p["target"], "scripts", NAME, "profile.json"), "wb") as handle:
            handle.write(kept_profile)
        report.append("Your studio profile.json was kept")
    with open(p["mod"], "w") as handle:
        handle.write("+ %s %s %s\n" % (NAME, new, NAME))
    scripts = os.path.join(p["target"], "scripts")
    _retire_loaded_bgcache(close_panel=True)   # b12: no Maya panel any more, all in the player
    _forget_loaded_bgcache(scripts)
    where = None
    if shelf:
        try:
            import bgcache.install
            where = bgcache.install.shelf()
        except Exception as error:
            report.append("Shelf button not added (%s): run  import bgcache.install; bgcache.install.shelf()" % error)
    lines = ["bgcache %s installed in %s" % (new, p["target"]),
             "Ready to use now, no restart needed."]
    if where:
        lines.append("Shelf button on shelf %r: click it to start (the player opens)." % where)
    message = "\n".join(lines + report)
    _tell(message, quiet)
    return message


def uninstall(quiet=False):
    """Remove the module, its .mod file and the shelf buttons. Returns a report."""
    if _running():
        message = "bgcache is running in this Maya: press Stop first, then uninstall."
        _tell(message, quiet)
        return message
    p = _places()
    removed = []
    buttons = 0
    try:
        import bgcache.install
        buttons = bgcache.install.remove_shelf_buttons()
    except Exception:
        pass
    _retire_loaded_bgcache(close_panel=True)
    if os.path.isdir(p["target"]):
        shutil.rmtree(p["target"], ignore_errors=True)
        removed.append(p["target"])
    if os.path.isfile(p["mod"]):
        os.remove(p["mod"])
        removed.append(p["mod"])
    _forget_loaded_bgcache()
    message = "bgcache uninstalled: removed %s; %d shelf button(s). Backups in %s are kept." % (
        ", ".join(removed) or "nothing (it wasn't installed)", buttons, p["backups"])
    _tell(message, quiet)
    return message


def onMayaDroppedPythonFile(*args):
    _forget_self()
    install()
