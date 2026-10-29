"""One-step shelf setup for bgcache. In Maya's Script Editor (Python):

    import bgcache.install; bgcache.install.shelf()

Copies the icons into your Maya prefs and adds a bgcache button to the current
shelf tab (or the tab you name). Run it again any time: it updates the existing
button instead of adding a second one.
"""
import os
import shutil

import maya.cmds as cmds
import maya.mel as mel

HERE = os.path.dirname(os.path.abspath(__file__))
COMMAND = "import bgcache.controller as bgc\nbgc.shelf_click()"
# The button's right-click menu (Python commands), kept in the shelf file.
MENU = [("Stop bgcache", "import bgcache.controller as bgc; bgc.shelf_stop()"),
        ("Reopen player", "import bgcache.controller as bgc; bgc.shelf_reopen()"),
        ("Restart bgcache", "import bgcache.controller as bgc; bgc.shelf_restart()"),
        ("Self-test", "import bgcache.controller as bgc; bgc.shelf_selftest()")]
TIP = "bgcache: click to start (or bring the player to the front). Right-click: Stop, Restart, Self-test"


def _menu_flags():
    return {"menuItem": [list(m) for m in MENU], "menuItemPython": list(range(len(MENU)))}


def _copy_icons():
    src = os.path.join(HERE, "icons")
    dst = os.path.join(cmds.internalVar(userPrefDir=True), "icons")
    existed = os.path.isdir(dst)
    os.makedirs(dst, exist_ok=True)
    for name in os.listdir(src):
        if name.endswith(".png"):
            shutil.copy2(os.path.join(src, name), os.path.join(dst, name))
    # Maya only searches folders that existed at startup by name; otherwise use
    # the full path (works now, but without the high-DPI versions until restart).
    return "bgcache.png" if existed else os.path.join(dst, "bgcache.png")


def _bgcache_buttons():
    """(shelf tab, button) for every bgcache button on any shelf."""
    top = mel.eval("$bgcacheTop = $gShelfTopLevel")
    out = []
    for tab in cmds.tabLayout(top, query=True, childArray=True) or []:
        for button in cmds.shelfLayout(tab, query=True, childArray=True) or []:
            try:
                if cmds.objectTypeUI(button) != "shelfButton":
                    continue
            except RuntimeError:
                continue
            if "bgcache.controller" in (cmds.shelfButton(button, query=True, command=True) or ""):
                out.append((tab, button))
    return out


def shelf(tab=None):
    """Add the bgcache button to the current shelf tab (or `tab`), or update
    the one that's already on any shelf."""
    image = _copy_icons()
    top = mel.eval("$bgcacheTop = $gShelfTopLevel")
    existing = _bgcache_buttons()
    if existing and tab is None:
        for where, button in existing:
            _button(dict(edit=True, image=image, label="bgcache", annotation=TIP,
                         imageOverlayLabel="", command=COMMAND, sourceType="python"), button)
            print("bgcache: updated the existing button on shelf %r" % where)
        mel.eval("saveAllShelves $gShelfTopLevel")
        return existing[0][0]
    if tab is None:
        tab = cmds.tabLayout(top, query=True, selectTab=True)
    elif not cmds.shelfLayout(tab, exists=True):
        mel.eval('addNewShelfTab "%s"' % tab)
    _button(dict(parent=tab, image=image, label="bgcache", annotation=TIP,
                 imageOverlayLabel="", command=COMMAND, sourceType="python"))
    print("bgcache: added a button to shelf %r" % tab)
    mel.eval("saveAllShelves $gShelfTopLevel")
    return tab


def _button(flags, button=None):
    """Make or update the shelf button, with its right-click menu (a Maya
    without menu items on shelf buttons: just the click)."""
    args = (button,) if button else ()
    try:
        return cmds.shelfButton(*args, **dict(flags, **_menu_flags()))
    except (TypeError, RuntimeError) as error:
        print("bgcache: shelf button without its right-click menu (%s)" % error)
        return cmds.shelfButton(*args, **flags)


def remove_shelf_buttons():
    """Remove every bgcache button from the shelves. Returns how many."""
    found = _bgcache_buttons()
    for _tab, button in found:
        cmds.deleteUI(button)
    if found:
        mel.eval("saveAllShelves $gShelfTopLevel")
    return len(found)
