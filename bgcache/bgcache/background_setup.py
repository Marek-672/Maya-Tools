"""Runs inside the background Maya while it starts (0.9.0b19): copied as
userSetup.py into the background Maya's own, clean settings folder
(scene.background_prefs), so Maya runs it before its main window is shown.

It keeps that window out of your way until bgcache's start command takes
over (worker._minimize_main marks the window "bgcacheStarted"). Until then,
every time Maya shows or restores its main window it is made see-through and
minimized again (it's up for a fraction of a second, unseen), and on Windows
the keyboard is handed back to the window you were in whenever this Maya
takes it (checked five times a second). Before b19
Maya opened full screen for a few seconds.

Tried and dropped: leaving it up and see-through (an unseen full-screen
window on top held the keyboard for 20 seconds), and acting only the first
time it's shown (Maya shows it more than once as it starts, and it came back
up full screen). If the start command never comes, it's left alone after two
minutes, solid, so a stuck Maya can be seen.

Only in the background Maya (BGCACHE_BACKGROUND is set); anywhere else it
does nothing. No Maya commands here: Qt only.
"""
import os


def _foreground():
    """Windows: the window you're working in right now (0 elsewhere)."""
    if os.name != "nt":
        return 0
    try:
        import ctypes
        return int(ctypes.windll.user32.GetForegroundWindow() or 0)
    except Exception as error:
        print("bgcache: can't tell which window you're in: %s" % error)
        return 0


def _give_back(hwnd):
    """Windows: if this Maya has the keyboard (any of its windows, the
    unseen helper ones too), hand it back to the window you were in."""
    if not hwnd or os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(pid))
        if pid.value == os.getpid() and user32.IsWindow(hwnd):
            user32.SetForegroundWindow(hwnd)
    except Exception as error:
        print("bgcache: keyboard not handed back: %s" % error)


def start_hidden():
    try:
        from PySide6 import QtCore, QtWidgets
    except ImportError:  # Maya 2024 and earlier
        from PySide2 import QtCore, QtWidgets
    app = QtWidgets.QApplication.instance()
    if app is None:
        return None
    watched = (QtCore.QEvent.Show, QtCore.QEvent.WindowStateChange, QtCore.QEvent.WindowActivate)

    class StartHidden(QtCore.QObject):
        active = True
        window = None
        yours = _foreground()

        def eventFilter(self, obj, event):
            if not self.active or event.type() not in watched:
                return False
            try:
                if not (obj.isWidgetType() and obj.isWindow() and obj.objectName() == "MayaWindow"):
                    return False
                self.window = obj
                if obj.property("bgcacheStarted"):
                    self.finish()
                elif event.type() == QtCore.QEvent.WindowActivate:
                    _give_back(self.yours)
                elif not obj.isMinimized():
                    obj.setWindowOpacity(0.0)             # unseen for the moment it's up
                    QtCore.QTimer.singleShot(0, self.down)
            except Exception as error:
                self.active = False
                print("bgcache: background window not hidden at start: %s" % error)
            return False

        def down(self):
            if self.active and self.window is not None and not self.window.isMinimized():
                self.window.showMinimized()

        def finish(self):
            self.active = False
            if self.window is not None:
                self.window.setWindowOpacity(1.0)

    keeper = StartHidden(app)
    app.installEventFilter(keeper)
    QtCore.QTimer.singleShot(120000, keeper.finish)
    if keeper.yours:                    # Windows: Maya takes the keyboard more than once as it starts
        keeper.watch = QtCore.QTimer(keeper)
        keeper.watch.timeout.connect(lambda: _give_back(keeper.yours) if keeper.active else keeper.watch.stop())
        keeper.watch.start(200)
    return keeper


if os.environ.get("BGCACHE_BACKGROUND") and os.environ.get("BGCACHE_SHOW_BACKGROUND") != "1":
    try:
        _bgcache_start_hidden = start_hidden()
    except Exception as error:
        print("bgcache: background window not hidden at start: %s" % error)
