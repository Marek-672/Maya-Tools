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
from bgcache.player_common import *  # noqa: F401,F403 (Qt, colours, helpers: used here and by tests as bgcache.player.X)
from bgcache.player_common import __all__ as _names
from bgcache import common, __version__  # noqa: F401
from bgcache.player_menus import MenusMixin, ReportDialog  # noqa: F401
from bgcache.player_range import RangeMixin
from bgcache.player_reel import ReelMixin
from bgcache.player_session import SessionMixin
from bgcache.player_input import InputMixin
from bgcache.player_paint import PaintMixin


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
class Player(MenusMixin, RangeMixin, ReelMixin, SessionMixin, InputMixin, PaintMixin,
             _continuity_part(), QtWidgets.QWidget):
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
        if self.focus_range:
            self._save_cameras()      # b8: the background Maya renders your range first
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
        # b8: it starts as your Maya's playback range (only that is rendered
        # first); with Sync on the two stay the same, both ways.
        focus = self.cfg.get("focus")
        if focus and len(focus) == 2 and tuple(focus) != (self.start, self.end):
            self.focus_range = (int(focus[0]), int(focus[1]))
        maya = self.cfg.get("maya_range") or [self.start, self.end]
        self.maya_range = (int(maya[0]), int(maya[1]))
        self._maya_range_ts = 0.0
        self._range_noted = False
        self._close_ts = time.time()      # b8: only close requests from now on
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
        lay.addWidget(self._build_reload_question())      # b21: shown when Refresh finds the scene changed
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
        self.b_app, app_menu = self._menu_word(row, "bgcache", "Reload scene, what's in the cache, restart, stop")
        # b21: Push selected is gone (Refresh sends the unkeyed values of what you've selected);
        # Reload scene is here for when you want it without Refresh asking.
        reload_item = app_menu.addAction("Reload scene", self.reload_scene)
        reload_item.setToolTip("Copy your scene to the background Maya again. Refresh asks for this when it sees the "
                               "scene has changed; here for the changes it can't see. Takes about as long as Start.")
        app_menu.addSeparator()
        show = app_menu.addAction("Show selected in the cache")
        show.setToolTip("Draw what's selected in your Maya in the cache, though it's part of the environment")
        show.triggered.connect(lambda: self._maya_cmd("cache_show_selected", "Show selected: sent to your Maya"))
        hide = app_menu.addAction("Remove selected from the cache")
        hide.setToolTip("Leave what's selected in your Maya out of the cache, though you can see it in Maya")
        hide.triggered.connect(lambda: self._maya_cmd("cache_remove_selected", "Remove selected: sent to your Maya"))
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
        rerender = help_menu.addAction("Re-render all", lambda: self._maya_cmd("rerender", "Re-rendering all frames"))
        rerender.setToolTip("Troubleshooting: redo every frame of the cache")
        self.help_menu = help_menu
        self._update_item = help_menu.addAction("Check for updates", self.check_for_update)
        self._update_item.setVisible(bool(self._update_source()))
        self._update_lines = []        # what the last check found, shown under it
        self._update_sep = help_menu.addSeparator()
        about = help_menu.addAction("About bgcache %s (%s)" % (__version__, "Full" if self.has_continuity
                                                               else "Simple"))     # b4: which edition
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
        """Refresh (b21: the one button; Reload scene is in the bgcache menu,
        Re-render all in Help) with its orange note, then Pause."""
        self.b_refresh = _tool("Refresh", tip="Press when the player doesn't match your Maya: sends your viewport "
                                              "settings, layers, shown and hidden objects, unkeyed values on what "
                                              "you've selected and image planes, and asks to reload the scene if "
                                              "it has changed")
        self.b_refresh.setObjectName("refreshButton")
        self.b_refresh.clicked.connect(lambda: self._maya_cmd("refresh", "Refresh sent to your Maya"))
        row.addWidget(self.b_refresh)
        self.refresh_note = QtWidgets.QLabel("")
        self.refresh_note.setObjectName("refreshNote")
        self.refresh_note.setVisible(False)
        row.addWidget(self.refresh_note)
        self.b_pause = _tool("Pause", tip="Pause re-rendering: your edits keep coming in and changed frames "
                                          "stay red. Resume starts again from the frame you're on.")
        self.b_pause.setObjectName("pauseButton")
        self.b_pause.setCheckable(True)
        self.b_pause.clicked.connect(self.set_paused)
        row.addWidget(self.b_pause)

    def _build_reload_question(self):
        """The bar under the toolbar that asks whether to reload the scene
        (b21). In the window, not a dialog: you can keep playing meanwhile."""
        bar = QtWidgets.QFrame()
        bar.setObjectName("reloadQuestion")
        row = QtWidgets.QHBoxLayout(bar)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(12)
        words = QtWidgets.QVBoxLayout()
        words.setSpacing(2)
        self.ask_title, self.ask_text = QtWidgets.QLabel(""), QtWidgets.QLabel("")
        self.ask_title.setObjectName("reloadTitle")
        self.ask_text.setObjectName("reloadText")
        self.ask_text.setWordWrap(True)
        words.addWidget(self.ask_title)
        words.addWidget(self.ask_text)
        row.addLayout(words, 1)
        yes = _tool("Reload scene", tip="Copy your scene to the background Maya again and re-render")
        yes.setObjectName("reloadYes")
        no = _tool("Not now", tip="Keep the cache as it is. The note next to Refresh stays; reload later from "
                                  "the bgcache menu")
        yes.clicked.connect(lambda: self.answer_reload(True))
        no.clicked.connect(lambda: self.answer_reload(False))
        row.addWidget(yes)
        row.addWidget(no)
        bar.setVisible(False)
        self.reload_question = bar
        return bar

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
        self.b_match = _tool("Match Maya", tip="Sync is off and your Maya's playback range (the blue line on the "
                                               "bar) isn't the focus: make the focus the same")
        self.b_match.clicked.connect(self.match_maya_range)
        self.b_match.setVisible(False)

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
        for b in (self.b_loop, self.b_sound, self.b_sync, self.b_match):
            row.addWidget(b)
        row.addSpacing(12)
        row.addWidget(self.status_label, 2)
        row.addSpacing(12)
        self.range_label = FitLabel(elide=Qt.ElideMiddle)
        self.range_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addWidget(self.range_label, 1)
        return tr

    def showEvent(self, event):
        super(Player, self).showEvent(event)
        QtCore.QTimer.singleShot(0, self._scroll_to_live)
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
