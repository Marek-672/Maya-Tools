"""Set up continuity (0.9.0b4): the setup wizard, in the player.

Five steps along the top: Footage · Shots · Sound · Files · Review.

    Footage   "Where does your continuity footage live?" Drop one movie of
              this shot (bgcache learns the folder layout from it: learn.py),
              or "My footage is all over the place" (point at folders; it
              searches them for files named after your shots). Optional: an
              edit export, so shots follow the cut.
    Shots     your sequence in cut (or name) order, what the example path was
              read as, and what's found for every shot and department
              (found / a guess / missing; click one to choose its file).
              Movies need ffmpeg: if there's none, Download it for me.
    Sound     what each shot will play.
    Files     just me, or a team (shared drawings and one setup for
              everyone, in the project folder).
    Review    everything, each with Change; Save and start playing.

Nothing is written until Save. It saves the same settings file a pipeline
TD writes (~/.bgcache/profile.json; a team's goes in the project folder),
and never touches a studio's. Learning and searching run in the
background, so the player keeps playing.
"""
import json
import os
import threading

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:  # Maya 2024 and earlier (PySide2)
    from PySide2 import QtCore, QtGui, QtWidgets

from bgcache import profile
from bgcache.continuity import edit_order, ffmpeg_get, learn, reel, resolver

Qt = QtCore.Qt
STEPS = ("Footage", "Shots", "Sound", "Files", "Review")
ORANGE, BLUE, GREEN, RED, DIM = "#e08a45", "#9cc8ee", "#7cc47c", "#e06c5a", "#9a9a9a"
ROLE_COLOURS = {"shot": ORANGE, "sequence": "#d7b24a", "department": BLUE, "version": GREEN,
                "file": "#cfcfcf", "folder": "#7a7a7a"}
MAX_SHOTS_CHECKED = 40

STYLE = """
QDialog#wizard { background: #1e1e1e; }
QLabel#title { color: #ffffff; font-size: 18px; font-weight: bold; }
QLabel#note { color: #9a9a9a; }
QLabel#bubble { color: #9a9a9a; background: #2a2a2a; border-radius: 11px; padding: 3px 12px; }
QLabel#bubble[state="now"] { color: #1e1e1e; background: #e08a45; font-weight: bold; }
QLabel#bubble[state="done"] { color: #cfe8cf; background: #2e3f2e; }
QFrame#choice { background: #262626; border: 1px solid #3c3c3c; border-radius: 6px; }
QFrame#choice:hover { border-color: #e08a45; }
QFrame#choice[picked="true"] { border: 2px solid #e08a45; background: #2f2721; }
QLabel#choiceTitle { color: #ffffff; font-size: 14px; font-weight: bold; }
QPushButton#primary { background: #e08a45; color: #1e1e1e; font-weight: bold; border: none;
                      border-radius: 3px; padding: 6px 16px; }
QPushButton#primary:hover { background: #f0a060; }
QPushButton#link { background: transparent; border: none; color: #9cc8ee; text-align: left; padding: 0; }
QPushButton#change { min-width: 0; padding: 2px 8px; }
"""


def _label(text, name=None, wrap=True):
    label = QtWidgets.QLabel(text)
    label.setWordWrap(wrap)
    if name:
        label.setObjectName(name)
    return label


def _button(text, slot, name=None, tip=""):
    b = QtWidgets.QPushButton(text)
    if name:
        b.setObjectName(name)
    if tip:
        b.setToolTip(tip)
    b.clicked.connect(lambda *_: slot())
    return b


