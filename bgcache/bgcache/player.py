"""Standalone flipbook for bgcache, run with mayapy as its own process so it
never stutters when your animation Maya is busy:

    mayapy -m bgcache.player <session_dir> [controller_pid]

Layout, top to bottom: toolbar (camera dropdown, status, toggles), the
continuity shot strip (only with the continuity add-on), picture (camera and
sound bottom-left, frame bottom-right), cache bar, playback buttons.

Cameras: nothing renders until you check a camera in the dropdown. Checked
cameras stay cached; the viewed one renders first after an edit.

Continuity (add-on, bgcache/continuity/): neighbour shots play before and
after yours as one reel; see continuity/ui.py.

Time sync: scrubbing, stepping or pausing on your shot moves Maya there;
changing frames in Maya moves the paused player.

Sound: Scrub plays each frame's sound while you drag or step. If sound lands
early or late (remote workstations add delay), open the Sound button's menu ->
Sync test, and nudge with [ (earlier) and ] (later) until the click lands on
the white flash. The offset is remembered.

Keys: Space play/pause, Left/Right or , . step, Home/End, L loop, M mute,
C show/hide shot strip (add-on), T always on top, [ ] sound offset. Sync and live/reference have
buttons only (S and R are Set Key and Scale in Maya, easy to press with the player focused).
Click or drag the picture or the bar to scrub.
"""
import collections
import os
import sys
import time

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:  # Maya 2024 and earlier (PySide2)
    from PySide2 import QtCore, QtGui, QtWidgets

from bgcache import common, __version__
from bgcache.widgets import FitLabel, FlowLayout, _checkbox_style, _icon, _tool

Qt = QtCore.Qt
_QAction = getattr(QtGui, "QAction", None) or QtWidgets.QAction     # QtGui in PySide6, QtWidgets in PySide2
BAR_H = 12
LRU_SIZE = 64
GREEN, RED = QtGui.QColor(60, 140, 90), QtGui.QColor(180, 55, 55)
STAGED = QtGui.QColor(66, 128, 186)      # staged neighbour shots: blue, as on their cards
TICK, TICK_EDGE = QtGui.QColor(224, 138, 69), QtGui.QColor(11, 11, 11)
FOCUS = QtGui.QColor(245, 214, 110)      # focus range handles (b18)
TAB_W, TAB_H = 11, 10                    # b4: the handles' tabs above the bar   # drawn-frame marks on the bar

STYLE = """
QWidget#bgcPlayer { background: #121212; }
QWidget#toolbar, QWidget#transport { background: #232323; }
QLabel { color: #cfcfcf; font-size: 12px; }
QToolButton { color: #ebebeb; background: #343434; border: 1px solid #4a4a4a;
              border-radius: 3px; padding: 3px 9px; font-size: 12px; }
QToolButton:checked { background: #3d6a8f; border-color: #8fc0e8; color: #ffffff; }
QToolButton#menuWord { background: transparent; border: 1px solid transparent; padding: 3px 7px; }
QToolButton#menuWord:hover, QToolButton#menuWord:pressed { background: #3a3a3a; border-color: #4a4a4a; }
QMenu::item:disabled { color: #8a8d93; }
QToolButton:disabled { color: #6a6a6a; }
QToolButton::menu-indicator { image: none; }
QToolButton#drawButton:checked { background: #b8662a; border-color: #e08a45; color: #fff4e8; font-weight: bold; }
QToolButton#pauseButton:checked { background: #7a5a1e; border-color: #d9a441; color: #fff4dc; font-weight: bold; }
QPushButton { color: #cfcfcf; background: #343434; border: 1px solid #4a4a4a;
              border-radius: 3px; font-size: 11px; padding: 2px 6px; }
QMenu { background: #2c2c2c; color: #ebebeb; border: 1px solid #555; }
QMenu::item:selected { background: #3d5a73; }
QCheckBox { color: #ebebeb; font-size: 13px; }
QScrollArea { border: none; background: #1b1b1b; }
QScrollBar:horizontal { background: #2b2b2b; height: 12px; margin: 0; border: none; }
QScrollBar:vertical { background: #2b2b2b; width: 12px; margin: 0; border: none; }
QScrollBar::handle:horizontal { background: #5d5d5d; min-width: 30px; border-radius: 3px; margin: 2px; }
QScrollBar::handle:vertical { background: #5d5d5d; min-height: 30px; border-radius: 3px; margin: 2px; }
QScrollBar::handle:hover { background: #727272; }
QScrollBar::handle:pressed { background: #8a8a8a; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; border: none; background: none; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
"""


def _separator(row):
    """A thin vertical line between groups of buttons."""
    sep = QtWidgets.QFrame()
    sep.setFixedSize(1, 20)
    sep.setStyleSheet("background: #444")
    row.addWidget(sep)


def _check_item(menu, text, on, slot, tip=""):
    """A tickable menu item."""
    act = menu.addAction(text)
    act.setCheckable(True)
    act.setChecked(bool(on))
    if tip:
        act.setToolTip(tip)
    act.triggered.connect(slot)
    return act


def _menu_section(menu, text):
    """A greyed heading inside a menu (FOCUS RANGE, SOUND)."""
    head = menu.addAction(text.upper())
    head.setEnabled(False)


# --------------------------------------------------------------------------
# Picture + cache bar
# --------------------------------------------------------------------------
def _shift(event):
    """Shift held (eraser: remove whole strokes). False if unknown."""
    try:
        return bool(event.modifiers() & Qt.ShiftModifier)
    except Exception:  # event without modifiers: Shift not held
        return False


class Canvas(QtWidgets.QWidget):
    def __init__(self, player):
        super(Canvas, self).__init__(player)
        self.player = player
        self.setMinimumSize(160, 90)          # small, so the window can get narrow (Draw strip open too)
        self.setMouseTracking(True)           # b4: the focus handles light up under the pointer

    def paintEvent(self, event):
        self.player.paint(self)

    def mousePressEvent(self, event):
        if self.player.canvas_press(self, event):
            return
        if event.button() == Qt.LeftButton:
            self.player.dragging = True
            self.player.scrub(self, event)

    def mouseMoveEvent(self, event):
        if self.player.canvas_move(self, event):
            return
        if event.buttons() & Qt.LeftButton:
            self.player.scrub(self, event)

    def mouseDoubleClickEvent(self, event):
        # b18: double-click the cache bar: cache the whole shot again
        if event.button() == Qt.LeftButton and \
                self.player._point(event).y() >= self.height() - BAR_H - 4:
            self.player.set_focus(clear=True)
            self.player._flash_message("Caching the whole shot", 2.0)
            return
        super(Canvas, self).mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event):
        if self.player.canvas_release(self, event):
            return
        if event.button() == Qt.LeftButton:
            self.player.dragging = False
            if not self.player.test_mode:
                self.player.send_time()

    def tabletEvent(self, event):
        self.player.canvas_tablet(self, event)

    def leaveEvent(self, event):
        drawer = getattr(self.player, "drawer", None)
        if drawer is not None:
            drawer.hover_at(None)            # hide the size circle










# --------------------------------------------------------------------------
# Continuity add-on (bgcache/continuity/), if installed
# --------------------------------------------------------------------------
class NoContinuity(object):
    """The player without the continuity add-on: your shot only."""
    has_continuity = False

    def _init_continuity(self):
        self.shot_ids = self.live_shot = None
        self.staged = {"before": [], "after": []}
        self.dept_override, self.infos, self.prepared = {}, {}, {}
        self.live_ref = self.live_ref_last = self.live_ref_ready = self.plane_mode = None
        self.continuity_on = self.browser_open = False
        self.shots = []

    def _continuity_buttons(self):
        return []

    def _continuity_widget(self, lay):
        pass

    def _continuity_ready(self):
        pass

    def _continuity_start(self):
        pass

    def _continuity_height(self):
        return 0

    def _continuity_prefs(self):
        pass

    def _footage_label(self, info):
        return ""

    def toggle_browser(self):
        pass

    def toggle_live_ref(self):
        pass

    def _scroll_to_live(self):
        pass

    def open_setup(self):
        pass


def _continuity_part():
    """The add-on's Continuity class, or NoContinuity if it isn't installed
    (or can't load: then the player still works, without the strip)."""
    try:
        from bgcache.continuity.ui import Continuity
        return Continuity
    except ImportError as error:
        if not (getattr(error, "name", None) or "").startswith("bgcache.continuity"):
            print("bgcache: continuity add-on not loaded (%s)" % error)
        return NoContinuity


# --------------------------------------------------------------------------
# Player
# --------------------------------------------------------------------------
class ReportDialog(QtWidgets.QDialog):
    """Help > Report a problem: what happened, an optional email, what goes
    in the report, Hide names, then Send (if switched on) or Save report."""

    def __init__(self, parent, items, can_send):
        super(ReportDialog, self).__init__(parent)
        self.setWindowTitle("Report a problem")
        self.choice = None
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(QtWidgets.QLabel("What happened? What were you doing just before?"))
        self.text = QtWidgets.QPlainTextEdit()
        self.text.setMinimumSize(420, 110)
        lay.addWidget(self.text)
        self.mail = QtWidgets.QLineEdit()
        self.mail.setPlaceholderText("Your email, if you'd like an answer (optional)")
        lay.addWidget(self.mail)
        lay.addWidget(QtWidgets.QLabel("The report holds:"))
        listing = QtWidgets.QLabel("\n".join(["   \u2022 what you wrote above"] +
                                             ["   \u2022 %s" % name for name, _p, _t in items]))
        listing.setToolTip("\n".join(path for _n, path, _t in items if path))
        lay.addWidget(listing)
        self.b_hide = QtWidgets.QCheckBox("Hide names (show, sequence, shot, scene and your user name)")
        self.b_hide.setChecked(True)
        lay.addWidget(self.b_hide)
        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        save = QtWidgets.QPushButton("Save report...")
        save.clicked.connect(lambda: self._done("save"))
        row.addWidget(save)
        if can_send:
            send = QtWidgets.QPushButton("Send")
            send.setDefault(True)
            send.clicked.connect(lambda: self._done("send"))
            row.addWidget(send)
        cancel = QtWidgets.QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        lay.addLayout(row)

    def _done(self, choice):
        self.choice = choice
        self.accept()

    def what(self):
        return self.text.toPlainText()

    def email(self):
        return self.mail.text()

    def hide_names(self):
        return self.b_hide.isChecked()


