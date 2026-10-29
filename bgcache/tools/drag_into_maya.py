"""Drag this file into a Maya viewport to install or change your bgcache version.

It does exactly what ./install does, from inside Maya, using the same folder:
the builds in releases/ next to this file, installed into your own
~/maya/<this Maya's version>/scripts/bgcache, with the copy you had moved to
scripts/.bgcache_backups first. So ./install --list / --version / --rollback
keep working, and nothing you had is ever deleted.

When you drop it you get:
    Install <newest>     the newest build in releases/ (the usual choice)
    Other version...     pick any build in releases/, e.g. 0.7.5
    Roll back            put back what you had before your last install
    Cancel
Going back to an older version, or reinstalling the same one, asks first.
It won't run while bgcache is running (press Stop first).
"""
import importlib.util
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "bgcache"


def _forget_self():
    """Since Maya 2022 a second drop of the same file runs the cached copy."""
    sys.modules.pop(os.path.splitext(os.path.basename(__file__))[0], None)


def _cli():
    """install_bgcache.py from this folder: the same code ./install runs."""
    spec = importlib.util.spec_from_file_location("bgcache_cli_installer", os.path.join(HERE, "install_bgcache.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _maya_root():
    """~/maya/<version> for this Maya (MAYA_APP_DIR respected, as ./install does)."""
    import maya.cmds as cmds
    user = os.path.normpath(cmds.internalVar(userAppDir=True))
    try:
        version = str(cmds.about(majorVersion=True))
    except Exception:
        version = re.match(r"\d+", str(cmds.about(version=True))).group(0)
    return os.path.join(user, version), user, version


def _running():
    controller = sys.modules.get(NAME + ".controller")
    try:
        return bool(controller and controller.get().running)
    except Exception:
        return False


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


def _forget_loaded_bgcache():
    """Make this Maya load the newly installed copy at the next shelf click."""
    for name in [m for m in sys.modules if m == NAME or m.startswith(NAME + ".")]:
        del sys.modules[name]


def _scripts_on_path(scripts):
    def add():
        if os.path.normcase(scripts) not in [os.path.normcase(p) for p in sys.path]:
            sys.path.insert(0, scripts)
    add()
    # Maya takes the first sys.path entry off after running a dropped file
    # (meaning its own folder); if that was this one, put it back afterwards.
    try:
        import maya.cmds as cmds
        cmds.evalDeferred(add, lowestPriority=True)
    except Exception:
        pass


def _module_copy_aside(cli, user, report):
    """A drag-and-drop module install (modules/bgcache) would compete with
    this one: move it to modules/.bgcache_backups."""
    modules = os.path.join(user, "modules")
    target, mod = os.path.join(modules, NAME), os.path.join(modules, NAME + ".mod")
    if not (os.path.isdir(target) or os.path.isfile(mod)):
        return
    backups = os.path.join(modules, ".bgcache_backups")
    os.makedirs(backups, exist_ok=True)
    if os.path.isdir(target):
        shutil.move(target, cli.backup_path(backups, "%s_module" % NAME))
    if os.path.isfile(mod):
        shutil.move(mod, cli.backup_path(backups, "%s_mod" % NAME))
    report.append("A second copy in %s was moved to %s, so only one bgcache is found." % (target, backups))


def _has_shelf_button():
    import maya.cmds as cmds
    import maya.mel as mel
    try:
        top = mel.eval("$bgcacheTmp = $gShelfTopLevel")
        for tab in cmds.tabLayout(top, query=True, childArray=True) or []:
            for button in cmds.shelfLayout(tab, query=True, childArray=True) or []:
                if cmds.objectTypeUI(button) == "shelfButton" and \
                        NAME in (cmds.shelfButton(button, query=True, command=True) or ""):
                    return True
    except Exception:
        pass
    return False


# ------------------------------------------------------------------ dialogs
def _ask(message, buttons, quiet, default):
    if quiet:
        return default
    import maya.cmds as cmds
    return cmds.confirmDialog(title="bgcache", message=message, button=buttons,
                              defaultButton=buttons[0], cancelButton=buttons[-1], dismissString=buttons[-1])


def _tell(message, quiet):
    print("bgcache: " + message.replace("\n", "\n    "))
    if not quiet:
        import maya.cmds as cmds
        cmds.confirmDialog(title="bgcache", message=message, button=["OK"])


def _pick_version(versions, installed, quiet):
    """Buttons for the builds in releases/, newest first (the 6 newest, plus
    the oldest so 0.7.5 is always there). Returns one or None."""
    if quiet:
        return None
    rows = list(reversed(versions))
    shown = rows[:6] + ([rows[-1]] if len(rows) > 6 else [])
    labels = [v + (" (installed)" if v == installed else "") for v in shown]
    answer = _ask("Which version? You have %s now.\n\nOlder builds stay in releases/ (./install --version <v> for any of them)."
                  % (installed or "none"), labels + ["Cancel"], False, "Cancel")
    return shown[labels.index(answer)] if answer in labels else None


# ------------------------------------------------------------------ the work
def run(quiet=False, choice=None, version=None):
    """The drop. `choice` ("newest" | "version" | "rollback") and `version`
    skip the dialogs (for scripts and tests). Returns the report text."""
    if _running():
        message = "bgcache is running in this Maya: press Stop first, then drag this file in again."
        _tell(message, quiet)
        return message
    cli = _cli()
    root, user, maya_version = _maya_root()
    target = os.path.join(root, "scripts", NAME)
    found = cli.releases()
    if not found:
        message = "No builds found in %s. This file must stay in the install_bgcache folder, next to releases/." % cli.RELEASES
        _tell(message, quiet)
        return message
    versions = sorted(found, key=cli.version_key)
    newest = versions[-1]
    installed = cli.version_of(target)
    can_roll_back = bool(cli.backups_of(root))

    if choice is None:
        buttons = ["Install %s" % newest, "Other version..."] + (["Roll back"] if can_roll_back else []) + ["Cancel"]
        answer = _ask("Maya %s\n\nInstalled now:  %s\nNewest build:  %s\n\nWhat would you like to do?"
                      % (maya_version, installed or "none", newest), buttons, quiet, buttons[0])
        choice = {buttons[0]: "newest", "Other version...": "version", "Roll back": "rollback"}.get(answer)
    if choice is None:
        return "cancelled"

    report = []
    if choice == "rollback":
        previous = cli.version_of(cli.backups_of(root)[-1]) if can_roll_back else None
        if not previous:
            message = "Nothing to roll back to: no earlier install was backed up."
            _tell(message, quiet)
            return message
        if _ask("Go back from %s to %s (what you had before your last install)?" % (installed, previous),
                ["Roll back", "Cancel"], quiet, "Roll back") != "Roll back":
            return "cancelled"
        _module_copy_aside(cli, user, report)
        old, new = cli.rollback(root, log=report.append)
    else:
        if choice == "version":
            version = version or _pick_version(versions, installed, quiet)
            if not version:
                return "cancelled"
        else:
            version = newest
        if version not in found:
            message = "Version %s isn't in releases/. There: %s" % (version, ", ".join(versions))
            _tell(message, quiet)
            return message
        if installed == version:
            if _ask("bgcache %s is already installed. Install it again?" % version,
                    ["Install again", "Cancel"], quiet, "Install again") != "Install again":
                return "cancelled"
        elif installed and installed in found and cli.version_key(version) < cli.version_key(installed):
            if _ask("This goes BACK from %s to the older %s.\n\nYour drawings stay where they are, and %s "
                    "is kept so you can return to it (drop this file again and pick it, or Roll back)."
                    % (installed, version, installed), ["Go back to " + version, "Cancel"], quiet,
                    "Go back to " + version) != "Go back to " + version:
                return "cancelled"
        _module_copy_aside(cli, user, report)
        old, new, _icons = cli.install_zip(found[version], root, log=report.append)

    scripts = os.path.join(root, "scripts")
    _scripts_on_path(scripts)
    _retire_loaded_bgcache(close_panel=True)   # b12: no Maya panel any more, all in the player
    _forget_loaded_bgcache()
    shelf_note = None
    if not _has_shelf_button():
        try:
            import bgcache.install
            shelf_note = "Shelf button added to shelf %r." % bgcache.install.shelf()
        except Exception as error:
            shelf_note = "Add the shelf button by running:  import bgcache.install; bgcache.install.shelf()  (%s)" % error
    lines = ["bgcache %s is installed for Maya %s%s." % (new, maya_version, (" (was %s)" % old) if old else ""),
             "No restart needed: click the bgcache shelf button to start (the player opens)."]
    if shelf_note:
        lines.append(shelf_note)
    lines.append("")
    lines += report
    message = "\n".join(lines).rstrip()
    _tell(message, quiet)
    return message


def onMayaDroppedPythonFile(*args):
    _forget_self()
    run()