class Choice(QtWidgets.QFrame):
    """A big clickable answer (title, a line, a small line); drops too."""

    def __init__(self, title, text, small, clicked, dropped=None):
        super(Choice, self).__init__()
        self.setObjectName("choice")
        self.setCursor(Qt.PointingHandCursor)
        self.clicked, self.dropped = clicked, dropped
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.addWidget(_label(title, "choiceTitle"))
        lay.addWidget(_label(text))
        if small:
            lay.addWidget(_label(small, "note"))
        self.setAcceptDrops(dropped is not None)

    def mousePressEvent(self, event):
        self.clicked()

    def set_picked(self, on):
        self.setProperty("picked", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = [u.toLocalFile() for u in event.mimeData().urls() if u.toLocalFile()]
        if urls and self.dropped:
            self.dropped(urls[0])


class Wizard(QtWidgets.QDialog):
    """The setup window. saved: True once Save wrote the settings."""

    def __init__(self, player):
        super(Wizard, self).__init__(player)
        self.setObjectName("wizard")
        self.setWindowTitle("Set up continuity")
        self.setStyleSheet(STYLE)
        self.resize(820, 600)
        self.player, self.cfg = player, player.cfg or {}
        self.scene = self.cfg.get("original_scene") or ""
        self.saved = False
        self.lay = None                # what learn.py worked out
        self.shots = []                # in play order
        self.found = {}                # (shot, department) -> resolved info or None
        self.state = {"edit": "", "by_hand": {}, "ffmpeg": "", "team": False, "project": "",
                      "roots": [], "off": set(), "names": {}}
        self._jobs = []
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(22, 16, 22, 16)
        root.addLayout(self._build_header())
        self.pages = QtWidgets.QStackedWidget()
        root.addWidget(self.pages, 1)
        self.page = {}
        for name, build in (("footage", self._page_footage), ("shots", self._page_shots),
                            ("ffmpeg", self._page_ffmpeg), ("sound", self._page_sound),
                            ("files", self._page_files), ("review", self._page_review)):
            widget = QtWidgets.QWidget()
            build(QtWidgets.QVBoxLayout(widget))
            self.page[name] = self.pages.addWidget(widget)
        self.go("footage")

    # ------------------------------------------------------------ frame
    def _build_header(self):
        top = QtWidgets.QVBoxLayout()
        row = QtWidgets.QHBoxLayout()
        row.addWidget(_label("Set up continuity", "title"))
        row.addStretch(1)
        ids = reel.parse_shot(self.scene)
        row.addWidget(_label("Shot open: %s" % (ids[1] if ids else os.path.basename(self.scene) or "none"),
                             "note", False))
        top.addLayout(row)
        bubbles = QtWidgets.QHBoxLayout()
        self.bubbles = []
        for i, step in enumerate(STEPS):
            b = _label("%d  %s" % (i + 1, step), "bubble", False)
            self.bubbles.append(b)
            bubbles.addWidget(b)
        bubbles.addStretch(1)
        top.addLayout(bubbles)
        return top

    def go(self, name):
        step = {"footage": 0, "shots": 1, "ffmpeg": 1, "sound": 2, "files": 3, "review": 4}[name]
        for i, b in enumerate(self.bubbles):
            b.setText("%s  %s" % ("✓" if i < step else i + 1, STEPS[i]))
            b.setProperty("state", "now" if i == step else "done" if i < step else "")
            b.style().unpolish(b)
            b.style().polish(b)
        enter = getattr(self, "_enter_" + name, None)
        if enter:
            enter()
        self.pages.setCurrentIndex(self.page[name])

    def run(self, work, done, progress=None):
        """work() in a thread (scanning folders must not freeze the player),
        then done(result) here. progress: a label told what's going on."""
        box = {"stop": False}

        def target():
            try:
                box["result"] = work()
            except Exception as error:    # shown in the wizard as a problem, never raised
                box["error"] = str(error)
        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        timer = QtCore.QTimer(self)

        def poll():
            if thread.is_alive():
                return
            timer.stop()
            if "error" in box:
                self._say("problem", box["error"])
            else:
                done(box.get("result"))
        timer.timeout.connect(poll)
        timer.start(60)
        self._jobs.append(box)
        return box

    def _footer(self, lay, back=None, next_text=None, next_slot=None, note=""):
        row = QtWidgets.QHBoxLayout()
        if back:
            row.addWidget(_button("Back", lambda: self.go(back)))
        else:
            row.addWidget(_button("Cancel", self.reject))
        if note:
            row.addWidget(_label(note, "note"))
        row.addStretch(1)
        button = None
        if next_text:
            button = _button(next_text, next_slot, "primary")
            row.addWidget(button)
        lay.addLayout(row)
        return button

    def _say(self, level, text):
        colour = {"ok": GREEN, "guess": ORANGE, "problem": RED}.get(level, DIM)
        self.status.setText('<span style="color:%s">%s</span>' % (colour, text))
        self.status.setVisible(bool(text))

    def closeEvent(self, event):
        profile.use(None)
        super(Wizard, self).closeEvent(event)

    def reject(self):
        profile.use(None)
        for box in self._jobs:
            box["stop"] = True
        super(Wizard, self).reject()

    # ---------------------------------------------------------- Footage
    def _page_footage(self, lay):
        lay.setSpacing(10)
        if profile.is_studio():
            lay.addWidget(_label("Continuity is set up by your studio", "title"))
            lay.addWidget(_label("Its settings are in %s. Ask your pipeline team to change them." %
                                 profile.source()))
            lay.addStretch(1)
            self._footer(lay)
            self.status = _label("")
            return
        lay.addWidget(_label("Where does your continuity footage live?", "title"))
        self.c_movie = Choice("Drop one movie of this shot",
                              "The movies of the shots around yours, from any department. I'll learn the "
                              "folder layout from it and find the rest.",
                              "Best for tidy folders: one folder per shot, department, version",
                              self.pick_movie, self.use_movie)
        self.c_search = Choice("My footage is all over the place",
                               "Point me at the folders. I'll search them for files named after your shots, "
                               "wherever they are.",
                               "Best for dailies dumps, edit exports, mixed MOV and MP4", self.pick_folders,
                               self.use_folder)
        lay.addWidget(self.c_movie)
        lay.addWidget(self.c_search)
        self.ask_row = QtWidgets.QWidget()
        ask = QtWidgets.QHBoxLayout(self.ask_row)
        ask.setContentsMargins(0, 0, 0, 0)
        ask.addWidget(_label("Which shot is this? Type its name as it's written in file names:", wrap=False))
        self.ask_shot = QtWidgets.QLineEdit()
        self.ask_shot.setPlaceholderText("e.g. sh010")
        ask.addWidget(self.ask_shot, 1)
        ask.addWidget(_button("Try again", self._try_again))
        self.ask_row.setVisible(False)
        lay.addWidget(self.ask_row)
        self.status = _label("")
        self.status.setVisible(False)
        lay.addWidget(self.status)
        edit = QtWidgets.QHBoxLayout()
        self.edit_label = _label("Optional: an edit export (EDL or XML) so shots play in cut order", "note")
        edit.addWidget(self.edit_label, 1)
        edit.addWidget(_button("Add edit...", self.pick_edit))
        lay.addLayout(edit)
        lay.addWidget(_button("Joining a team? Use its settings file...", self.join_team, "link"))
        lay.addStretch(1)
        self._footer(lay, note="Anything missed can be given a file by hand later")
        self._pending = None

    def pick_movie(self):
        path = QtWidgets.QFileDialog.getOpenFileName(
            self, "One movie of this shot", os.path.dirname(self.scene),
            "Movies and images (*.mov *.mp4 *.m4v *.jpg *.jpeg *.png *.exr *.tif *.tiff *.dpx);;All files (*)")[0]
        if path:
            self.use_movie(path)

    def use_movie(self, path, known=None):
        self.c_movie.set_picked(True)
        self.c_search.set_picked(False)
        self._pending = ("movie", path)
        self._say("", "Reading the folders around %s..." % os.path.basename(path))
        self.run(lambda: learn.learn(path, self.scene or None, known), self._learned)

    def pick_folders(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "A folder with your footage",
                                                            os.path.dirname(self.scene))
        if folder:
            self.use_folder(folder)

    def use_folder(self, folder, known=None):
        if os.path.isfile(folder):
            folder = os.path.dirname(folder)
        roots = [learn.norm(folder)]
        more = QtWidgets.QMessageBox.question(self, "Set up continuity", "Search another folder too?",
                                              QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                                              QtWidgets.QMessageBox.No)
        while more == QtWidgets.QMessageBox.Yes:
            extra = QtWidgets.QFileDialog.getExistingDirectory(self, "Another folder", folder)
            if not extra:
                break
            roots.append(learn.norm(extra))
            more = QtWidgets.QMessageBox.question(self, "Set up continuity", "Search another folder too?",
                                                  QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                                                  QtWidgets.QMessageBox.No)
        self._search(roots, known)

    def _search(self, roots, known=None):
        self.c_search.set_picked(True)
        self.c_movie.set_picked(False)
        self._pending = ("search", roots)
        shot = known or learn.scene_shot(self.scene)
        if not shot:
            self.ask_row.setVisible(True)
            self._say("guess", "Your scene's name doesn't say which shot it is.")
            return
        sequence = learn._sequence(learn.parts_of(self.scene or shot), shot, None)[0]
        self.state["roots"] = roots
        self._say("", "Searching %s for files named after %s..." % (", ".join(roots), shot))
        held = {}
        held["box"] = self.run(lambda: learn.from_search(roots, shot, sequence,
                                                         stop=lambda: held["box"].get("stop")), self._learned)

    def _try_again(self):
        known = self.ask_shot.text().strip()
        if not known or not self._pending:
            return
        kind, what = self._pending
        (self.use_movie if kind == "movie" else self._search)(what, known)

    def _learned(self, lay):
        problems = [text for level, text in lay["notes"] if level == "problem"]
        if not lay.get("shot") or (problems and not lay["departments"]):
            self.ask_row.setVisible(not lay.get("shot"))
            self._say("problem", problems[0] if problems else "I couldn't work out the shot")
            return
        self.ask_row.setVisible(False)
        self._say("", "")
        self.lay = lay
        self.state["by_hand"] = {}
        self.go("shots")

    def pick_edit(self):
        path = QtWidgets.QFileDialog.getOpenFileName(self, "Your edit export", os.path.dirname(self.scene),
                                                     "Edits (*.edl *.xml *.fcpxml);;All files (*)")[0]
        if path:
            self.state["edit"] = learn.norm(path)
            self.edit_label.setText("Cut order from %s" % os.path.basename(path))

    def join_team(self):
        path = QtWidgets.QFileDialog.getOpenFileName(self, "The team's settings file (bgcache/settings.json)",
                                                     os.path.dirname(self.scene), "Settings (*.json)")[0]
        if not path:
            return
        project = learn.norm(os.path.dirname(os.path.dirname(path)))
        project = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Where is the project folder on this computer?", project) or project
        own = _read_json(profile.personal_path())
        own.update(team_settings=learn.norm(path), project_folder=learn.norm(project))
        _write_json(profile.personal_path(), own)
        profile.use(None)
        profile.load(force=True)
        self.saved = True
        self.accept()

    # ------------------------------------------------------------ Shots
    def _page_shots(self, lay):
        lay.setSpacing(8)
        self.shots_title = _label("Your sequence", "title")
        lay.addWidget(self.shots_title)
        self.shots_order = _label("", "note")
        lay.addWidget(self.shots_order)
        self.shot_list = QtWidgets.QLabel()
        self.shot_list.setWordWrap(True)
        self.shot_list.setTextFormat(Qt.RichText)
        lay.addWidget(self.shot_list)
        self.chips = QtWidgets.QLabel()
        self.chips.setTextFormat(Qt.RichText)
        self.chips.setWordWrap(True)
        lay.addWidget(self.chips)
        lay.addWidget(_label("What I found", "title"))
        self.depts_box = QtWidgets.QHBoxLayout()
        lay.addLayout(self.depts_box)
        self.summary = _label("", "note")
        lay.addWidget(self.summary)
        self.table = QtWidgets.QTableWidget()
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.table.verticalHeader().setVisible(True)
        self.table.cellClicked.connect(self._cell_clicked)
        lay.addWidget(self.table, 1)
        lay.addWidget(_label("Click a ⚠ or ✗ to choose that shot's file. Missing footage is fine: "
                             "that shot just plays without it.", "note"))
        self._footer(lay, "footage", "Next: Sound", self._after_found)

    def candidate(self):
        """The settings as they'd be saved (the profile's format)."""
        prof = learn.to_profile(self.lay)
        depts = []
        for d in prof["departments"]:
            if d["name"] in self.state["off"]:
                continue
            d = dict(d, name=self.state["names"].get(d["name"], d["name"]))
            depts.append(d)
        prof["departments"] = depts
        prof["auto_order"] = [d["name"] for d in depts]
        if self.state["edit"]:
            prof["edit_order"] = self.state["edit"]
        by_hand = {}
        for (shot, dept), path in self.state["by_hand"].items():
            by_hand.setdefault(shot, {})[self.state["names"].get(dept, dept)] = path
        if by_hand:
            prof["footage_by_hand"] = by_hand
        if self.state["ffmpeg"]:
            prof["ffmpeg"] = self.state["ffmpeg"]
        if self.state["team"] and self.state["project"]:
            prof["drawings_folder"] = learn.norm(self.state["project"]) + "/bgcache/drawings/{shot}"
        return prof

    def _enter_shots(self):
        lay = self.lay
        self.shots_title.setText("Your sequence%s" % (", in cut order" if self.state["edit"] else ""))
        self.chips.setText(self._chips_html())
        self._build_dept_row()
        self.table.clear()
        self.table.setRowCount(0)
        self.summary.setText("Looking for every shot's footage...")
        profile.use(self.candidate())
        seq = lay["sequence"] or lay["shot"]
        self.run(lambda: self._resolve_all(seq), self._show_found)

    def _resolve_all(self, seq):
        shots = resolver.list_shots_in_sequence("", seq) or list(self.lay["shots"])
        if self.lay["shot"] not in shots and self.lay["shot"].lower() not in [s.lower() for s in shots]:
            shots.append(self.lay["shot"])
        names = [d["name"] for d in resolver.get_departments()]
        found = {}
        for shot in shots[:MAX_SHOTS_CHECKED]:
            for name in names:
                found[(shot, name)] = resolver.resolve_shot("", shot, name)
        return shots, names, found

    def _show_found(self, result):
        shots, names, found = result
        self.shots, self.found = shots, found
        live = self.lay["shot"].lower()
        self.shot_list.setText("  ".join(
            '<span style="color:%s">%s%s</span>' % (ORANGE if s.lower() == live else "#dddddd", s,
                                                  " (yours)" if s.lower() == live else "") for s in shots))
        self.shots_order.setText(
            "Order from your edit: %s" % os.path.basename(self.state["edit"]) if self.state["edit"]
            else "In name order. Add an edit export on the Footage step to follow the cut.")
        checked = shots[:MAX_SHOTS_CHECKED]
        self.table.setColumnCount(len(names))
        self.table.setHorizontalHeaderLabels(names)
        self.table.setRowCount(len(checked))
        self.table.setVerticalHeaderLabels(checked)
        counts = {"found": 0, "guess": 0, "missing": 0}
        for r, shot in enumerate(checked):
            for c, name in enumerate(names):
                kind, text = self._cell(shot, name, found.get((shot, name)))
                counts[kind] += 1
                item = QtWidgets.QTableWidgetItem(text)
                item.setForeground(QtGui.QColor({"found": GREEN, "guess": ORANGE, "missing": RED}[kind]))
                self.table.setItem(r, c, item)
        self.table.resizeColumnsToContents()
        self.counts = counts
        self.summary.setText("%d found · %d guesses · %d missing" %
                             (counts["found"], counts["guess"], counts["missing"]))

    def _cell(self, shot, name, info):
        if not info:
            return "missing", "✗ none"
        original = next((k for k, v in self.state["names"].items() if v == name), name)
        how = "by hand" if (shot, original) in self.state["by_hand"] else \
            "search" if any(d.get("search_roots") for d in resolver.get_departments() if d["name"] == name) \
            else "pattern"
        kind = "image" if info["source_type"] == "image_sequence" else \
            os.path.splitext(info["source_path"])[1].lstrip(".").lower()
        version = info.get("version")
        if not version:
            return "guess", "⚠ newest file · %s" % kind
        return "found", "✓ v%03d · %s · %s" % (version, kind, how)

    def _chips_html(self):
        if not self.lay.get("chips"):
            roots = ", ".join(self.state["roots"])
            return '<span style="color:%s">Searching %s for files named like %s</span>' % (DIM, roots,
                                                                                          self.lay["shot"])
        out = []
        for text, role, sure in self.lay["chips"]:
            colour = ROLE_COLOURS.get(role, DIM)
            tag = "" if role == "folder" else '<sub style="color:%s"> %s%s</sub>' % (
                DIM, role, "?" if not sure else "")
            out.append('<span style="color:%s">%s</span>%s' % (colour, text, tag))
        return "Read as: " + ' <span style="color:#555">/</span> '.join(out)

    def _build_dept_row(self):
        while self.depts_box.count():
            item = self.depts_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.depts_box.addWidget(_label("Departments:", wrap=False))
        for d in self.lay["departments"]:
            box = QtWidgets.QCheckBox(self.state["names"].get(d["name"], d["name"]))
            box.setChecked(d["name"] not in self.state["off"])
            box.setToolTip("Untick to leave it out. Double-click the name in the table to rename it.\n"
                           "Example: %s" % d.get("example", ""))
            box.toggled.connect(lambda on, n=d["name"]: self._toggle_dept(n, on))
            self.depts_box.addWidget(box)
        rename = _button("Rename...", self._rename_dept)
        self.depts_box.addWidget(rename)
        self.depts_box.addStretch(1)

    def _toggle_dept(self, name, on):
        (self.state["off"].discard if on else self.state["off"].add)(name)
        self._enter_shots()

    def _rename_dept(self):
        current = [d["name"] for d in self.lay["departments"] if d["name"] not in self.state["off"]]
        if not current:
            return
        pick, ok = QtWidgets.QInputDialog.getItem(self, "Rename", "Department:", current, 0, False)
        if not ok:
            return
        new, ok = QtWidgets.QInputDialog.getText(self, "Rename", "Short name shown on the strip:",
                                                 text=self.state["names"].get(pick, pick))
        if ok and new.strip():
            self.state["names"][pick] = new.strip()
            self._enter_shots()

    def _cell_clicked(self, row, col):
        shot = self.table.verticalHeaderItem(row).text()
        dept = self.table.horizontalHeaderItem(col).text()
        original = next((k for k, v in self.state["names"].items() if v == dept), dept)
        menu = QtWidgets.QMenu(self)
        menu.addAction("Choose the file for %s · %s..." % (shot, dept),
                       lambda: self._choose_file(shot, original))
        if (shot, original) in self.state["by_hand"]:
            menu.addAction("Forget the chosen file", lambda: self._forget_file(shot, original))
        info = self.found.get((shot, dept))
        if info:
            menu.addAction("Show in folder", lambda: QtGui.QDesktopServices.openUrl(
                QtCore.QUrl.fromLocalFile(os.path.dirname(info["source_path"]))))
        (getattr(menu, "exec", None) or menu.exec_)(QtGui.QCursor.pos())

    def _choose_file(self, shot, dept):
        start = os.path.dirname(self.lay.get("example") or self.scene)
        path = QtWidgets.QFileDialog.getOpenFileName(
            self, "The movie for %s" % shot, start,
            "Movies and images (*.mov *.mp4 *.m4v *.jpg *.jpeg *.png *.exr *.tif *.tiff *.dpx)")[0]
        if path:
            self.state["by_hand"][(shot, dept)] = learn.norm(path)
            self._enter_shots()

    def _forget_file(self, shot, dept):
        self.state["by_hand"].pop((shot, dept), None)
        self._enter_shots()

    def _after_found(self):
        movies = any(d["source_type"] == "single_movie" for d in self.candidate()["departments"])
        if movies and not (self.state["ffmpeg"] or ffmpeg_get.find()):
            self.go("ffmpeg")
        else:
            self.go("sound")

    # ----------------------------------------------------------- ffmpeg
    def _page_ffmpeg(self, lay):
        lay.setSpacing(10)
        lay.addWidget(_label("Movies need ffmpeg, a free video tool", "title"))
        lay.addWidget(_label("It isn't on this computer. bgcache uses it to turn your movies into frames it "
                             "can play."))
        build = ffmpeg_get.build_for_this_computer()
        size = " · about %d MB" % (build[2] // 1000000) if build else ""
        self.b_download = _button("Download it for me%s" % size, self._download, "primary")
        self.b_download.setEnabled(ffmpeg_get.can_download())
        lay.addWidget(self.b_download)
        lay.addWidget(_button("I have it: show me where", self._locate_ffmpeg))
        lay.addWidget(_button("Skip: image sequences only", lambda: self.go("sound")))
        self.ff_progress = QtWidgets.QProgressBar()
        self.ff_progress.setVisible(False)
        lay.addWidget(self.ff_progress)
        self.ff_note = _label("Goes into ~/.bgcache/ffmpeg only: no admin rights, nothing else on your computer "
                              "changes. A fixed build (ffmpeg 7.0.2, from the ffmpeg-static project), checked "
                              "before use. ffmpeg is free software under the GPL.", "note")
        lay.addWidget(self.ff_note)
        if not ffmpeg_get.can_download():
            self.ff_note.setText("Downloading isn't available here: install ffmpeg, then show me where it is.")
        lay.addStretch(1)
        self._footer(lay, "shots")

    def _download(self):
        self.b_download.setEnabled(False)
        self.ff_progress.setVisible(True)
        self.ff_progress.setRange(0, 100)
        shared = {"done": 0, "total": 1}
        timer = QtCore.QTimer(self)
        timer.timeout.connect(lambda: self.ff_progress.setValue(int(100 * shared["done"] / max(1, shared["total"]))))
        timer.start(100)
        held = {}

        def work():
            return ffmpeg_get.download(progress=lambda d, t: shared.update(done=d, total=t),
                                       stop=lambda: held["box"].get("stop"))

        def done(path):
            timer.stop()
            self.state["ffmpeg"] = ""            # bgcache's own copy is found without a setting
            self.ff_note.setText('<span style="color:%s">✓ ffmpeg is ready (%s)</span>' % (GREEN, path))
            QtCore.QTimer.singleShot(800, lambda: self.go("sound"))
        self.status = self.ff_note
        held["box"] = self.run(work, done)

    def _locate_ffmpeg(self):
        path = QtWidgets.QFileDialog.getOpenFileName(self, "ffmpeg", os.path.expanduser("~"))[0]
        if path and ffmpeg_get.works(path):
            self.state["ffmpeg"] = learn.norm(path)
            self.go("sound")
        elif path:
            QtWidgets.QMessageBox.warning(self, "ffmpeg", "That file doesn't run as ffmpeg.")

    # ------------------------------------------------------------ Sound
    def _page_sound(self, lay):
        lay.setSpacing(10)
        lay.addWidget(_label("Sound", "title"))
        self.sound_text = QtWidgets.QLabel()
        self.sound_text.setTextFormat(Qt.RichText)
        self.sound_text.setWordWrap(True)
        lay.addWidget(self.sound_text)
        lay.addStretch(1)
        self._footer(lay, "shots", "Next: Files", lambda: self.go("files"))

    def _enter_sound(self):
        audio = (self.cfg.get("audio") or {}).get("path")
        live = self.lay["shot"]
        others = [s for s in self.shots if s.lower() != live.lower()]
        if not audio:
            self.sound_text.setText("Your shot has no sound in Maya, so every shot plays its movie's own sound "
                                    "(when the movie has some).")
            return
        self.sound_text.setText("Checking sound for %d shots..." % len(others))

        def work():
            template = reel.audio_template(audio, live)
            return template, {s: reel.find_shot_audio(template, live, s) for s in others[:MAX_SHOTS_CHECKED]}

        self.run(work, self._show_sound)

    def _show_sound(self, result):
        template, found = result
        have = [s for s, p in found.items() if p]
        missing = [s for s, p in found.items() if not p]
        lines = []
        if template:
            lines.append('<span style="color:%s">✓ %d of %d shots have a sound file like yours</span> '
                         '(in %s, newest version)' % (GREEN, len(have), len(found), template[0]))
        else:
            lines.append("Your shot's sound isn't in a versioned folder, so I can't look for the other shots' "
                         "sound the same way.")
        if missing or not template:
            names = ", ".join((missing or list(found))[:12])
            lines.append('<span style="color:%s">%s</span> play their movie\'s own sound, when it has '
                         'some.' % (ORANGE, names))
        self.sound_text.setText("<br><br>".join(lines))

    # ------------------------------------------------------------ Files
    def _page_files(self, lay):
        lay.setSpacing(10)
        lay.addWidget(_label("Who's working on this film?", "title"))
        self.c_me = Choice("Just me", "Drawings next to my scenes. Settings on this computer.", "",
                           lambda: self._team(False))
        self.c_team = Choice("A team", "Shared drawings, everyone sees each other's notes. One setup for "
                             "everyone.", "", lambda: self._team(True))
        lay.addWidget(self.c_me)
        lay.addWidget(self.c_team)
        self.team_box = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(self.team_box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setColumnStretch(1, 1)
        self.project_label = _label("")
        grid.addWidget(_label("Project folder", wrap=False), 0, 0)
        grid.addWidget(self.project_label, 0, 1)
        grid.addWidget(_button("Change", self._pick_project, "change"), 0, 2)
        self.team_paths = _label("", "note")
        grid.addWidget(self.team_paths, 1, 0, 1, 3)
        lay.addWidget(self.team_box)
        lay.addWidget(_label("Converted movies: %s (this computer only)" % reel.CACHE_ROOT, "note"))
        lay.addStretch(1)
        self._footer(lay, "sound", "Next: Review", lambda: self.go("review"))

    def _enter_files(self):
        if not self.state["project"]:
            paths = [p for p in [self.scene, self.lay.get("example")] + self.state["roots"] if p]
            common_root = os.path.commonpath([learn.norm(p) for p in paths]) if len(paths) > 1 else ""
            self.state["project"] = learn.norm(common_root) if len(learn.parts_of(common_root)) > 2 else ""
        self._team(self.state["team"])

    def _team(self, on):
        self.state["team"] = on
        self.c_me.set_picked(not on)
        self.c_team.set_picked(on)
        self.team_box.setVisible(on)
        project = self.state["project"] or "(choose)"
        self.project_label.setText(project)
        self.team_paths.setText(
            "Shared drawings: %s/bgcache/drawings/&lt;shot&gt;/<br>Team settings: %s/bgcache/settings.json "
            "· everyone who uses them gets this setup. On another computer (a Mac, say) the project "
            "folder may be somewhere else: each computer says where the first time." % (project, project))

    def _pick_project(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "The project folder", self.state["project"])
        if folder:
            self.state["project"] = learn.norm(folder)
            self._team(True)

    # ----------------------------------------------------------- Review
    def _page_review(self, lay):
        lay.setSpacing(8)
        lay.addWidget(_label("Here's everything before you start", "title"))
        self.review_grid = QtWidgets.QGridLayout()
        self.review_grid.setColumnStretch(1, 1)
        lay.addLayout(self.review_grid)
        lay.addStretch(1)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(_button("Back", lambda: self.go("files")))
        row.addStretch(1)
        row.addWidget(_button("Save a copy...", self.save_copy))
        row.addWidget(_button("Save and start playing", self.save, "primary"))
        lay.addLayout(row)

    def _review_rows(self):
        prof = self.candidate()
        counts = getattr(self, "counts", {"found": 0, "guess": 0, "missing": 0})
        depts = prof["departments"]
        how = "searching %s" % ", ".join(self.state["roots"]) if any(d.get("search_roots") for d in depts) \
            else "learned from %s" % os.path.basename(self.lay.get("example") or "")
        ffmpeg = self.state["ffmpeg"] or ffmpeg_get.find()
        team = ("Shared drawings and settings for everyone in %s/bgcache" % self.state["project"]
                if self.state["team"] else "Just me: drawings next to my scenes, settings on this computer")
        return [
            ("Shots", "%s · %s" % (", ".join(self.shots[:14]) + (" ..." if len(self.shots) > 14 else ""),
                                        "cut order from %s" % os.path.basename(self.state["edit"])
                                        if self.state["edit"] else "name order"), "footage"),
            ("Footage", "✓ %d found  ⚠ %d guesses  ✗ %d missing · %s · %s" % (
                counts["found"], counts["guess"], counts["missing"], ", ".join(d["name"] for d in depts), how),
             "shots"),
            ("By hand", "%d shots given a file by hand" % len(self.state["by_hand"]), "shots"),
            ("Sound", self.sound_text.text().split("<br>")[0] or "—", "sound"),
            ("ffmpeg", "✓ %s" % ffmpeg if ffmpeg else "none: movies won't play (image sequences will)",
             "ffmpeg"),
            ("Team", team, "files"),
            ("Saved in", self._save_target(), "files"),
        ]

    def _enter_review(self):
        while self.review_grid.count():
            item = self.review_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for r, (name, text, page) in enumerate(self._review_rows()):
            self.review_grid.addWidget(_label("<b>%s</b>" % name, wrap=False), r, 0)
            value = _label(text)
            value.setTextFormat(Qt.RichText)
            self.review_grid.addWidget(value, r, 1)
            self.review_grid.addWidget(_button("Change", lambda p=page: self.go(p), "change"), r, 2)

    def _save_target(self):
        if self.state["team"] and self.state["project"]:
            return "%s/bgcache/settings.json (the team) and %s (this computer)" % (
                self.state["project"], profile.personal_path())
        return profile.personal_path()

    def save(self):
        prof = self.candidate()
        own = _read_json(profile.personal_path())
        for key in ("team_settings", "project_folder"):
            own.pop(key, None)
        if self.state["team"] and self.state["project"]:
            team_file = learn.norm(self.state["project"]) + "/bgcache/settings.json"
            _write_json(team_file, learn.relative_to(prof, self.state["project"]))
            for key in prof:
                own.pop(key, None)
            own.update(team_settings=team_file, project_folder=learn.norm(self.state["project"]))
            if prof.get("scenes_by_hand"):
                own["scenes_by_hand"] = prof["scenes_by_hand"]
        else:
            own.update(prof)
        _write_json(profile.personal_path(), own)
        profile.use(None)
        profile.load(force=True)
        self.saved = True
        self.accept()

    def save_copy(self):
        path = QtWidgets.QFileDialog.getSaveFileName(self, "Save a copy of the settings",
                                                     os.path.expanduser("~/bgcache_settings.json"),
                                                     "Settings (*.json)")[0]
        if path:
            prof = self.candidate()
            if self.state["team"] and self.state["project"]:
                prof = learn.relative_to(prof, self.state["project"])
            _write_json(path, prof)


def _read_json(path):
    try:
        with open(path) as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (IOError, OSError, ValueError):
        return {}


def _write_json(path, data):
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w") as handle:
        json.dump(data, handle, indent=2)       # people read and share these files
    os.replace(tmp, path)