class Player(_continuity_part(), QtWidgets.QWidget):
    def __init__(self, session, controller_pid=None):
        """The player for one session (session folder name); controller_pid:
        your Maya's process id (the player quits when it's gone)."""
        super(Player, self).__init__()
        from bgcache import audio
        self.audio_mod = audio
        self.session = session
        self.p = common.paths(session)
        self.controller_pid = controller_pid
        self.cfg = common.read_json(self.p["config"]) or {}
        self.start = int(self.cfg.get("start", 1))
        self.end = int(self.cfg.get("end", 1))
        self.fps = float(self.cfg.get("fps") or 24.0)
        self.height_px = int(self.cfg.get("height") or 540)

        # live frames per camera (from the background Maya)
        self.data = collections.defaultdict(dict)
        self.loaded = collections.defaultdict(dict)
        self.dirty = {}
        self.state = "starting background Maya..."
        want = common.read_json(self.p["cameras"]) or {}
        self.checked = list(want.get("checked") or [])
        self.view = want.get("view")

        self._init_playback()
        self._load_settings()
        self.test_mode = False
        self._play_token = None
        self._flash, self._flash_until = "", 0.0
        self._reload_asked = None      # (time, config rev, reloads done) while a Reload scene is on its way
        self._reloads_done = None      # the background Maya's count of finished reloads
        self._cfg_mtime = 0.0
        self.segments = []
        self.total = 1
        self._init_continuity()        # continuity add-on (or NoContinuity)

        # sound
        self.sound = audio.Sound()
        self.live_pcm, self.live_status = None, "no sound in scene"
        self.rate, self.channels = 48000, 2
        self._init_live_sound()

        self.drawer = self.drawui.Drawer(self)
        self._build_ui()
        self._rebuild_reel()
        self._move_to_live(self.start)
        self._continuity_start()

        self._init_health()
        self._start_timers()
        if not self.sync:
            self.send_time()   # tell Maya's side sync is off (doesn't move Maya)
        self._poll()

    def _init_playback(self):
        """Playback state: frame cache, position, direction, loop, input."""
        self.lru = collections.OrderedDict()
        self.pos = 0
        self.playing = 0          # 1 forward, -1 backwards, 0 stopped
        self.loop = True
        self.clock = QtCore.QElapsedTimer()
        self.origin = 0
        self.loops = 0
        self.shown = collections.deque(maxlen=48)
        self.dragging = False
        self._maya_ts = 0.0
        from bgcache import drawui
        self.drawui = drawui
        self.keymap = drawui.KeyMap(self.cfg.get("hotkeys"))
        self.scrub_held = False
        self.input_mode = None       # "scrub", "draw" or "tablet" while a button is down
        self.last_target = None

    def _load_settings(self):
        """Your saved player settings (sync, scrub sound, sound offset)."""
        self.prefs = common.load_prefs()
        self.sync = bool(self.prefs.get("sync", True))   # your last choice
        self.scrub_on = bool(self.prefs.get("scrub", True))
        if self.prefs.get("audio_offset_v", 1) < 2:
            # Offsets saved before 0.5.5 were compensating for a wrong automatic
            # shift that's now gone, so start again from zero once.
            self.prefs["audio_offset"] = 0.0
            self.prefs["audio_offset_v"] = 2
            common.save_prefs(self.prefs)
        self.audio_offset = float(self.prefs.get("audio_offset", 0.0))  # frames; + = sound earlier

    def _init_health(self):
        """Health: the background Maya's warnings, graphics-memory errors in
        its log, and caching that has stopped moving (see _health_banner)."""
        self._warning = ""
        self._rescue_seen = 0.0
        self.focus_range = None     # b18: (first, last) to cache; None = the whole shot
        self._handle_drag = None    # "in" / "out" while a focus handle is dragged
        self._gpu = None            # GPU deformers in the background Maya (its status)
        self._worker_pid = None
        self._gpu_trouble_t = None
        self._log_pos = 0
        self._log_check_t = 0.0
        self._progress_key = None
        self._progress_t = time.time()

    def _start_timers(self):
        """Playback tick (4 ms), status poll (250 ms), new-frames check
        (40 ms) and the progress spinner (50 ms)."""
        self.tick_timer = QtCore.QTimer(self)
        self.tick_timer.setTimerType(Qt.PreciseTimer)
        self.tick_timer.timeout.connect(self._tick)
        self.tick_timer.start(4)
        self.poll_timer = QtCore.QTimer(self)
        self.poll_timer.timeout.connect(self._poll)
        self.poll_timer.start(250)
        # New frames: a cheap look at status.json's timestamp every 40 ms, and a
        # full read only when the background Maya has rewritten it.
        self._status_mtime = None
        self.frames_timer = QtCore.QTimer(self)
        self.frames_timer.timeout.connect(self._poll_if_changed)
        self.frames_timer.start(40)
        self.spin_timer = QtCore.QTimer(self)
        self.spin_timer.timeout.connect(self._spin)
        self.spin_timer.start(50)

    # ================================================================ UI
    def _build_ui(self):
        """The window, top to bottom: toolbar, continuity strip (add-on),
        the picture with the drawing strip beside it, the playback bar."""
        self.setObjectName("bgcPlayer")
        self.setStyleSheet(STYLE)
        self.setWindowTitle("bgcache %s player" % __version__)
        self.setFocusPolicy(Qt.StrongFocus)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._build_toolbar())
        self._continuity_widget(lay)         # continuity shot strip (add-on)
        self._build_picture(lay)
        lay.addWidget(self._build_transport())
        self._continuity_ready()
        self.resize(1180, self._window_height())
        self._update_cam_button()

    def _build_toolbar(self):
        """The toolbar (b14, after the toolbar/menu guidelines): menus first,
        in the usual order (bgcache like File, View, Help), then what you see
        (camera, Draw), the three cache buttons together, Pause. Loop, Sound
        and Sync sit with the playback buttons at the bottom. One row when it
        fits; wraps onto a second row in a narrow window."""
        bar = QtWidgets.QWidget()
        bar.setObjectName("toolbar")
        bar.setMinimumHeight(40)
        row = FlowLayout(bar, spacing=6, margins=(6, 4, 10, 4))
        self._build_menus(row)
        _separator(row)
        self._build_view_buttons(row)
        _separator(row)
        self._build_cache_buttons(row)
        row.addStretch(1)
        self._continuity_buttons()           # b14: nothing on the toolbar (the switch is on the strip)
        self.status_label = FitLabel()
        self._build_playback_toggles()
        return bar

    def _menu_word(self, row, text, tip):
        """A menu shown as a plain word on the toolbar (bgcache, View, Help)."""
        button = _tool(text + " \u25be", tip=tip)
        button.setObjectName("menuWord")
        button.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        menu = QtWidgets.QMenu(self)
        menu.setToolTipsVisible(True)
        button.setMenu(menu)
        row.addWidget(button)
        return button, menu

    def _build_menus(self, row):
        """bgcache, View and Help, in the usual order (bgcache is like File)."""
        # -- bgcache (like File): what to send, restart, stop
        self.b_app, app_menu = self._menu_word(row, "bgcache", "Push selected, restart, stop")
        self.b_push = app_menu.addAction("Push selected")
        self.b_push.setToolTip("Send the unkeyed values of what's selected in your Maya")
        self.b_push.triggered.connect(lambda: self._maya_cmd("push_selected", "Push selected sent to your Maya"))
        if self.has_continuity:
            app_menu.addAction("Set up continuity...", self.open_setup)
        app_menu.addSeparator()
        app_menu.addAction("Restart bgcache", lambda: self._maya_cmd(
            "restart", "Restarting: the player reopens in a moment"))
        app_menu.addAction("Stop bgcache", self.stop_bgcache)

        # -- View: the picture, and sound settings
        self.b_view, view_menu = self._menu_word(row, "View", "Film gate, drawings, keep on top, sound settings")
        self.gate_mask = bool(self.prefs.get("gate_mask", True))
        self.b_gate = _check_item(view_menu, "Film gate", self.gate_mask, self._set_gate_mask,
                                  "Darken what's outside the camera's film gate (out of shot)")
        self.b_drawings = _check_item(view_menu, "Show drawings", self.drawer.show, self._set_show_drawings)
        self.b_top = _check_item(view_menu, "Keep on top (T)", False, lambda c: self._set_on_top(c))
        view_menu.addSeparator()
        _menu_section(view_menu, "Focus range")
        clear = view_menu.addAction("Clear focus range (cache the whole shot)", lambda: self.set_focus(clear=True))
        clear.setToolTip("I / O set the start / end at the frame you're on; drag the handles on the cache bar; "
                         "double-click the bar to clear")
        view_menu.addSeparator()
        _menu_section(view_menu, "Sound")
        self.b_scrub = _check_item(view_menu, "Sound while scrubbing", self.scrub_on,
                                   lambda c: self._set_scrub(c), "Sound while scrubbing and stepping")
        view_menu.addAction("Sync test", self.toggle_sync_test)
        view_menu.addAction("Reset sound offset", lambda: self._set_offset(0.0))

        # -- Help: checks, updates, version
        self.b_help, help_menu = self._menu_word(row, "Help", "Self-test, updates, version")
        help_menu.addAction("Self-test", lambda: self._maya_cmd(
            "selftest", "Self-test running: the report prints in your Maya's Script Editor in about a minute"))
        help_menu.addAction("Report a problem...", self.report_problem)
        self.help_menu = help_menu
        self._update_item = help_menu.addAction("Check for updates", self.check_for_update)
        self._update_item.setVisible(bool(self._update_source()))
        self._update_lines = []        # what the last check found, shown under it
        self._update_sep = help_menu.addSeparator()
        about = help_menu.addAction("About bgcache %s" % __version__)
        about.setEnabled(False)

    def _build_view_buttons(self, row):
        """What you see: the camera menu and Draw."""
        self.cam_button = _tool("no camera", tip="Tick cameras to cache them; click a name to view it")
        self.cam_button.setMinimumWidth(120)
        self.cam_button.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.cam_menu = QtWidgets.QMenu(self)
        self.cam_menu.aboutToShow.connect(self._fill_camera_menu)
        self.cam_button.setMenu(self.cam_menu)
        row.addWidget(self.cam_button)
        self.b_draw = _tool("Draw", True, "Draw over the picture (D)")
        self.b_draw.setIcon(self.drawui.icon("pen"))
        self.b_draw.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.b_draw.setObjectName("drawButton")
        self.b_draw.clicked.connect(lambda c: self.drawer.set_on(c))
        row.addWidget(self.b_draw)

    def _build_cache_buttons(self, row):
        """Refresh, Reload scene and Re-render all together, then Pause."""
        self.b_refresh = _tool("Refresh", tip="Send your viewport settings, hidden/shown objects, display "
                                              "layers, image planes and GPU Override from your Maya, and re-render")
        self.b_refresh.clicked.connect(lambda: self._maya_cmd("refresh", "Refresh sent to your Maya"))
        self.b_reload = _tool("Reload scene", tip="Copy your scene to the background Maya again: after adding "
                                                  "characters, props, references or cameras, or changing the "
                                                  "frame range or sound. Takes about as long as Start.")
        self.b_reload.clicked.connect(self.reload_scene)
        self.b_rerender = _tool("Re-render all", tip="Redo every frame of the cache (if anything looks out of date)")
        self.b_rerender.clicked.connect(lambda: self._maya_cmd("rerender", "Re-rendering all frames"))
        for b in (self.b_refresh, self.b_reload, self.b_rerender):
            row.addWidget(b)
        self.b_pause = _tool("Pause", tip="Pause re-rendering: your edits keep coming in and changed frames "
                                          "stay red. Resume starts again from the frame you're on.")
        self.b_pause.setObjectName("pauseButton")
        self.b_pause.setCheckable(True)
        self.b_pause.clicked.connect(self.set_paused)
        row.addWidget(self.b_pause)

    def _build_playback_toggles(self):
        """Loop, Sound and Sync: built with the toolbar, placed on the
        playback bar (_build_transport)."""
        self.b_loop = _tool("Loop", True, "Loop (L)")
        self.b_sound = _tool("Sound", True, "Sound on/off (M). Sound settings: View menu")
        self.b_sync = _tool("Sync", True, "Time sync with Maya. Off shows SYNC OFF on the picture. "
                                         "(No single-letter key: S is Set Key in Maya.)")
        self.b_loop.setChecked(self.loop)
        self.b_sound.setChecked(True)
        self.b_sync.setChecked(self.sync)
        self.b_loop.clicked.connect(lambda c: self._set_loop(c))
        self.b_sound.clicked.connect(lambda c: self._set_mute(not c))
        self.b_sync.clicked.connect(lambda c: self._set_sync(c))

    def _build_picture(self, lay):
        """The picture and cache bar, with the drawing strip beside it (Draw mode)."""
        middle = QtWidgets.QHBoxLayout()
        middle.setContentsMargins(0, 0, 0, 0)
        middle.setSpacing(0)
        self.canvas = Canvas(self)
        self.canvas.setAttribute(Qt.WA_TabletTracking, False)
        middle.addWidget(self.canvas, 1)
        self.draw_panel = self.drawui.DrawPanel(self.drawer, self.keymap)
        middle.addWidget(self.draw_panel)
        lay.addLayout(middle, 1)

    def _build_transport(self):
        """The playback bar: playback buttons, Loop/Sound/Sync, status, range."""
        tr = QtWidgets.QWidget()
        tr.setObjectName("transport")
        tr.setFixedHeight(40)
        row = QtWidgets.QHBoxLayout(tr)
        row.setContentsMargins(10, 4, 10, 4)
        row.setSpacing(2)
        km = self.keymap.label
        specs = [("start", "Go to start (%s)" % km("start"), lambda: self._jump(0)),
                 ("prev_frame", "Step back one frame (%s)" % km("prev_frame"), lambda: self._step(-1)),
                 ("prev_key", "Step back one key, Maya selection (%s)" % km("prev_key"), lambda: self.send_cmd("prev_key")),
                 ("play_back", "Play backwards", lambda: self.toggle_play(-1)),
                 ("play", "Play forwards (%s, Space)" % km("play"), lambda: self.toggle_play(1)),
                 ("next_key", "Step forward one key, Maya selection (%s)" % km("next_key"), lambda: self.send_cmd("next_key")),
                 ("next_frame", "Step forward one frame (%s)" % km("next_frame"), lambda: self._step(1)),
                 ("end", "Go to end (%s)" % km("end"), lambda: self._jump(self.total - 1))]
        self.transport = {}
        for kind, tip, fn in specs:
            b = _tool(icon=kind, tip=tip)
            b.clicked.connect(fn)
            row.addWidget(b)
            self.transport[kind] = b
        row.addSpacing(8)
        _separator(row)
        row.addSpacing(8)
        for b in (self.b_loop, self.b_sound, self.b_sync):
            row.addWidget(b)
        row.addSpacing(12)
        row.addWidget(self.status_label, 2)
        row.addSpacing(12)
        self.range_label = FitLabel(elide=Qt.ElideMiddle)
        self.range_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addWidget(self.range_label, 1)
        return tr

    # ---------------------------------------------------------------- updates
    # 0.9.0b2: only when you ask (Help > Check for updates). Nothing checks or
    # installs by itself, and there's no Update button: the answer shows in the
    # Help menu. Studio builds look in the profile's releases folder, others
    # on GitHub (bgcache's only network use, and only on that click).
    def _update_source(self):
        cfg = self.cfg or {}
        if cfg.get("releases_folder"):
            return "folder"
        if cfg.get("github_releases"):
            return "github"
        return None

    def check_for_update(self):
        source = self._update_source()
        if not source:
            return None
        from bgcache import update
        if source == "folder":
            self._update_checked(update.check_folder(self.cfg["releases_folder"], __version__))
            return self._update_result
        from bgcache import system
        edition = "full" if self.has_continuity else "simple"
        self._show_update_lines([("Checking for updates...", None)])
        self._run_in_background(lambda: update.check_github(self.cfg["github_releases"], __version__,
                                                            system.NAME, edition), self._update_checked)
        return None

    def _run_in_background(self, work, done):
        """work() in a thread (a network call must not freeze the player),
        then done(result) back here."""
        import threading
        box = {}

        def run():
            try:
                box["result"] = work()
            except Exception as error:       # reported as the check's answer, never raised
                box["result"] = {"state": "error", "message": str(error)}
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        timer = QtCore.QTimer(self)

        def poll():
            if not thread.is_alive():
                timer.stop()
                done(box.get("result") or {"state": "error", "message": "no answer"})
        timer.timeout.connect(poll)
        timer.start(50)

    def _update_checked(self, result):
        self._update_result = result
        state = result.get("state")
        if state == "newer":
            lines = [("Latest: %s (you have %s)" % (result["version"], __version__), None)]
            if result.get("notes"):
                lines.append(("What's new in %s" % result["version"], self.show_update_notes))
            lines.append(("Update to %s and restart" % result["version"], self.update_and_restart))
        elif state == "latest":
            lines = [("You have the latest (%s)" % __version__, None)]
        else:
            lines = [("Couldn't check: %s" % result.get("message", "unknown error"), None)]
            if result.get("page"):
                lines.append(("Open the download page", lambda: self._open_url(result["page"])))
        self._show_update_lines(lines)
        QtCore.QTimer.singleShot(0, self.b_help.showMenu)     # show the answer where you asked

    def _show_update_lines(self, lines):
        """Replace the lines under Check for updates: (text, slot); no slot = a note."""
        for act in self._update_lines:
            self.help_menu.removeAction(act)
        self._update_lines = []
        for text, slot in lines:
            act = _QAction("    " + text, self.help_menu)
            if slot is None:
                act.setEnabled(False)
            else:
                act.triggered.connect(lambda checked=False, fn=slot: fn())
            self.help_menu.insertAction(self._update_sep, act)
            self._update_lines.append(act)

    # ---------------------------------------------------------------- reports
    def report_problem(self):
        """Help > Report a problem: what you write, plus the logs, in one zip.
        You see the list first. Send only when the profile has reports_url."""
        from bgcache import report
        edition = "full" if self.has_continuity else "simple"
        items = report.gather(self.session, self.cfg, __version__, edition)
        dialog = ReportDialog(self, items, bool((self.cfg or {}).get("reports_url")))
        (getattr(dialog, "exec", None) or dialog.exec_)()
        if not dialog.choice:
            return None
        names = report.names_to_hide(self.cfg) if dialog.hide_names() else None
        data = report.build(items, dialog.what(), dialog.email(), names)
        name = report.file_name(__version__)
        if dialog.choice == "send":
            self._flash_message("Sending the report...")
            self._run_in_background(
                lambda: dict(zip(("ok", "message"), report.send(self.cfg["reports_url"], data, name, __version__))),
                self._report_sent)
            return "send"
        start = os.path.join((self.cfg or {}).get("reports_folder") or os.path.expanduser("~"), name)
        path = QtWidgets.QFileDialog.getSaveFileName(self, "Save report", start, "Zip (*.zip)")[0]
        if path:
            report.save(data, path)
            self._flash_message("Report saved: %s" % os.path.basename(path))
        return path

    def _report_sent(self, result):
        self._flash_message(result.get("message") or "Couldn't send the report")
        if not result.get("ok"):
            print("bgcache player: report %s (use Help > Report a problem > Save report...)" % result.get("message"))

    def _open_url(self, url):
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))

    def show_update_notes(self):
        result = getattr(self, "_update_result", None) or {}
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle("What's new in bgcache %s" % result.get("version", ""))
        box.setText(result.get("notes") or "")
        if hasattr(Qt, "MarkdownText"):            # the release notes are Markdown (Qt 5.14+)
            box.setTextFormat(Qt.MarkdownText)
        go = box.addButton("Update and restart", QtWidgets.QMessageBox.AcceptRole)
        box.addButton("Close", QtWidgets.QMessageBox.RejectRole)
        box.exec_() if hasattr(box, "exec_") else box.exec()
        if box.clickedButton() is go:
            self.update_and_restart()

    def update_and_restart(self):
        """Your Maya stops bgcache, swaps in the new copy (the old one is
        kept in .bgcache_backups) and starts it again, without restarting Maya."""
        result = getattr(self, "_update_result", None) or {}
        if result.get("state") != "newer":
            return
        if result.get("zip"):                     # studio releases folder
            self._send_update(result["version"], result["zip"])
            return
        from bgcache import update
        self._flash_message("Downloading bgcache %s..." % result["version"], 30.0)
        folder = self.p.get("tmp") or os.path.join(self.session, "tmp")
        self._run_in_background(lambda: {"state": "ok", "path": update.download(result["zip_url"], folder,
                                                                                result["zip_name"])},
                                lambda got: self._send_update(result["version"], got.get("path"))
                                if got.get("state") == "ok" else
                                self._flash_message("Update didn't download: %s" % got.get("message"), 8.0))

    def _send_update(self, version, path):
        self.send_cmd("update", path=path)
        self._close_quietly = True
        self._flash_message("Updating bgcache to %s: it reopens in a moment" % version, 10.0)

    def _window_height(self):
        return 28 + 40 + 600 + BAR_H + 40 + self._continuity_height()


    # ---------------------------------------------------------------- camera menu
    def _fill_camera_menu(self):
        self.cam_menu.clear()
        cams = self.cfg.get("cameras") or []
        if not cams:
            act = self.cam_menu.addAction("No shot camera in this scene")
            act.setEnabled(False)
            return
        for cam in cams:
            name = cam["name"]
            w = QtWidgets.QWidget()
            row = QtWidgets.QHBoxLayout(w)
            row.setContentsMargins(10, 3, 10, 3)
            row.setSpacing(8)
            box = QtWidgets.QCheckBox()
            box.setStyleSheet(_checkbox_style())
            box.setCursor(Qt.PointingHandCursor)
            box.setChecked(name in self.checked)
            box.setToolTip("Cache this camera")
            box.toggled.connect(lambda on, n=name: self._set_checked(n, on))
            pick = QtWidgets.QPushButton(cam["label"])
            pick.setFlat(True)
            pick.setStyleSheet("text-align: left; border: none; background: transparent; font-size: 13px; "
                               "color: %s; font-weight: %s" % ("#f0f0f0" if name in self.checked else "#9a9a9a",
                                                                "bold" if name == self.view else "normal"))
            pick.clicked.connect(lambda _=False, n=name: self._view_camera(n))
            state = "viewing" if name == self.view else ("cached" if name in self.checked else "off")
            tag = QtWidgets.QLabel(state)
            tag.setStyleSheet("font-size: 11px; color: %s" % ("#cfe0f0" if state == "viewing" else "#8a8a8a"))
            row.addWidget(box)
            row.addWidget(pick, 1)
            row.addWidget(tag)
            w.setMinimumWidth(260)
            act = QtWidgets.QWidgetAction(self.cam_menu)
            act.setDefaultWidget(w)
            self.cam_menu.addAction(act)

    def _set_checked(self, cam, on):
        if on and cam not in self.checked:
            self.checked.append(cam)
            if not self.view:
                self.view = cam
        elif not on and cam in self.checked:
            self.checked.remove(cam)
            for d in (self.data, self.loaded, self.dirty):
                d.pop(cam, None)
            for k in [k for k in self.lru if k[0] == "live" and k[1] == cam]:
                del self.lru[k]
            if self.view == cam:
                self.view = self.checked[0] if self.checked else None
        self._save_cameras()

    def _view_camera(self, cam):
        if cam not in self.checked:
            self.checked.append(cam)       # picking a camera by name also caches it
        self.view = cam
        self.cam_menu.hide()
        self._save_cameras()
        self.drawer.changed()          # drawings are per camera

    def _save_cameras(self):
        common.write_json_atomic(self.p["cameras"], {"checked": self.checked, "view": self.view,
                                                     "focus": list(self.focus_range) if self.focus_range else None})

    # ---------------------------------------------------------------- focus range (b18)
    def set_focus(self, first=None, last=None, clear=False, save=True):
        """Cache only first-last of your shot. Frames outside that your edits
        change go red but wait; widening the range (or clearing it) lets the
        background Maya redo them. b4: Play also stays inside the range (and
        loops it); stepping and scrubbing still go anywhere."""
        if clear:
            self.focus_range = None
        else:
            a, b = self.focus_range or (self.start, self.end)
            a = a if first is None else first
            b = b if last is None else last
            a, b = max(self.start, min(a, self.end)), max(self.start, min(b, self.end))
            if a > b:
                a, b = b, a
            self.focus_range = None if (a, b) == (self.start, self.end) else (a, b)
        if save:                 # b19: while a handle is dragged, only when you let go
            self._save_cameras()
        self._update_status()
        self.canvas.update()

    def _in_focus(self, frame):
        return not self.focus_range or self.focus_range[0] <= frame <= self.focus_range[1]

    def _dirty_in_focus(self):
        dirty = self.dirty.get(self.view, set()) if self.view else set()
        return {f for f in dirty if self._in_focus(f)}

    def _focus_key(self, which):
        """I / O: set the focus start / end at the frame you're on (Shift: back to the shot's end)."""
        frame = self.current_live_frame()
        if frame is None:
            self._flash_message("I and O set the focus range on your own shot", 2.5)
            return
        if which == "in":
            self.set_focus(first=frame)
        else:
            self.set_focus(last=frame)
        a, b = self.focus_range or (self.start, self.end)
        self._flash_message("Caching %d-%d only" % (a, b) if self.focus_range else "Caching the whole shot", 2.0)

    def _bar_x(self, canvas, frame, right=False):
        n = float(self.total) or 1.0
        local = self._live_offset() + frame - self.start + (1 if right else 0)
        return int(canvas.width() * local / n)

    def _handle_at(self, canvas, event):
        """'in' / 'out' if the press is on a focus handle in the cache bar."""
        pt = self._point(event)
        if pt.y() < canvas.height() - BAR_H - TAB_H - 2:
            return None
        a, b = self.focus_range or (self.start, self.end)
        xin, xout = self._bar_x(canvas, a), self._bar_x(canvas, b, right=True)
        # b4: a wider grab, reaching inward over the tab
        if -4 <= pt.x() - xin <= TAB_W + 2 and (abs(pt.x() - xin) <= abs(pt.x() - xout)):
            return "in"
        if -4 <= xout - pt.x() <= TAB_W + 2:
            return "out"
        return None

    def _frame_at(self, canvas, event):
        n = self.total or 1
        x = min(max(self._point(event).x(), 0), canvas.width() - 1)
        local = int(x * n / float(max(1, canvas.width()))) - self._live_offset()
        return self.start + local
        self._update_cam_button()
        self.canvas.update()

    def _update_cam_button(self):
        name = self._label(self.view) if self.view else "pick a camera"
        n = len(self.checked)
        short = name if len(name) <= 24 else name[:11] + "\u2026" + name[-11:]   # long names shortened
        self.cam_button.setText("%s    %d cached  \u25be" % (short, n) if n else "%s  \u25be" % short)
        self.setWindowTitle("bgcache %s player - %s" % (__version__, self._label(self.view) or "no camera"))

    @staticmethod
    def _label(cam):
        return cam.split("|")[-1] if cam else ""

    # ================================================================ sound
    def _init_live_sound(self):
        self.live_pcm, self.live_status = None, "no sound in scene"
        info = self.cfg.get("audio")
        if not info:
            return
        if info.get("mute"):
            self.live_status = "sound muted in Maya"
            return
        try:
            self.live_pcm, self.channels, self.rate = self.audio_mod.load_aligned(
                info, self.start, self.end, self.fps)
            self.live_status = "sound on"
        except Exception as error:
            self.live_status = "sound unreadable: %s" % error
            print("bgcache: %s (%s)" % (self.live_status, info.get("path")))

    def _rebuild_sound(self):
        parts, any_sound = [], False
        n_live = self.end - self.start + 1
        for seg in self.segments:
            if seg["kind"] == "live":
                parts.append(self.audio_mod.fit(self.live_pcm, n_live, self.fps, self.rate, self.channels))
                any_sound = any_sound or self.live_pcm is not None
            else:
                parts.append(seg["pcm"])
                any_sound = any_sound or bool(seg["sound"])
        if self.live_pcm is not None or not any_sound:
            status = self.live_status
        else:                                   # neighbours play, your shot doesn't: say so
            status = "sound on, except your shot (%s)" % self.live_status
        self.sound.set_pcm(b"".join(parts) if any_sound else b"", self.channels, self.rate, self.fps, status)

    def _sound_text(self):
        if self.sound.muted:
            return "sound off (M)"
        return self.sound.status

    # ================================================================ reel
    def _rebuild_reel(self):
        """Before shots + live shot + after shots, in sequence order."""
        if self.test_mode:
            return            # rebuilt when the sync test ends
        anchor = self._locate(self.pos) if self.segments else None
        order = {s: i for i, s in enumerate(self.shots)}
        segs = []

        def neighbours(side):
            out = []
            if not self.continuity_on:
                return out
            for shot in sorted(self.staged[side], key=lambda s: order.get(s, 1e9)):
                ready = self.prepared.get(shot)
                if ready:
                    out.append({"kind": side, "shot": shot, "n": len(ready["frames"]),
                                "frames": ready["frames"], "pcm": ready["pcm"], "sound": ready["sound"],
                                "first": ready["first"], "label": self._footage_label(ready["info"])})
            return out

        segs += neighbours("before")
        live = {"kind": "live", "shot": self.live_shot, "n": self.end - self.start + 1}
        if self.live_ref and self.live_ref_ready:
            live["ref"] = self.live_ref_ready["frames"]
            live["label"] = self._footage_label(self.live_ref_ready["info"])
        segs.append(live)
        segs += neighbours("after")
        self.segments = segs
        self.total = sum(s["n"] for s in segs)
        # stay on the same picture if it's still in the reel
        if anchor:
            seg, local = anchor
            if seg["kind"] == "live":
                self.pos = self._live_offset() + local
            else:
                self.pos = next((o + local for o, s in self._offsets() if s["shot"] == seg["shot"]),
                                self._live_offset())
        self.pos = min(max(self.pos, 0), self.total - 1)
        self._rebuild_sound()
        self._update_strip_header()
        direction = self.playing
        if direction:                      # restart cleanly from the same picture
            self._stop()
            self.toggle_play(direction)
        self.canvas.update()

    def _offsets(self):
        o = 0
        for s in self.segments:
            yield o, s
            o += s["n"]

    def _live_offset(self):
        for o, s in self._offsets():
            if s["kind"] == "live":
                return o
        return 0

    def _locate(self, pos):
        for o, s in self._offsets():
            if pos < o + s["n"]:
                return s, pos - o
        last = self.segments[-1]
        return last, last["n"] - 1

    def _live_frame(self, pos=None):
        seg, local = self._locate(self.pos if pos is None else pos)
        return self.start + local if seg["kind"] == "live" else None

    def _move_to_live(self, frame):
        self.pos = self._live_offset() + min(max(frame, self.start), self.end) - self.start

    def _range_text(self):
        return self._range_texts()[0]

    def _range_texts(self):
        """The playback bar's range text, longest first: shot numbers around
        your range, then counts ("3 before · 1001 – 1100 · 2 after"), then
        the range alone. The label shows the first that fits."""
        short = lambda shot: shot.split("_")[-1]
        segs = getattr(self, "segments", None) or []
        before = [short(s["shot"]) for s in segs if s["kind"] == "before"]
        after = [short(s["shot"]) for s in segs if s["kind"] == "after"]
        rng = "%d – %d" % (self.start, self.end)
        full = "  ·  ".join(([" ".join(before)] if before else []) + [rng] + ([" ".join(after)] if after else []))
        counts = "  ·  ".join((["%d before" % len(before)] if before else []) + [rng]
                              + (["%d after" % len(after)] if after else []))
        return [full, counts, rng]














    def _flash_message(self, text, seconds=3.0):
        self._flash, self._flash_until = text, time.time() + seconds
        self.canvas.update()




    def _update_strip_header(self):
        """The ticked shots are shown by their cards (and the range text in
        the playback bar); 0.7.3 removed the Before/After list from here."""
        if getattr(self, "range_label", None) is not None:
            self.range_label.set_texts(self._range_texts())

    def _save_prefs(self):
        self._continuity_prefs()
        common.save_prefs(self.prefs)



    # ================================================================ time sync
    def send_time(self):
        frame = self._live_frame()
        if frame is None:
            return            # on a neighbour shot: Maya stays where it is
        try:
            common.write_json_atomic(self.p["player_time"], {
                "frame": frame, "ts": time.time(), "sync": self.sync})
        except (IOError, OSError):
            pass

    def send_cmd(self, cmd, **extra):
        msg = {"cmd": cmd, "ts": time.time(), "frame": self._live_frame() or self.start}
        self._last_cmd_ts = msg["ts"]
        msg.update(extra)
        try:
            common.write_json_atomic(self.p["player_cmd"], msg)
        except (IOError, OSError):
            pass

    def _follow_maya(self):
        st = common.read_json(self.p["maya_time"])
        if not st or st.get("ts", 0) <= self._maya_ts:
            return
        self._maya_ts = st["ts"]
        if st.get("raise"):                 # the shelf button, while bgcache runs
            self.showNormal()
            self.raise_()
            self.activateWindow()
            return
        if st.get("note"):                  # a message from your Maya, e.g. a reload that failed
            self._reload_asked = None
            self._flash_message(st["note"], 8.0)
            return
        if (not self.sync and not st.get("force")) or self.playing or self.dragging:
            return              # "force": a step-key jump, followed even with Sync off
        frame = int(st["frame"])
        if self.start <= frame <= self.end:
            pos = self._live_offset() + frame - self.start
            if pos != self.pos:
                self.pos = pos
                self.canvas.update()

    # ================================================================ reload
    RELOAD_GIVE_UP_S = 600        # no sign of the reload by then: stop saying it's coming

    def reload_scene(self):
        """Cache > Reload scene: your Maya exports the scene (can take a while
        on a heavy shot), then the background Maya reopens it. A banner over
        the picture says which stage it's at until it's done."""
        self.send_cmd("reload")
        self._reload_asked = (time.time(), self.cfg.get("rev", 1), self._reloads_done or 0)
        self.canvas.update()

    def _reload_banner(self):
        """The reload banner's text, or None when no reload is going on."""
        clock = lambda since: "%d:%02d" % divmod(int(max(0, time.time() - since)), 60)
        if self.state == "reloading scene":
            since = self.cfg.get("reloaded_at") or (self._reload_asked or (time.time(),))[0]
            return "Reloading scene in the background Maya... %s   (the picture is from before)" % clock(since)
        if self._reload_asked:
            asked, rev, _done = self._reload_asked
            if self.cfg.get("rev", 1) != rev:
                return "Reloading scene in the background Maya... %s" % clock(asked)
            if time.time() - asked > self.RELOAD_GIVE_UP_S:
                self._reload_asked = None
                self._flash_message("Reload scene didn't start: see your Maya's Script Editor", 6.0)
                return None
            return "Reload scene: your Maya is exporting the scene... %s" % clock(asked)
        return None

    def _track_reload(self, status):
        """Called on every status read: notices a finished reload (yours, or
        one started from the Maya panel), however quick it was."""
        done = int(status.get("reloads") or 0)
        if self._reloads_done is None:          # first status: just note where it's at
            self._reloads_done = done
            return
        if done > self._reloads_done and self.state != "reloading scene":
            self._reloads_done = done
            self._reload_asked = None
            self._flash_message("Scene reloaded: re-rendering all frames", 4.0)

    # ================================================================ health
    STUCK_S = 120                 # dirty frames and nothing new for this long: say so
    STUCK_GPU_S = 30              # the same, after graphics-memory errors in worker.log

    def _track_health(self):
        """On every status poll: note when caching last moved, and (every 2 s)
        look for graphics-memory errors in the background Maya's log."""
        now = time.time()
        dirty = self._dirty_in_focus()
        key = (len(dirty), sum(self.loaded.get(self.view, {}).values()) if self.view else 0)
        if key != self._progress_key or not dirty or getattr(self, "paused", False) or self._loading():
            self._progress_key, self._progress_t = key, now
        if now - self._log_check_t >= 2.0:
            self._log_check_t = now
            text, self._log_pos = common.read_new(self.p["log"], self._log_pos)
            if text and common.GPU_TROUBLE_RE.search(text):
                self._gpu_trouble_t = now

    def _health_banner(self):
        """A red banner when caching is in trouble, else None."""
        if self.test_mode or self._loading() or getattr(self, "paused", False):
            return None
        dirty = bool(self._dirty_in_focus())
        if self._warning and dirty:
            return self._warning
        stuck = time.time() - self._progress_t
        if dirty and self._gpu_trouble_t and stuck > self.STUCK_GPU_S:
            return ("GPU deformers failed in the background Maya and caching stopped: "
                    "bgcache is restarting it on the CPU. If this stays, press Stop and Start.")
        if dirty and stuck > self.STUCK_S:
            return ("Caching seems stuck: nothing new for %d:%02d. Try Stop and Start "
                    "(worker.log in ~/.bgcache/logs has the details)." % divmod(int(stuck), 60))
        return None

    # ================================================================ data
    def _check_config(self):
        """The controller rewrites config.json on Reload scene."""
        try:
            mtime = os.path.getmtime(self.p["config"])
        except OSError:
            return
        if mtime == self._cfg_mtime:
            return
        self._cfg_mtime = mtime
        cfg = common.read_json(self.p["config"])
        if not cfg or cfg.get("rev", 1) == self.cfg.get("rev", 1):
            return
        self.cfg = cfg
        self.start, self.end = int(cfg["start"]), int(cfg["end"])
        self.fps = float(cfg.get("fps") or self.fps)
        for cam in list(self.data):
            self.data[cam] = {f: b for f, b in self.data[cam].items() if self.start <= f <= self.end}
            self.loaded[cam] = {f: v for f, v in self.loaded[cam].items() if self.start <= f <= self.end}
        self.lru.clear()
        self._init_live_sound()
        self._update_cam_button()
        self._rebuild_reel()

    def _loading(self):
        return self.state in ("copying scene", "snapshotting", "starting background Maya...", "starting",
                              "opening scene", "reloading scene")

    def _loading_text(self):
        since = max(self.cfg.get("launched_at") or 0, self.cfg.get("reloaded_at") or 0)
        elapsed = int(time.time() - since) if since else 0
        what = {"copying scene": "Copying your Maya scene",
                "snapshotting": "Reading your animation"}.get(self.state)
        if what:
            return "%s..." % what
        if self._warning and "GPU" in self._warning:
            # b18: the restart on the CPU reopens your scene; say so, so it isn't taken for a freeze
            since = self._rescue_seen or max(self.cfg.get("launched_at") or 0, self.cfg.get("reloaded_at") or 0)
            elapsed = int(time.time() - since) if since else 0
            return ("GPU deformers failed: restarting the background Maya on the CPU, your edits are "
                    "kept... %d:%02d" % (elapsed // 60, elapsed % 60))
        what = "Launching background Maya" if self.state.startswith("starting") else \
            "Reloading scene" if self.state == "reloading scene" else "Loading scene"
        text = "%s... %d:%02d" % (what, elapsed // 60, elapsed % 60)
        usual = self.cfg.get("usual_startup")
        if usual and not self.cfg.get("reloaded_at"):
            text += " (usually about %d:%02d)" % (int(usual) // 60, int(usual) % 60)
        return text

    def _spin(self):
        if not self.playing and (self._loading() or self._reload_asked or
                                 time.time() < self._flash_until + 0.1):
            self.canvas.update()

    def _status_changed(self):
        try:
            mtime = os.stat(self.p["status"]).st_mtime_ns
        except OSError:
            return False
        if mtime == getattr(self, "_status_mtime", None):
            return False
        self._status_mtime = mtime
        return True

    def _poll_if_changed(self):
        if self._status_changed():
            self._poll()

    def _poll(self):
        self._status_changed()          # note the version we're about to read
        self._check_config()
        st = common.read_json(self.p["status"])
        if st:
            self.state = st.get("state", "")
            self._track_reload(st)
            self._show_paused(bool(st.get("paused")))
            for cam, info in (st.get("cameras") or {}).items():
                if cam not in self.checked:
                    continue
                self.dirty[cam] = set(info.get("dirty") or [])
                for key, version in (info.get("versions") or {}).items():
                    frame = int(key)
                    if self.loaded[cam].get(frame) == version:
                        continue
                    try:
                        with open(common.frame_path(self.session, frame, cam), "rb") as handle:
                            blob = handle.read()
                    except (IOError, OSError):
                        continue
                    self.data[cam][frame] = blob
                    self.loaded[cam][frame] = version
                    self.lru.pop(("live", cam, frame), None)
            warning = st.get("warning") or ""
            if warning and not self._warning:
                self._rescue_seen = time.time()
            self._warning = warning
            self._gpu = st.get("gpu")
            self._worker_pid = st.get("pid")
        self._track_health()
        self._follow_maya()
        self._update_status()
        if self.controller_pid and not common.pid_alive(self.controller_pid):
            self._close_quietly = True        # your Maya is gone: nothing to ask
            self.close()
        if not self.playing:
            self.canvas.update()

    def _update_status(self):
        text = self._loading_text() if self._loading() else self.state
        if self.state.startswith("error"):
            self.status_label.setStyleSheet("color: #ff8a80")
        elif getattr(self, "paused", False) and not self._loading():
            self.status_label.setStyleSheet("color: #e8c070")
            dirty = len(self.dirty.get(self.view, ())) if self.view else 0
            text = "paused, %d frame%s to redo" % (dirty, "" if dirty == 1 else "s")
        else:
            self.status_label.setStyleSheet("")
        if self.playing and len(self.shown) > 2:
            span = self.shown[-1] - self.shown[0]
            if span > 0:
                text += "  ·  %.1f fps" % ((len(self.shown) - 1) / span)
        else:
            text += "  ·  %.0f fps" % self.fps
        if not self.sync:
            text += "  ·  sync off"
        if self.focus_range:
            waiting = len(self.dirty.get(self.view, set()) - self._dirty_in_focus()) if self.view else 0
            text += "  ·  focus %d-%d" % self.focus_range
            if waiting:
                text += " · %d frame%s waiting outside" % (waiting, "" if waiting == 1 else "s")
        if self._warning:
            text += "  ·  GPU failed, caching on CPU"
            self.status_label.setStyleSheet("color: #ff8a80")
        elif self._gpu is False and not self._loading():
            text += "  ·  caching on CPU"          # quiet: GPU Override is off in your Maya
        self.status_label.setText(text)

    def _image(self, pos):
        seg, local = self._locate(pos)
        if seg["kind"] == "live" and seg.get("ref"):
            if local >= len(seg["ref"]):
                return None                 # reference movie shorter than the shot
            seg = {"kind": "ref", "shot": "ref", "frames": seg["ref"]}
        if seg["kind"] == "live":
            cam, frame = self.view, self.start + local
            if cam is None or frame not in self.data.get(cam, {}):
                return None
            key = ("live", cam, frame)
        else:
            key = (seg["shot"], seg["frames"][local])
        img = self.lru.get(key)
        if img is None:
            if seg["kind"] == "live":
                img = QtGui.QImage.fromData(QtCore.QByteArray(self.data[cam][frame]))
            else:
                img = QtGui.QImage(seg["frames"][local])
            self.lru[key] = img
            while len(self.lru) > LRU_SIZE:
                self.lru.popitem(last=False)
        else:
            self.lru.move_to_end(key)
        return img

    # ================================================================ sound timing
    def _sound_pos(self, pos):
        """Where in the soundtrack to start for picture position pos, shifted
        by your offset from the sync test (+ = earlier). Nothing automatic:
        the audio buffer size is not the real delay (it made sound ~6 frames early)."""
        return pos + self.audio_offset

    def _play_sound(self, pos):
        start = self._sound_pos(pos)
        token = self._play_token = object()
        if start >= 0:
            self.sound.play(start)
        else:   # sound should start later than the picture: wait
            QtCore.QTimer.singleShot(int(-start / self.fps * 1000), lambda: (
                self.playing > 0 and self._play_token is token and self.sound.play(0)))

    def _scrub_sound(self, old):
        if self.scrub_on and not self.playing and self.pos != old:
            self.sound.scrub(max(0.0, self._sound_pos(self.pos)))

    def _set_offset(self, frames):
        self.audio_offset = round(frames, 2)
        self.prefs["audio_offset"] = self.audio_offset
        self._save_prefs()
        if self.playing > 0:
            self._play_sound(self.pos)     # hear the change right away
        when = "earlier" if self.audio_offset > 0 else "later" if self.audio_offset < 0 else ""
        self._flash = "sound offset %+.2f frames %s" % (self.audio_offset, when)
        self._flash_until = time.time() + 2.0
        self.canvas.update()

    def _set_scrub(self, on):
        self.scrub_on = on
        self.b_scrub.setChecked(on)
        self.prefs["scrub"] = on
        self._save_prefs()

    # ---------------------------------------------------------------- sync test
    def toggle_sync_test(self):
        """Flash + click once a second; nudge [ ] until they line up."""
        self._stop()
        if self.test_mode:
            self.test_mode = False
            self.pos = self._test_saved_pos
            self._rebuild_reel()
            self.canvas.update()
            return
        self._test_saved_pos = self.pos
        self.test_mode = True
        self.test_every = max(1, int(round(self.fps)))
        self.total = self.test_every * 4
        self.pos = 0
        self.sound.set_pcm(self.audio_mod.click_track(self.total, self.fps, self.rate, self.channels,
                                                      self.test_every),
                           self.channels, self.rate, self.fps, "sync test")
        if self.sound.muted:
            self._set_mute(False)
        self.toggle_play(1)

    # ================================================================ playback
    def _play_window(self):
        """(first, end) reel positions playback stays in: the focus range when
        one is set (b4: like a play range; neighbouring shots are skipped),
        else the whole reel."""
        if not self.focus_range:
            return 0, self.total
        live = self._live_offset()
        a, b = self.focus_range
        return live + a - self.start, min(self.total, live + b - self.start + 1)

    def toggle_play(self, direction=1):
        if self.playing:
            stopping = self.playing == direction
            self.playing = 0
            self.sound.stop()
            self._set_play_icons()
            if stopping:
                self.send_time()
                self.canvas.update()
                return
        self.playing = direction
        lo, hi = self._play_window()
        if not lo <= self.pos < hi:            # outside the focus: play it from its start
            self.pos = lo if direction > 0 else hi - 1
        self.origin = self.pos
        self.loops = 0
        self.clock.restart()
        self.shown.clear()
        if direction > 0:
            self._play_sound(self.pos)
        self._set_play_icons()
        self.canvas.update()

    def _set_play_icons(self):
        self.transport["play"].setIcon(_icon("pause" if self.playing > 0 else "play"))
        self.transport["play_back"].setIcon(_icon("pause" if self.playing < 0 else "play_back"))

    def _tick(self):
        if not self.playing:
            return
        lo, hi = self._play_window()
        n = max(1, hi - lo)
        i = self.origin + self.playing * int(self.clock.nsecsElapsed() * 1e-9 * self.fps)
        if self.loop:
            loops = (i - lo) // n
            i = lo + (i - lo) % n
            if loops != self.loops:
                self.loops = loops
                if self.playing > 0:
                    self._play_sound(lo)
        elif not lo <= i < hi:
            i = min(max(i, lo), hi - 1)
            self.playing = 0
            self.sound.stop()
            self._set_play_icons()
            self.send_time()
        if i != self.pos:
            self.pos = i
            self.shown.append(time.time())
            self.canvas.update()

    def _stop(self):
        if self.playing:
            self.playing = 0
            self.sound.stop()
            self._set_play_icons()

    def _set_pos(self, pos):
        self._stop()
        self.pos = pos % self.total
        self.canvas.update()

    def _step(self, delta):
        old = self.pos
        self._set_pos(self.pos + delta)
        self._scrub_sound(old)
        if not self.test_mode:
            self.send_time()

    def _jump(self, pos):
        old = self.pos
        self._set_pos(pos)
        self._scrub_sound(old)
        if not self.test_mode:
            self.send_time()

    def drawn_frames(self):
        """Frames in your range with a mark on the bar, in order."""
        try:
            return sorted(f for f in self.drawer.ticks() if self.start <= f <= self.end)
        except Exception:  # drawings not ready yet: no marks
            return []

    def step_drawing(self, delta):
        """Go to the next (1) or previous (-1) drawing. Past the last one it
        cycles back to the first (and before the first, to the last)."""
        frames = self.drawn_frames()
        if not frames:
            self._flash_message("No drawings to step to", 2.0)
            return
        live = self._live_offset()
        current = self.start + self.pos - live            # Maya frame (outside your range when on a neighbour)
        if delta > 0:
            target = next((f for f in frames if f > current), frames[0])
            wrapped = frames[-1] <= current <= self.end
        else:
            target = next((f for f in reversed(frames) if f < current), frames[-1])
            wrapped = self.start <= current <= frames[0]
        self._jump(live + target - self.start)
        if wrapped and len(frames) > 1:
            self._flash_message("Back to the first drawing" if delta > 0 else "Round to the last drawing", 1.5)

    def _set_loop(self, on):
        self.loop = on
        self.b_loop.setChecked(on)

    def _set_mute(self, muted):
        if self.sound.muted != muted:
            self.sound.toggle_mute()
        self.b_sound.setChecked(not muted)
        if not muted and self.playing > 0:
            self._play_sound(self.pos)
        self.canvas.update()

    def _set_sync(self, on):
        self.sync = on
        self.b_sync.setChecked(on)
        self.prefs["sync"] = on
        self._save_prefs()
        self.send_time()
        self._update_status()

    def _set_on_top(self, on):
        self.setWindowFlag(Qt.WindowStaysOnTopHint, on)
        self.b_top.setChecked(on)
        self.show()

    def showEvent(self, event):
        super(Player, self).showEvent(event)
        QtCore.QTimer.singleShot(0, self._scroll_to_live)

    def stop_bgcache(self):
        """bgcache > Stop: your Maya stops the background Maya
        and closes this player."""
        if not self.test_mode and not self.drawer.ask_to_save(self, "stopping bgcache"):
            return
        self._close_quietly = True
        self.send_cmd("stop")
        self._flash_message("Stopping bgcache")
        # b13: your Maya normally stops everything at once. If it's frozen,
        # the player stops the background Maya itself, then closes.
        QtCore.QTimer.singleShot(4000, self._stop_background_directly)

    def _maya_answered(self):
        done = common.read_json(self.p["player_cmd"] + ".done") or {}
        return done.get("ts", 0) >= getattr(self, "_last_cmd_ts", 0)

    def _stop_background_directly(self):
        pid = self._worker_pid
        if self._maya_answered():
            pid = None                       # your Maya is stopping it
        if pid and pid != os.getpid() and common.pid_alive(pid):
            print("bgcache player: your Maya didn't stop the background Maya: asking it to quit")
            common.post_message(self.session, {"op": "quit"})
            until = time.time() + 8.0
            while time.time() < until and common.pid_alive(pid):
                QtCore.QCoreApplication.processEvents()
                time.sleep(0.2)
            if common.pid_alive(pid):
                print("bgcache player: the background Maya didn't answer: ending it (pid %s)" % pid)
                import signal
                try:
                    os.kill(int(pid), getattr(signal, "SIGKILL", signal.SIGTERM))
                except (OSError, ValueError) as error:
                    print("bgcache player: couldn't end it: %s" % error)
        self.close()

    def _close_choice(self):
        """Closing the window (x): "stop", "keep" (caching carries on; the
        shelf button reopens the player) or None (cancel). Asks unless you
        ticked "Don't ask again"."""
        remembered = self.prefs.get("on_close")
        if remembered in ("stop", "keep"):
            return remembered
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle("bgcache")
        box.setText("Stop bgcache, or keep caching in the background?")
        box.setInformativeText("Keep caching: the bgcache shelf button brings this player back, "
                               "with everything cached so far.")
        stop = box.addButton("Stop bgcache", QtWidgets.QMessageBox.AcceptRole)
        keep = box.addButton("Keep caching", QtWidgets.QMessageBox.ActionRole)
        box.addButton("Cancel", QtWidgets.QMessageBox.RejectRole)
        box.setDefaultButton(keep)
        again = QtWidgets.QCheckBox("Don't ask again")
        box.setCheckBox(again)
        run = getattr(box, "exec", None) or box.exec_
        run()
        clicked = box.clickedButton()
        choice = "stop" if clicked is stop else "keep" if clicked is keep else None
        if choice and again.isChecked():
            self.prefs["on_close"] = choice
            self._save_prefs()
        return choice

    def closeEvent(self, event):
        if not getattr(self, "_close_quietly", False) and not self.test_mode:
            choice = self._close_choice()
            if choice is None:
                event.ignore()
                return
            if choice == "stop":
                event.ignore()
                self.stop_bgcache()           # also works when your Maya is frozen
                return
            if not self.drawer.ask_to_save(self, "closing the player"):
                event.ignore()
                return
        self.sound.stop()
        super(Player, self).closeEvent(event)

    # ================================================================ input
    def keyPressEvent(self, event):
        """Your Maya playback keys first (read from your hotkeys at Start),
        then the player's own keys where they don't clash with those."""
        key = event.key()
        action = self.keymap.action(event)
        if action == "scrub":
            self.scrub_held = True
            return
        if action and not event.isAutoRepeat() or action in ("prev_frame", "next_frame"):
            if action == "prev_frame":
                self._step(-1)
            elif action == "next_frame":
                self._step(1)
            elif action in ("prev_key", "next_key") and self.drawer.on:
                self.step_drawing(-1 if action == "prev_key" else 1)      # Draw mode: drawings, not keys
            elif action in ("prev_key", "next_key"):
                self.send_cmd(action)
            elif action == "play":
                self.toggle_play(1)
            elif action == "start":
                self._jump(0)
            elif action == "end":
                self._jump(self.total - 1)
            if action:
                return
        alt, ctrl, shift = (bool(event.modifiers() & m) for m in
                            (Qt.AltModifier, Qt.ControlModifier, Qt.ShiftModifier))
        if ctrl and key == Qt.Key_S and not shift:
            self.drawer.save_now()           # b3: drawings are shared on Save
            return
        if self.drawer.on and ctrl and key == Qt.Key_Z:
            (self.drawer.redo if shift else self.drawer.undo)()
            return
        if self.drawer.on and ctrl and key == Qt.Key_Y:
            self.drawer.redo()
            return
        if alt or ctrl:
            super(Player, self).keyPressEvent(event)
            return
        mine = lambda code: not self.keymap.taken(code)       # free in your Maya keys
        if key == Qt.Key_Space:
            self.toggle_play(1)
        elif key == Qt.Key_Left and mine(key):
            self._step(-1)
        elif key == Qt.Key_Right and mine(key):
            self._step(1)
        elif key == Qt.Key_Home and mine(key):
            self._jump(0)
        elif key == Qt.Key_End and mine(key):
            self._jump(self.total - 1)
        elif key == Qt.Key_D and mine(key):
            self.drawer.set_on(not self.drawer.on)
        elif key == Qt.Key_L and mine(key):
            self._set_loop(not self.loop)
        elif key == Qt.Key_M and mine(key):
            self._set_mute(not self.sound.muted)
        elif key == Qt.Key_C and mine(key):
            self.toggle_browser()
        elif key in (Qt.Key_I, Qt.Key_O) and mine(key):
            if _shift(event):
                self.set_focus(**({"first": self.start} if key == Qt.Key_I else {"last": self.end}))
            else:
                self._focus_key("in" if key == Qt.Key_I else "out")
        elif key == Qt.Key_T and mine(key):
            self._set_on_top(not self.b_top.isChecked())
        elif key == Qt.Key_BracketLeft and mine(key):
            self._set_offset(self.audio_offset + 0.25)    # sound earlier
        elif key == Qt.Key_BracketRight and mine(key):
            self._set_offset(self.audio_offset - 0.25)    # sound later
        elif key == Qt.Key_Escape and self.test_mode:
            self.toggle_sync_test()
        else:
            super(Player, self).keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if not event.isAutoRepeat() and self.keymap.is_key("scrub", event):
            self.scrub_held = False
            return
        super(Player, self).keyReleaseEvent(event)

    # ================================================================ drawing input
    @staticmethod
    def _point(event):
        for name in ("position", "posF", "pos"):
            fn = getattr(event, name, None)
            if fn is not None:
                try:
                    pt = fn()
                    return QtCore.QPointF(pt)
                except Exception:  # Qt versions name the position differently: try the next
                    continue
        return QtCore.QPointF(0, 0)

    def current_live_frame(self):
        """Your shot's frame on screen, live or shown as a department's movie
        (b4: drawings and focus work on both); None on a neighbour."""
        seg, local = self._locate(self.pos)
        if seg["kind"] != "live":
            return None
        return self.start + local

    def _wants_scrub(self, canvas, event):
        in_bar = self._point(event).y() >= canvas.height() - BAR_H - 4
        return event.button() == Qt.MiddleButton or self.scrub_held or in_bar

    def canvas_press(self, canvas, event):
        """True when the press is used here (a focus handle, drawing, or
        scrubbing in Draw mode)."""
        if event.button() == Qt.LeftButton and not self.playing:
            handle = self._handle_at(canvas, event)
            if handle:
                self._handle_drag = handle
                return True
        if event.button() == Qt.MiddleButton or (self.drawer.on and event.button() == Qt.LeftButton
                                                 and self._wants_scrub(canvas, event)):
            self.input_mode = "scrub"
            self.dragging = True
            self.scrub(canvas, event)
            return True
        if not self.drawer.on or event.button() != Qt.LeftButton:
            return False
        if self.playing:
            return True                       # no drawing while playing
        self.input_mode = "draw" if self.drawer.press(self._point(event), whole=_shift(event)) else None
        return True

    def canvas_move(self, canvas, event):
        if not event.buttons() and not self._handle_drag:
            self._hover_handle_at(canvas, event)
        if self._handle_drag:
            frame = self._frame_at(canvas, event)
            if self._handle_drag == "in":
                self.set_focus(first=frame, save=False)
            else:
                self.set_focus(last=frame, save=False)
            return True
        if self.input_mode == "scrub":
            self.scrub(canvas, event)
            return True
        if self.input_mode == "draw":
            self.drawer.move(self._point(event))
            return True
        if self.drawer.on and not self.input_mode:
            self.drawer.hover_at(self._point(event))     # the size circle follows the pointer
        return self.drawer.on and bool(event.buttons() & Qt.LeftButton)

    def _hover_handle_at(self, canvas, event):
        """b4: a focus handle under the pointer lights up, with a sideways cursor."""
        handle = None if self.playing else self._handle_at(canvas, event)
        if handle == getattr(self, "_hover_handle", None):
            return
        self._hover_handle = handle
        if handle:
            canvas.setCursor(Qt.SizeHorCursor)
        else:
            canvas.setCursor(Qt.CrossCursor if self.drawer.on else Qt.ArrowCursor)
        canvas.update()

    def canvas_release(self, canvas, event):
        if self._handle_drag:
            self._handle_drag = None
            self._save_cameras()
            a, b = self.focus_range or (self.start, self.end)
            self._flash_message("Caching %d-%d only" % (a, b) if self.focus_range else "Caching the whole shot", 2.0)
            return True
        mode, self.input_mode = self.input_mode, None
        if mode == "scrub":
            self.dragging = False
            if not self.test_mode:
                self.send_time()
            return True
        if mode == "draw":
            self.drawer.release(self._point(event))
            return True
        return self.drawer.on

    def canvas_tablet(self, canvas, event):
        """Pen input with pressure, when the tablet's pressure reaches this
        machine (over PCoIP it may arrive as a plain mouse instead)."""
        kind = event.type()
        if not self.drawer.on or self.playing:
            event.ignore()
            return
        if kind == QtCore.QEvent.TabletPress:
            if self.scrub_held or self._point(event).y() >= canvas.height() - BAR_H - 4:
                event.ignore()                   # let the mouse event scrub
                return
            eraser = "Eraser" in str(event.pointerType())
            self.input_mode = "tablet" if self.drawer.press(self._point(event), event.pressure(), eraser,
                                                            whole=_shift(event)) else None
            event.accept()
        elif kind == QtCore.QEvent.TabletMove:
            if self.input_mode == "tablet":
                self.drawer.move(self._point(event), event.pressure())
                event.accept()
            else:
                event.ignore()
        elif kind == QtCore.QEvent.TabletRelease:
            if self.input_mode == "tablet":
                self.input_mode = None
                self.drawer.release(self._point(event))
                event.accept()
            else:
                event.ignore()

    def update_draw_buttons(self):
        self.b_draw.setChecked(self.drawer.on)
        self.b_drawings.setChecked(self.drawer.show)

    def _set_show_drawings(self, on):
        self.drawer.show = on
        self.drawer.save_prefs()
        self.canvas.update()

    def _set_gate_mask(self, on):
        self.gate_mask = on
        self.b_gate.setChecked(on)
        self.prefs["gate_mask"] = on
        self._save_prefs()
        self.canvas.update()

    def _paint_gate(self, p, target):
        """Film gate mask: 75% black outside what's in shot, thin line on the gate."""
        gate = None
        for cam in self.cfg.get("cameras") or []:
            if cam.get("name") == self.view:
                gate = cam.get("gate")
        W, H = int(self.cfg.get("width") or 960), int(self.cfg.get("height") or 540)
        rect = self.drawui.drawing.film_gate_rect(gate, W, H)
        if rect is None:
            return
        s = target.width() / float(W)
        inner = QtCore.QRectF(target.x() + rect[0] * s, target.y() + rect[1] * s, rect[2] * s, rect[3] * s)
        outer = QtCore.QRectF(target)
        shade = QtGui.QColor(0, 0, 0, 191)
        p.save()
        p.setPen(Qt.NoPen)
        p.setBrush(shade)
        p.drawRect(QtCore.QRectF(outer.left(), outer.top(), outer.width(), inner.top() - outer.top()))
        p.drawRect(QtCore.QRectF(outer.left(), inner.bottom(), outer.width(), outer.bottom() - inner.bottom()))
        p.drawRect(QtCore.QRectF(outer.left(), inner.top(), inner.left() - outer.left(), inner.height()))
        p.drawRect(QtCore.QRectF(inner.right(), inner.top(), outer.right() - inner.right(), inner.height()))
        p.setPen(QtGui.QPen(QtGui.QColor(150, 150, 150), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(inner)
        p.restore()

    def set_paused(self, on=None):
        """Pause / resume re-rendering. Sent straight to the background Maya
        (works even while your Maya is busy); resume starts at this frame."""
        on = self.b_pause.isChecked() if on is None else bool(on)
        frame = self._live_frame()
        common.post_message(self.session, {"op": "pause", "on": on,
                                           "focus": frame if frame is not None else self.start})
        self._show_paused(on)
        self._flash_message("Re-rendering paused: edits keep coming in, changed frames stay red"
                            if on else "Re-rendering resumed from this frame")

    def _show_paused(self, on):
        self.paused = on
        self.b_pause.blockSignals(True)
        self.b_pause.setChecked(on)
        self.b_pause.setText("Resume" if on else "Pause")
        self.b_pause.blockSignals(False)

    def _maya_cmd(self, cmd, message):
        self.send_cmd(cmd)
        self._flash_message(message)

    def scrub(self, canvas, event):
        if canvas.width() <= 0:
            return
        x = min(max(self._point(event).x(), 0), canvas.width() - 1)
        old = self.pos
        self._set_pos(int(x * self.total / float(canvas.width())))
        self._scrub_sound(old)

    # ================================================================ drawing
    def paint(self, canvas):
        """Draw the canvas: the frame (or why there's none), drawings, film
        gate, overlays and banners, then the cache bar."""
        p = QtGui.QPainter(canvas)
        rect = canvas.rect()
        p.fillRect(rect, QtGui.QColor(18, 18, 18))
        view = QtCore.QRect(0, 0, rect.width(), rect.height() - BAR_H)
        if self.test_mode:
            self._paint_test(p, view, rect)
            p.end()
            return
        seg, local = self._locate(self.pos)
        live = seg["kind"] == "live"
        ref = live and bool(seg.get("ref"))          # your shot, shown as a department's movie
        frame = self.start + local if live else None
        stale = live and not ref and frame in self.dirty.get(self.view, set())

        img = self._image(self.pos)
        target = view
        if img is not None and not img.isNull():
            target = self._paint_frame(p, view, img, live and not ref, frame, stale)
            if ref:
                self._paint_drawings_on_ref(p, target, frame)
        else:
            p.setPen(QtGui.QColor(150, 150, 150))
            p.drawText(view, Qt.AlignCenter, self._no_frame_text(p, view, seg, live, ref))
        self._paint_overlays(p, target, seg, local, live, ref, frame, stale)
        self._paint_bar(p, QtCore.QRect(0, rect.height() - BAR_H, rect.width(), BAR_H))
        p.end()

    def _paint_frame(self, p, view, img, yours, frame, stale):
        """The cached frame, fitted to the view; on your live shot (yours)
        also the drawings, film gate, paused tint and the red stale frame.
        Returns where the picture went."""
        scale = min(view.width() / float(img.width()), view.height() / float(img.height()))
        w, h = int(img.width() * scale), int(img.height() * scale)
        target = QtCore.QRect((view.width() - w) // 2, (view.height() - h) // 2, w, h)
        p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)
        p.drawImage(target, img)
        if yours:
            self.last_target = target
            try:
                self.drawer.paint_paper(p, target)        # Paper: the movie fades to white under the drawings
                self.drawer.paint(p, target, frame)
            except Exception as error:
                print("bgcache player: drawing: %s" % error)
            if self.gate_mask:
                self._paint_gate(p, target)
        if yours and getattr(self, "paused", False):
            p.fillRect(target, QtGui.QColor(190, 30, 30, 46))     # paused: a red tint over the picture
        if stale:
            p.setPen(QtGui.QPen(QtGui.QColor(220, 60, 60), 4))
            p.drawRect(target.adjusted(2, 2, -2, -2))
        return target

    def _paint_drawings_on_ref(self, p, target, frame):
        """b4: your drawings stay on when your shot shows a department's
        movie (same shot, same frames), fitted to the shot's frame shape
        inside the movie's picture; you can keep drawing there too."""
        w, h = float(self.drawer.W), float(self.drawer.H)
        scale = min(target.width() / w, target.height() / h)
        fit = QtCore.QRect(target.x() + int((target.width() - w * scale) / 2),
                           target.y() + int((target.height() - h * scale) / 2), int(w * scale), int(h * scale))
        self.last_target = fit
        try:
            self.drawer.paint_paper(p, fit)
            self.drawer.paint(p, fit, frame)
        except Exception as error:
            print("bgcache player: drawing: %s" % error)

    def _no_frame_text(self, p, view, seg, live, ref):
        """What the picture says when there's no frame to show (the spinner
        too while loading)."""
        if live and not self.cfg.get("cameras"):
            return "No shot camera in this scene\n(persp, top, front and side aren't offered)"
        if live and self.state.startswith("error"):
            p.setPen(QtGui.QColor(255, 138, 128))
            return "The background Maya stopped.\nSee worker.log in the session folder, then Stop and Start again."
        if ref:
            return "the %s movie has no frame here (it's shorter than the shot)" % seg["label"]
        if live and self._loading():
            self._paint_spinner(p, view)
            text = "\n\n\n\n%s" % self._loading_text()
            if not self.view and self.cfg.get("cameras"):
                text += "\nYou can pick a camera from the Camera menu now."
            return text
        if live and not self.view:
            return "Pick a camera from the Camera menu to start caching\n%s" % self.state
        return "frame not rendered yet\n%s" % self.state

    def _paint_overlays(self, p, target, seg, local, live, ref, frame, stale):
        """Text over the picture: camera and sound, frame number, the DRAW /
        PAUSED / SYNC OFF tags, and one banner at the top."""
        if ref:
            left = "REFERENCE: %s · %s     %s     (R: live)" % (seg["shot"], seg["label"], self._sound_text())
            right = "%d" % frame
        elif live:
            left = "%s     %s" % (self._label(self.view) or "no camera", self._sound_text())
            right = "%d%s" % (frame, "  stale" if stale else "")
        else:
            left = "%s · %s · %s     %s" % (seg["shot"], seg["label"], seg["kind"],
                                          "sound" if seg["sound"] else "no sound")
            right = str(seg["first"] + local)
        self._overlay(p, target, left, Qt.AlignLeft, 13)
        self._overlay(p, target, right, Qt.AlignRight, 15)
        tag_y = 0
        if self.drawer.on and live:
            mine = self.drawer.mine_now()
            layer = mine.active_layer() if mine else None
            dot = " ●" if mine is not None and mine.dirty else ""     # unsaved
            tag_y = self._overlay_tag(p, target, "DRAW · %s%s" % (layer["name"] if layer else "-", dot))
        if live and not ref and getattr(self, "paused", False):
            tag_y = self._overlay_tag(p, target, "PAUSED", y=tag_y, pause_icon=True)
        if live and self.focus_range:         # b4: why playback stays in part of the shot
            tag_y = self._overlay_tag(p, target, "FOCUS %d-%d" % self.focus_range, y=tag_y)
        if live and not self.sync:            # easy to miss otherwise (studio, b11)
            self._overlay_tag(p, target, "SYNC OFF", y=tag_y)
        banner = self._reload_banner()
        trouble = None if banner else self._health_banner()
        if time.time() < self._flash_until:
            self._overlay_top(p, target, self._flash)
        elif banner:
            self._overlay_top(p, target, banner, busy=True)
        elif trouble:
            self._overlay_top(p, target, trouble, warn=True)

    def _overlay_tag(self, p, target, text, y=0, pause_icon=False):
        """An orange tag at the picture's top left (DRAW, PAUSED); y: below
        another tag. Returns the y for a tag under this one."""
        font = p.font()
        font.setPixelSize(12)
        p.setFont(font)
        metrics = QtGui.QFontMetrics(font)
        w = metrics.horizontalAdvance(text) if hasattr(metrics, "horizontalAdvance") else metrics.width(text)
        icon_w = 14 if pause_icon else 0
        top = target.top() + 10 + y
        box = QtCore.QRect(target.left() + 12, top, w + 16 + icon_w, metrics.height() + 6)
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor(184, 102, 42, 220))
        p.drawRoundedRect(box, 3, 3)
        if pause_icon:                       # the orange tag's "II"
            p.setBrush(QtGui.QColor(255, 244, 232))
            bar_h = box.height() - 10
            p.drawRect(QtCore.QRect(box.left() + 8, box.top() + 5, 3, bar_h))
            p.drawRect(QtCore.QRect(box.left() + 14, box.top() + 5, 3, bar_h))
        p.setPen(QtGui.QColor(255, 244, 232))
        p.drawText(box.adjusted(icon_w, 0, 0, 0), Qt.AlignCenter, text)
        return y + box.height() + 6

    def _paint_spinner(self, p, view):
        r = 18
        c = view.center()
        box = QtCore.QRect(c.x() - r, c.y() - r - 24, 2 * r, 2 * r)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        p.setPen(QtGui.QPen(QtGui.QColor(60, 60, 60), 4))
        p.drawEllipse(box)
        p.setPen(QtGui.QPen(QtGui.QColor(232, 163, 61), 4, Qt.SolidLine, Qt.RoundCap))
        angle = (time.time() * 300.0) % 360.0
        p.drawArc(box, int(-angle * 16), 100 * 16)
        p.setPen(QtGui.QColor(170, 170, 170))

    def _overlay_top(self, p, target, text, busy=False, warn=False):
        """A message box at the top of the picture. busy: orange, with a
        small spinner (something is in progress). warn: red (needs you)."""
        font = p.font()
        font.setPixelSize(14)
        p.setFont(font)
        metrics = QtGui.QFontMetrics(font)
        w = metrics.horizontalAdvance(text) if hasattr(metrics, "horizontalAdvance") else metrics.width(text)
        h = metrics.height() + 8
        spin = h if busy else 0
        box = QtCore.QRect(target.center().x() - (w + spin) // 2 - 10, target.top() + 12, w + spin + 20, h)
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor(150, 40, 40, 230) if warn else
                   QtGui.QColor(122, 78, 20, 220) if busy else QtGui.QColor(0, 0, 0, 170))
        p.drawRoundedRect(box, 3, 3)
        if busy:
            r = QtCore.QRect(box.left() + 8, box.top() + 5, h - 10, h - 10)
            p.setRenderHint(QtGui.QPainter.Antialiasing, True)
            p.setPen(QtGui.QPen(QtGui.QColor(255, 220, 160), 2, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(r, int(-(time.time() * 300.0 % 360.0) * 16), 100 * 16)
        p.setPen(QtGui.QColor(240, 240, 240))
        p.drawText(box.adjusted(spin, 0, 0, 0), Qt.AlignCenter, text)

    def _paint_test(self, p, view, rect):
        """Sync test: white flash on the click frames, instructions on top."""
        w = min(view.width(), int(view.height() * 16 / 9.0))
        h = int(w * 9 / 16.0)
        target = QtCore.QRect((view.width() - w) // 2, (view.height() - h) // 2, w, h)
        flash = self.pos % self.test_every == 0
        p.fillRect(target, QtGui.QColor(255, 255, 255) if flash else QtGui.QColor(0, 0, 0))
        when = "earlier" if self.audio_offset > 0 else "later" if self.audio_offset < 0 else ""
        lines = ["SYNC TEST: the click should land exactly on the white flash",
                 "[  sound earlier      ]  sound later      Esc  done",
                 "your offset: %+.2f frames %s" % (self.audio_offset, when)]
        if not self.sound.available:
            lines.append("no audio output: %s" % self.sound.status)
        font = p.font()
        font.setPixelSize(15)
        p.setFont(font)
        p.setPen(QtGui.QColor(232, 163, 61))
        p.drawText(target.adjusted(20, 20, -20, -20), Qt.AlignHCenter | Qt.AlignBottom, "\n".join(lines))
        bar = QtCore.QRect(0, rect.height() - BAR_H, rect.width(), BAR_H)
        p.fillRect(bar, QtGui.QColor(40, 40, 40))
        x = int(bar.width() * (self.pos + 0.5) / float(self.total))
        p.fillRect(QtCore.QRect(x - 1, bar.y(), 2, bar.height()), QtGui.QColor(255, 255, 255))

    def _overlay(self, p, target, text, align, size):
        font = p.font()
        font.setPixelSize(size)
        p.setFont(font)
        metrics = QtGui.QFontMetrics(font)
        w = metrics.horizontalAdvance(text) if hasattr(metrics, "horizontalAdvance") else metrics.width(text)
        h = metrics.height()
        x = target.left() + 12 if align == Qt.AlignLeft else target.right() - 12 - w - 16
        box = QtCore.QRect(x, target.bottom() - 10 - h - 6, w + 16, h + 6)
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor(0, 0, 0, 140))
        p.drawRoundedRect(box, 3, 3)
        p.setPen(QtGui.QColor(240, 240, 240))
        p.drawText(box, Qt.AlignCenter, text)

    def _paint_bar(self, p, bar):
        p.fillRect(bar, QtGui.QColor(40, 40, 40))
        n = self.total
        have, dirty = self.data.get(self.view, {}), self.dirty.get(self.view, set())
        top = bar.y() + 3
        for o, seg in self._offsets():
            x0 = bar.x() + bar.width() * o // n
            x1 = bar.x() + bar.width() * (o + seg["n"]) // n
            if seg["kind"] != "live" or seg.get("ref"):
                p.fillRect(QtCore.QRect(x0, top, max(1, x1 - x0), bar.height() - 3), STAGED)
            else:
                for i in range(seg["n"]):
                    frame = self.start + i
                    color = RED if frame in dirty else GREEN if frame in have else None
                    if color is None:
                        continue
                    a = bar.x() + bar.width() * (o + i) // n
                    b = bar.x() + bar.width() * (o + i + 1) // n
                    p.fillRect(QtCore.QRect(a, top, max(1, b - a), bar.height() - 3), color)
            if o > 0:
                p.fillRect(QtCore.QRect(x0 - 1, bar.y(), 2, bar.height()), QtGui.QColor(18, 18, 18))
        try:
            drawn = self.drawer.ticks()
        except Exception:  # drawings not ready yet: no marks
            drawn = set()
        if drawn:
            # Drawn frames: 3 px orange ticks the full height of the bar with a
            # dark edge, so they read over green and red. Edges first, so ticks
            # on neighbouring frames don't cover each other.
            live = self._live_offset()
            xs = [bar.x() + int(bar.width() * (live + frame - self.start + 0.5) / n)
                  for frame in drawn if self.start <= frame <= self.end]
            for x in xs:
                p.fillRect(QtCore.QRect(x - 2, bar.y(), 5, bar.height()), TICK_EDGE)
            for x in xs:
                p.fillRect(QtCore.QRect(x - 1, bar.y(), 3, bar.height()), TICK)
        self._paint_focus(p, bar)
        x = bar.x() + int(bar.width() * (self.pos + 0.5) / n)
        p.fillRect(QtCore.QRect(x - 1, bar.y(), 2, bar.height()), QtGui.QColor(255, 255, 255))

    def _paint_focus(self, p, bar):
        """b18: the focus range: outside it the bar is dimmed (red frames
        there wait), with a handle at each end."""
        n = float(self.total) or 1.0
        live = self._live_offset()
        a, b = self.focus_range or (self.start, self.end)
        xa = bar.x() + int(bar.width() * (live + a - self.start) / n)
        xb = bar.x() + int(bar.width() * (live + b - self.start + 1) / n)
        if self.focus_range:
            x0 = bar.x() + int(bar.width() * live / n)
            x1 = bar.x() + int(bar.width() * (live + self.end - self.start + 1) / n)
            shade = QtGui.QColor(0, 0, 0, 130)
            if xa > x0:
                p.fillRect(QtCore.QRect(x0, bar.y(), xa - x0, bar.height()), shade)
            if x1 > xb:
                p.fillRect(QtCore.QRect(xb, bar.y(), x1 - xb, bar.height()), shade)
        hover = getattr(self, "_hover_handle", None) or self._handle_drag
        for x, inward, name in ((xa, 1, "in"), (xb, -1, "out")):
            color = FOCUS if self.focus_range else QtGui.QColor(175, 175, 175)
            if hover == name:
                color = color.lighter(125)
            # b4: a tab above the bar, pointing inward, so a handle shows even
            # at the window's edge; and a 3 px line down the bar
            p.fillRect(QtCore.QRect(x if inward > 0 else x - 3, bar.y(), 3, bar.height()), color)
            tab = QtGui.QPolygon([QtCore.QPoint(x, bar.y() - TAB_H), QtCore.QPoint(x + inward * TAB_W, bar.y() - TAB_H),
                                  QtCore.QPoint(x, bar.y())])
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawPolygon(tab)


def _name_and_icon(app):
    """bgcache's name and icon for the player (the Mac's Dock showed "mayapy"
    with a terminal icon; the Windows taskbar showed Python's)."""
    try:
        app.setApplicationName("bgcache")
        if hasattr(app, "setApplicationDisplayName"):
            app.setApplicationDisplayName("bgcache")
        here = os.path.dirname(os.path.abspath(__file__))
        for path in (os.path.join(here, "icons", "bgcache_200.png"),
                     os.path.join(os.path.dirname(os.path.dirname(here)), "icons", "bgcache_200.png")):
            if os.path.isfile(path):
                app.setWindowIcon(QtGui.QIcon(path))
                break
    except Exception as error:
        print("bgcache player: name/icon not set: %s" % error)


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    if len(argv) < 2:
        print(__doc__)
        return 1
    session = argv[1]
    pid = int(argv[2]) if len(argv) > 2 else None
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(argv)
    _name_and_icon(app)
    from bgcache import theme
    theme.apply(app, QtGui, QtWidgets)     # dialogs and popups dark too
    window = Player(session, pid)
    window.show()
    window.raise_()
    run = getattr(app, "exec", None) or app.exec_
    return run()


if __name__ == "__main__":
    sys.exit(main())
