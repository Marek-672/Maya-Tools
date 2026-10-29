"""Continuity add-on for the bgcache player: the shot strip.

The strip lists your sequence's shots. Tick a shot's checkbox and it plays
with yours as one reel, with its own sound: shots left of yours play before
it, shots right of it play after. Your shot's card is outlined orange, ticked
shots blue (and blue on the cache bar). Right-click a shot to pick its
department; on your own card, show a department's movie instead of the live
cache or put it in Maya as an image plane.

Where shots and footage are comes from the pipeline profile
(bgcache/profile.py). Without this folder installed, the player simply has
no Continuity button.

Continuity is mixed into the Player class (bgcache/player.py); the hooks
below (_init_continuity, _continuity_buttons, ...) are the ones the player
calls, with do-nothing versions in player.NoContinuity.
"""
import collections
import os

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:  # Maya 2024 and earlier (PySide2)
    from PySide2 import QtCore, QtGui, QtWidgets

from bgcache import profile
from bgcache.continuity import reel
from bgcache.widgets import FitLabel, _checkbox_style, _tool

NEWER_CHECK_MS = 120000      # how often the strip looks for newer footage
VERSIONS_LISTED = 10         # versions per department in the menu (More versions... for the rest)

Qt = QtCore.Qt

STYLE = """
QWidget#stripHeader { background: #202020; }
QWidget#stripBody { background: #1b1b1b; }
QFrame#card { background: #262626; border: 1px solid #3a3a3a; border-radius: 4px; }
QToolButton#deptButton { background: transparent; border: none; border-radius: 3px;
                         color: #a8a8a8; padding: 0px 3px; font-size: 12px; }
QToolButton#deptButton:hover { background: #3a3a3a; color: #ffffff; }
QToolButton#deptButton[override="true"] { color: #9cc8ee; }
QToolButton#deptButton[newer="true"] { color: #e8a040; font-weight: bold; }
QFrame#card[live="true"] QToolButton#deptButton[override="false"] { color: #f0c890; }
QFrame#card[staged="true"] { background: #22303c; border: 2px solid #4f9bd9; }
QFrame#card[live="true"] { background: #3a2e20; border: 2px solid #e8a33d; }
"""


# --------------------------------------------------------------------------
# Shot strip widgets
# --------------------------------------------------------------------------
class ShotCard(QtWidgets.QFrame):
    def __init__(self, player, shot, live=False):
        super(ShotCard, self).__init__()
        self.player, self.shot, self.live = player, shot, live
        self.setObjectName("card")
        self.setProperty("live", "true" if live else "false")
        self.setFixedSize(184, 90)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(5, 5, 5, 5)
        lay.setSpacing(3)
        self.thumb = QtWidgets.QLabel("live cache" if live else "finding footage...")
        self.thumb.setFixedSize(172, 60)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setStyleSheet("background: %s; color: %s; font-size: 11px"
                                 % (("#4a3a26", "#f0c890") if live else ("#31363d", "#8d96a3")))
        lay.addWidget(self.thumb)
        row = QtWidgets.QHBoxLayout()
        self.name = QtWidgets.QLabel(shot)
        # Department label doubles as a dropdown: click to pick another department
        self.dept = QtWidgets.QToolButton()
        self.dept.setObjectName("deptButton")
        self.dept.setFocusPolicy(Qt.NoFocus)
        self.dept.setCursor(Qt.PointingHandCursor)
        if live:
            self.dept.setToolTip("Show this shot live, or as one department's movie. "
                                 "Also puts that movie in Maya as an image plane.")
            self.dept.setText("Live  \u25be")
            self.dept.clicked.connect(lambda: player.live_menu(
                self.dept.mapToGlobal(QtCore.QPoint(0, self.dept.height()))))
        else:
            self.dept.setToolTip("Pick which department's footage to use (or right-click the card)")
            self.dept.setText("...  \u25be")
            self.dept.clicked.connect(lambda: player.department_menu(
                shot, self.dept.mapToGlobal(QtCore.QPoint(0, self.dept.height()))))
        if live:
            self.name.setStyleSheet("font-weight: bold; color: #f5d7a8")
        row.addWidget(self.name)
        row.addStretch(1)
        row.addWidget(self.dept)
        lay.addLayout(row)
        self.check = None
        if not live:
            # Small checkbox over the thumbnail's top-left corner: include this
            # shot in the reel. Before/after follows its place in the filmstrip.
            self.check = QtWidgets.QCheckBox(self.thumb)
            self.check.setFocusPolicy(Qt.NoFocus)
            self.check.setCursor(Qt.PointingHandCursor)
            self.check.setToolTip("Play this shot with yours (before or after, by its place in the sequence)")
            self.check.setStyleSheet(_checkbox_style())
            self.check.move(5, 5)
            self.check.clicked.connect(lambda on: player.stage(shot, on))

    def set_info(self, info, image, text=None):
        if image is not None and not image.isNull():
            self.thumb.setPixmap(QtGui.QPixmap.fromImage(image))
        else:
            self.thumb.setText(text or ("no footage" if not info else "no thumbnail"))
        self.set_dept(info)

    def set_dept(self, info):
        """Department + version on the dropdown, blue if picked by hand
        (on your own shot: "Live", or the reference movie in blue)."""
        if self.live:
            self.dept.setText("%s  \u25be" % (reel.label(info) if info else "Live"))
            override = bool(info)
        else:
            newer = self.player.newer.get(self.shot) if info else None
            text = reel.label(info) if info else "none"
            if newer:      # newer footage has come in: "P v012 -> v013"
                text += " \u2192 v%03d" % newer["version"] if newer["department"] == info["department"] \
                    else " \u2192 %s" % reel.label(newer)
            pin = self.player.version_pin.get(self.shot)
            if pin is not None and info:
                text += " (pinned)"
            self.dept.setText("%s  \u25be" % text)
            override = self.shot in self.player.dept_override
            self.dept.setProperty("newer", "true" if newer else "false")
            self.dept.setToolTip("Newer footage is in: pick \"Update\" in this menu" if newer else
                                 "Pick which department's footage to use, or a version (or right-click the card)")
        self.dept.setProperty("override", "true" if override else "false")
        self.dept.style().unpolish(self.dept)
        self.dept.style().polish(self.dept)

    def set_progress(self, text):
        self.thumb.setPixmap(QtGui.QPixmap())
        self.thumb.setText(text)
        self.set_reference_tag(None)

    def set_reference_tag(self, text):
        """Your own shot showing a department's movie instead of Live: an
        orange "REF · P v012" tag over its thumbnail, so it's obvious."""
        tag = getattr(self, "ref_tag", None)
        if not text:
            if tag is not None:
                tag.hide()
            return
        if tag is None:
            tag = self.ref_tag = QtWidgets.QLabel(self.thumb)
            tag.setStyleSheet("background: rgba(184, 102, 42, 230); color: #fff4e8; font-size: 10px;"
                              " font-weight: bold; padding: 1px 5px; border-radius: 3px")
            tag.move(4, 4)
        tag.setText(text)
        tag.adjustSize()
        tag.show()
        tag.raise_()

    def set_reference(self, image, label):
        """Thumbnail of the reference movie with its REF tag."""
        if image is not None and not image.isNull():
            self.thumb.setPixmap(QtGui.QPixmap.fromImage(image))
        else:
            self.thumb.setText("reference: %s" % label)
        self.set_reference_tag("REF \u00b7 %s" % label)

    def set_staged(self, side):
        if self.live:
            return
        self.check.blockSignals(True)
        self.check.setChecked(bool(side))
        self.check.blockSignals(False)
        self.setProperty("staged", "true" if side else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def contextMenuEvent(self, event):
        if self.live:
            self.player.live_menu(event.globalPos())
        else:
            self.player.department_menu(self.shot, event.globalPos())


class ShotBrowser(QtWidgets.QWidget):
    def __init__(self, player):
        super(ShotBrowser, self).__init__()
        self.player = player
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        header = QtWidgets.QWidget()
        header.setObjectName("stripHeader")
        header.setFixedHeight(26)
        row = QtWidgets.QHBoxLayout(header)
        row.setContentsMargins(8, 2, 8, 2)
        row.setSpacing(12)
        # b14: the one Continuity switch lives here (lit = on); the arrow
        # folds the shot cards away while continuity stays on.
        self.switch = _tool("Continuity", True, "Play the staged shots before and after yours")
        self.toggle = _tool(tip="Show/hide the shot cards (C)")
        self.toggle.setArrowType(Qt.UpArrow)
        self.toggle.clicked.connect(player.toggle_browser)
        self.info = FitLabel()
        self.refresh_all = _tool("Update footage", tip="Check every shot on the strip for newer or "
                                 "re-published movies, and load the ones that changed")
        self.refresh_all.clicked.connect(lambda *_: player.refresh_all_footage())
        self.untick = _tool("Untick all", tip="Take every ticked shot out of the reel")
        self.untick.setEnabled(False)
        self.untick.clicked.connect(lambda *_: player.untick_all())
        row.addWidget(self.switch)
        row.addWidget(self.toggle)
        row.addWidget(self.info, 1)
        row.addWidget(self.refresh_all)
        row.addWidget(self.untick)
        lay.addWidget(header)
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setFixedHeight(116)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setWidgetResizable(True)
        body = QtWidgets.QWidget()
        body.setObjectName("stripBody")
        self.cards_layout = QtWidgets.QHBoxLayout(body)
        self.cards_layout.setContentsMargins(8, 6, 8, 6)
        self.cards_layout.setSpacing(8)
        self.cards_layout.addStretch(1)
        self.scroll.setWidget(body)
        lay.addWidget(self.scroll)
        self.cards = {}

    def set_open(self, is_open, on=True):
        self.scroll.setVisible(bool(is_open and on))
        self.toggle.setArrowType(Qt.UpArrow if is_open else Qt.DownArrow)
        self.toggle.setVisible(bool(on))
        self.refresh_all.setEnabled(bool(on))
        self.info.setVisible(bool(on))

    def add_card(self, card):
        self.cards[card.shot] = card
        self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)

    def wheelEvent(self, event):   # mouse wheel scrolls the strip sideways
        bar = self.scroll.horizontalScrollBar()
        bar.setValue(bar.value() - event.angleDelta().y())


# --------------------------------------------------------------------------
# The player's continuity part
# --------------------------------------------------------------------------
class Continuity(object):
    has_continuity = True

    # ---------------------------------------------------------------- hooks
    def _init_continuity(self):
        self.reel_mod = reel
        self.shot_ids = reel.parse_shot(self.cfg.get("original_scene")) or \
            reel.parse_shot((self.cfg.get("audio") or {}).get("path"))
        self.live_shot = self.shot_ids[1] if self.shot_ids else None
        mine = self.prefs.get("shots", {}).get(self.live_shot or "", {})
        # ticked shots last while the player is open; every Start begins with
        # none (they used to be remembered per shot)
        self.staged = {"before": [], "after": []}
        self.dept_override = dict(mine.get("dept", {}))
        self.version_pin = {k: int(v) for k, v in (mine.get("pins") or {}).items()}   # shot -> pinned version
        self.newer = {}                                # shot -> newer footage found since it was resolved
        self.live_ref = mine.get("live_ref")           # department shown for YOUR shot, None = live
        self.live_ref_last = self.live_ref or mine.get("live_ref_last")
        self.live_ref_ready = None                     # {"info", "frames"} once converted
        self._live_gen = 0
        self.plane_mode = None                         # Maya image plane: "front", "behind" or None
        self.continuity_on = bool(self.prefs.get("continuity", True)) and bool(self.shot_ids)
        self.browser_open = bool(self.prefs.get("browser_open", True))
        self.shots = []           # sequence order
        self.infos = {}           # shot -> resolved info
        self.prepared = {}        # shot -> prepare_shot result
        self.preparing = set()
        self.generation = collections.Counter()   # bumps when a shot's department changes
        self.failed = {}
        self.jobs = reel.Jobs()

    def _continuity_buttons(self):
        """b14: nothing on the toolbar; the Continuity switch is on the strip's header."""
        return []

    def _continuity_widget(self, lay):
        """The shot strip, under the toolbar."""
        self.setStyleSheet(self.styleSheet() + STYLE)
        self.browser = ShotBrowser(self)
        self.b_cont = self.browser.switch
        self.b_cont.setChecked(self.continuity_on)
        self.b_cont.setEnabled(bool(self.shot_ids))
        if not self.shot_ids:
            where = profile.get("shot_folder")
            self.b_cont.setToolTip("Continuity needs a scene inside a shot folder (%s)" % where if where else
                                   "Continuity needs a pipeline profile that says where shots are")
        self.b_cont.clicked.connect(lambda *_: self.toggle_continuity())
        if self.shot_ids:
            self.browser.add_card(ShotCard(self, self.live_shot, live=True))
            self.browser.info.setText("%s · finding shots..." % self.shot_ids[2])
        lay.addWidget(self.browser)

    def _continuity_ready(self):
        """End of the player's UI building."""
        self._apply_continuity_visibility()
        self.browser.scroll.horizontalScrollBar().rangeChanged.connect(self._center_now)

    def _continuity_start(self):
        """After the player's first reel: find the sequence's shots."""
        if self.shot_ids:
            self._list_shots()
        # tidy the continuity cache in the background (lowest priority)
        self.jobs.add(9, lambda report: reel.prune_cache(), lambda kind, value: None)
        self.job_timer = QtCore.QTimer(self)
        self.job_timer.timeout.connect(self.jobs.drain)
        self.job_timer.start(100)
        # every 2 minutes: has newer footage come in for the shots on the strip?
        self.newer_timer = QtCore.QTimer(self)
        self.newer_timer.timeout.connect(self._check_newer)
        self.newer_timer.start(NEWER_CHECK_MS)

    def _continuity_height(self):
        return 26 + (116 if self.browser_open and self.continuity_on else 0)

    def _continuity_prefs(self):
        shots = self.prefs.setdefault("shots", {})
        if self.live_shot:
            shots[self.live_shot] = {"dept": self.dept_override, "pins": self.version_pin,
                                     "live_ref": self.live_ref,
                                     "live_ref_last": self.live_ref_last}
        self.prefs["continuity"] = self.continuity_on
        self.prefs["browser_open"] = self.browser_open

    def _footage_label(self, info):
        return reel.label(info)

    def _apply_continuity_visibility(self):
        self.browser.setVisible(True)            # the header (and its switch) always shows
        self.browser.set_open(self.browser_open, self.continuity_on)

    # ---------------------------------------------------------------- browser
    def _list_shots(self):
        show, shot, seq = self.shot_ids

        def done(kind, value):
            if kind != "done":
                self.browser.info.setText("%s · %s" % (seq, value if kind == "error" else ""))
                return
            self.shots = value if shot in value else sorted(value + [shot])
            self.browser.info.setText("%s · %d shots" % (seq, len(self.shots)))
            for name in self.shots:
                if name != shot:
                    self.browser.add_card(ShotCard(self, name))
            # keep the live card in sequence order
            live = self.browser.cards.get(shot)
            if live:
                self.browser.cards_layout.removeWidget(live)
                self.browser.cards_layout.insertWidget(self.shots.index(shot), live)
            for name in self.shots:
                if name != shot:
                    self._resolve(name)
            remembered = self.staged["before"] + self.staged["after"]
            self.staged = {"before": [], "after": []}
            for name in remembered:
                if name in self.shots and name != shot:
                    self.staged[self._side(name)].append(name)
                    self._prepare(name)
            self._save_prefs()
            self._refresh_cards()
            if self.live_ref:
                self._prepare_live_ref()
            QtCore.QTimer.singleShot(0, self._scroll_to_live)

        self.jobs.add(1, lambda report: self.reel_mod.cr.list_shots_in_sequence(show, seq), done)

    def _scroll_to_live(self):
        """Centre your shot's card in the strip. Qt lays the cards out later,
        so this asks for centring and _center_now does it once the strip's
        scroll range is known (it's called again when the range changes)."""
        self._center_pending = True
        self._center_now()

    def _center_now(self, *args):
        if not getattr(self, "_center_pending", False) or not self.shots:
            return
        if not self.browser.isVisible() or not self.browser.scroll.isVisible():
            return
        lay = self.browser.cards_layout
        margin = lay.contentsMargins().left()
        spacing = lay.spacing()
        n = len(self.shots)
        width = 184
        content = 2 * margin + n * width + (n - 1) * spacing
        viewport = self.browser.scroll.viewport().width()
        bar = self.browser.scroll.horizontalScrollBar()
        if content <= viewport:
            self._center_pending = False          # everything fits: nothing to scroll
            return
        if bar.maximum() < content - viewport - 1:
            return                                # not laid out yet: wait for rangeChanged
        index = self.shots.index(self.live_shot) if self.live_shot in self.shots else 0
        middle = margin + index * (width + spacing) + width / 2.0
        bar.setValue(int(round(middle - viewport / 2.0)))
        self._center_pending = False

    def _resolve(self, shot, priority=2):
        show = self.shot_ids[0]
        dept = self.dept_override.get(shot)
        version = self.version_pin.get(shot) if dept else None

        def done(kind, value):
            card = self.browser.cards.get(shot)
            if kind == "error":
                if card:
                    card.set_info(None, None, "error: %s" % value[:40])
                return
            info, image = value
            self.infos[shot] = info
            self.newer.pop(shot, None)
            if card:
                card.thumb_image = image
                if shot in self.preparing:
                    card.set_dept(info)
                else:
                    card.set_info(info, image)

        if version is None:
            self.jobs.add(priority, lambda report: self.reel_mod.resolve(show, shot, dept), done)
        else:
            self.jobs.add(priority, lambda report: self.reel_mod.resolve(show, shot, dept, version=version), done)

    def check_newer_now(self, shots=None):
        """Right-click > Check for newer now (one shot) or Update footage: look
        right away instead of waiting for the 2-minute check."""
        self._check_newer(shots, priority=1, say=True)

    def reload_footage(self, shot):
        """Right-click > Update this shot's footage: the same version made
        again from its file."""
        info = self.infos.get(shot)
        if info:
            self.reel_mod.forget(shot, info)
        self._flash_message("Reloading %s" % shot)
        self._set_department(shot, self.dept_override.get(shot), self.version_pin.get(shot))

    def show_in_folder(self, shot):
        """Open the folder holding the shot's movie in the file browser."""
        info = self.infos.get(shot) or {}
        folder = os.path.dirname(info.get("source_path") or "")
        if folder and os.path.isdir(folder):
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(folder))

    def refresh_all_footage(self):
        """Update footage: reload shots whose file changed, then look for newer
        versions of every shot."""
        changed = [s for s, info in list(self.infos.items())
                   if info and s != self.live_shot and self.reel_mod.footage_changed(s, info, self.height_px)]
        for shot in changed:
            self.reload_footage(shot)
        self._flash_message("Checking every shot for newer footage%s" % (
            " · reloading %d changed" % len(changed) if changed else ""))
        self._check_newer(None, priority=1, say=True)

    def _check_newer(self, shots=None, priority=8, say=False):
        """In the background: for each shot on the strip that isn't pinned,
        is there newer footage than the version it shows? Marks the card.
        A shot that follows Latest and whose file changed is reloaded."""
        if not self.shot_ids:
            return
        show = self.shot_ids[0]
        for shot, info in list(self.infos.items()):
            if shots is not None and shot not in shots:
                continue
            if not info or shot == self.live_shot:
                continue
            if shot in getattr(self, "prepared", {}) and shot not in self.version_pin and \
                    self.reel_mod.footage_changed(shot, info, self.height_px):
                self.reload_footage(shot)
                continue
            if shot in self.version_pin:
                if say:
                    self._flash_message("%s is pinned to v%03d" % (shot, self.version_pin[shot]))
                continue
            dept = self.dept_override.get(shot)

            def done(kind, value, shot=shot, info=info):
                if kind != "done" or not value or self.infos.get(shot) is not info:
                    return
                if (value["department"], value["version"]) == (info["department"], info["version"]) or \
                        (value["department"] == info["department"] and value["version"] < info["version"]):
                    if say and shots is not None:
                        self._flash_message("%s: %s is the newest" % (shot, self.reel_mod.label(info)))
                    return
                self.newer[shot] = value
                card = self.browser.cards.get(shot)
                if card:
                    card.set_dept(info)

            self.jobs.add(priority, lambda report, shot=shot, dept=dept: self.reel_mod.resolve_info(show, shot, dept),
                          done)

    def _prepare(self, shot):
        if shot in self.prepared or shot in self.preparing:
            return
        self.preparing.add(shot)
        self.failed.pop(shot, None)
        gen = self.generation[shot]
        show = self.shot_ids[0]
        info, dept = self.infos.get(shot), self.dept_override.get(shot)
        template = self.reel_mod.audio_template((self.cfg.get("audio") or {}).get("path"), self.live_shot)
        sound_args = (template, self.live_shot, self.rate, self.channels)
        args = (show, shot, info, dept, self.height_px, self.fps, sound_args)
        card = self.browser.cards.get(shot)
        if card:
            card.set_progress("preparing...")

        def done(kind, value):
            if gen != self.generation[shot]:
                return                      # department changed meanwhile: stale result
            card = self.browser.cards.get(shot)
            if kind == "progress":
                if card:
                    card.set_progress("converting... %d%%" % (value * 100) if isinstance(value, float)
                                      else "converting... %d frames" % value)
                return
            self.preparing.discard(shot)
            if kind == "error":
                self.failed[shot] = value
                if card:
                    card.set_progress("failed: %s" % value[:60])
                    card.setToolTip(value)
                return
            self.prepared[shot] = value
            self.infos[shot] = value["info"]
            if card:
                image = getattr(card, "thumb_image", None)
                card.set_info(value["info"], image, "%d frames" % len(value["frames"]))
            if shot in self.staged["before"] or shot in self.staged["after"]:
                self._rebuild_reel()

        self.jobs.add(0, lambda report: self.reel_mod.prepare_shot(*(args + (report,))), done)

    def _side(self, shot):
        """Before or after, from the shot's place in the sequence."""
        if shot in self.shots and self.live_shot in self.shots:
            return "before" if self.shots.index(shot) < self.shots.index(self.live_shot) else "after"
        return "before" if shot < (self.live_shot or "") else "after"

    def stage(self, shot, on):
        for side in ("before", "after"):
            if shot in self.staged[side]:
                self.staged[side].remove(shot)
        if on:
            self.staged[self._side(shot)].append(shot)
            self._prepare(shot)
        self._save_prefs()
        self._refresh_cards()
        self._rebuild_reel()

    def live_menu(self, where):
        """Your own shot: Live, or one department's movie; image plane in Maya."""
        menu = QtWidgets.QMenu(self)
        act = menu.addAction("Live (your animation)")
        act.setCheckable(True)
        act.setChecked(self.live_ref is None)
        act.triggered.connect(lambda: self.set_live_ref(None))
        menu.addSeparator()
        for name in self.reel_mod.department_order():
            act = menu.addAction(name)
            act.setCheckable(True)
            act.setChecked(self.live_ref == name)
            act.triggered.connect(lambda _=False, n=name: self.set_live_ref(n))
        menu.addSeparator()
        ref = self.live_ref or self.live_ref_last
        for mode, text in (("front", "in front"), ("behind", "behind")):
            act = menu.addAction("Image plane in Maya: %s%s" % (text, " (%s)" % ref if ref else ""))
            act.setCheckable(True)
            act.setChecked(self.plane_mode == mode)
            act.setEnabled(bool(ref))
            act.triggered.connect(lambda _=False, m=mode: self.image_plane(m))
        act = menu.addAction("Remove image plane")
        act.setEnabled(self.plane_mode is not None)
        act.triggered.connect(self.remove_image_plane)
        menu.exec(where) if hasattr(menu, "exec") else menu.exec_(where)

    def set_live_ref(self, dept):
        """Show your shot as a department's movie instead of the live cache
        (None = live). The live cache keeps updating in the background."""
        self.live_ref = dept
        if dept:
            self.live_ref_last = dept
        self.live_ref_ready = None
        self._live_gen += 1
        self._save_prefs()
        card = self.browser.cards.get(self.live_shot)
        if card:
            card.set_dept(None)
            card.set_progress("live cache")
        if dept:
            self._prepare_live_ref()
        self._rebuild_reel()

    def toggle_live_ref(self):
        """R: flip between your live animation and the last reference movie."""
        if self.live_ref:
            self.set_live_ref(None)
        elif self.live_ref_last:
            self.set_live_ref(self.live_ref_last)

    def _prepare_live_ref(self):
        dept, gen, show, shot = self.live_ref, self._live_gen, self.shot_ids[0], self.live_shot
        height = self.height_px

        def work(report):
            info = self.reel_mod.resolve_info(show, shot, dept)
            if not info:
                raise RuntimeError("no %s for this shot" % dept)
            frames, _skip = self.reel_mod.shot_frames(shot, info, height, report)    # without a movie's slate
            return {"info": info, "frames": frames}

        def done(kind, value):
            if gen != self._live_gen:
                return                      # you picked something else meanwhile
            card = self.browser.cards.get(shot)
            if kind == "progress":
                if card:
                    card.set_progress("converting %s... %s" % (dept, "%d%%" % (value * 100)
                                      if isinstance(value, float) else "%d frames" % value))
                return
            if kind == "error":
                if card:
                    card.set_progress("no %s for this shot" % dept)
                self._flash_message("No %s for this shot: showing live" % dept)
                self.live_ref = None
                self._save_prefs()
                return
            self.live_ref_ready = value
            if card:
                card.set_dept(value["info"])
                frames = value.get("frames") or []
                image = None
                if frames:
                    image = QtGui.QImage(frames[len(frames) // 2])
                    if not image.isNull():
                        image = image.scaled(card.thumb.width(), card.thumb.height(),
                                             Qt.KeepAspectRatio, Qt.SmoothTransformation)
                card.set_reference(image, self.reel_mod.label(value["info"]))
            self._rebuild_reel()

        self.jobs.add(0, work, done)

    def image_plane(self, mode):
        """Put the reference movie on the shot camera in your Maya, in front of
        or behind the scene. Uses full-resolution frames (converted once)."""
        dept = self.live_ref or self.live_ref_last
        if not dept:
            return
        show, shot = self.shot_ids[0], self.live_shot
        camera = self.view or ((self.cfg.get("cameras") or [{}])[0].get("name"))
        if not camera:
            self._flash_message("Pick a camera first")
            return
        info = (self.live_ref_ready or {}).get("info") if self.live_ref == dept else None

        def work(report):
            found = info or self.reel_mod.resolve_info(show, shot, dept)
            if not found:
                raise RuntimeError("no %s for this shot" % dept)
            return self.reel_mod.prepare_full(shot, found, report)

        def done(kind, value):
            if kind == "progress":
                self._flash_message("Preparing image plane... %s" % (
                    "%d%%" % (value * 100) if isinstance(value, float) else "%d frames" % value))
                return
            if kind == "error":
                self._flash_message("Image plane: %s" % value)
                return
            path, first = value
            self.send_cmd("image_plane", mode=mode, camera=camera, path=path, offset=first - self.start)
            self.plane_mode = mode
            self._flash_message("Image plane in your Maya: %s (%s). Refresh to see it in the cache"
                                % ("in front" if mode == "front" else "behind", dept), 5.0)

        self._flash_message("Preparing image plane...")
        self.jobs.add(0, work, done)

    def remove_image_plane(self):
        self.send_cmd("image_plane_remove")
        self.plane_mode = None
        self._flash_message("Image plane removed from your Maya. Refresh to take it out of the cache", 5.0)

    def department_menu(self, shot, where):
        """Auto, or a department: its latest version, or one version pinned
        (the 10 newest listed, More versions... for the rest). When newer
        footage has come in, "Update to ..." comes first."""
        menu = QtWidgets.QMenu(self)
        current = self.dept_override.get(shot)
        pinned = self.version_pin.get(shot)
        newer = self.newer.get(shot)
        if newer:
            act = menu.addAction("Update to %s" % self.reel_mod.label(newer))
            act.triggered.connect(lambda: self._set_department(shot, current))
            menu.addSeparator()
        menu.addAction("Check for newer now").triggered.connect(lambda: self.check_newer_now([shot]))
        act = menu.addAction("Update this shot's footage")
        act.setToolTip("Convert the same version again from its file (for a version re-published "
                       "under the same name)")
        act.triggered.connect(lambda: self.reload_footage(shot))
        info = self.infos.get(shot)
        act = menu.addAction("Show in folder")
        act.setEnabled(bool(info and info.get("source_path")))
        act.triggered.connect(lambda: self.show_in_folder(shot))
        menu.addSeparator()
        order = self.reel_mod.department_order()
        act = menu.addAction("Auto (%s)" % ", ".join(order))
        act.setCheckable(True)
        act.setChecked(current is None)
        act.triggered.connect(lambda: self._set_department(shot, None))
        menu.addSeparator()
        show = self.shot_ids[0] if self.shot_ids else ""
        for name in order:
            try:
                versions = self.reel_mod.cr.list_versions(show, shot, name)
            except Exception:  # a department folder we can't list: shown with no versions
                versions = []
            if not versions:
                act = menu.addAction("%s (none)" % name)
                act.setEnabled(False)
                continue
            sub = menu.addMenu(("\u2713 " if current == name else "") + name)
            act = sub.addAction("Latest (v%03d)" % versions[0])
            act.setCheckable(True)
            act.setChecked(current == name and pinned is None)
            act.triggered.connect(lambda _=False, n=name: self._set_department(shot, n))
            sub.addSeparator()
            for v in versions[:VERSIONS_LISTED]:
                act = sub.addAction("v%03d" % v)
                act.setCheckable(True)
                act.setChecked(current == name and pinned == v)
                act.triggered.connect(lambda _=False, n=name, v=v: self._set_department(shot, n, v))
            if len(versions) > VERSIONS_LISTED:
                act = sub.addAction("More versions...")
                act.triggered.connect(lambda _=False, n=name, vs=versions: self._pick_older(shot, n, vs))
        menu.exec(where) if hasattr(menu, "exec") else menu.exec_(where)

    def _pick_older(self, shot, dept, versions):
        items = ["v%03d" % v for v in versions]
        item, ok = QtWidgets.QInputDialog.getItem(self, "%s versions" % dept, "Pin %s for %s to:" % (dept, shot),
                                                  items, 0, False)
        if ok and item:
            self._set_department(shot, dept, int(item[1:]))

    def _set_department(self, shot, dept, version=None):
        """dept None: Auto. version: pin that version (None: always the latest)."""
        self.newer.pop(shot, None)
        if version is None:
            self.version_pin.pop(shot, None)
        else:
            self.version_pin[shot] = int(version)
        if dept is None:
            self.dept_override.pop(shot, None)
            self.version_pin.pop(shot, None)
        else:
            self.dept_override[shot] = dept
        self._save_prefs()
        self.generation[shot] += 1
        self.preparing.discard(shot)
        self.prepared.pop(shot, None)
        self.infos.pop(shot, None)
        card = self.browser.cards.get(shot)
        if card:
            card.set_progress("finding footage...")
        self._resolve(shot, priority=0)
        if shot in self.staged["before"] or shot in self.staged["after"]:
            self.jobs.add(0, lambda report: None, lambda kind, value: self._prepare(shot))
        self._rebuild_reel()

    def _refresh_cards(self):
        for shot, card in self.browser.cards.items():
            card.set_staged("before" if shot in self.staged["before"] else
                            "after" if shot in self.staged["after"] else None)
        self.browser.untick.setEnabled(bool(self.staged["before"] or self.staged["after"]))
        self._update_strip_header()

    def untick_all(self):
        """Untick all: back to your shot on its own."""
        if not (self.staged["before"] or self.staged["after"]):
            return
        self.staged = {"before": [], "after": []}
        self._save_prefs()
        self._refresh_cards()
        self._rebuild_reel()

    def toggle_continuity(self, on=None):
        if not self.shot_ids:
            return
        self.continuity_on = self.b_cont.isChecked() if on is None else on
        self.b_cont.setChecked(self.continuity_on)
        self._apply_continuity_visibility()
        if self.continuity_on:
            QtCore.QTimer.singleShot(0, self._scroll_to_live)
        self._save_prefs()
        self._rebuild_reel()

    def toggle_browser(self):
        if not self.continuity_on:
            return
        self.browser_open = not self.browser_open
        self._apply_continuity_visibility()
        if self.browser_open:
            QtCore.QTimer.singleShot(0, self._scroll_to_live)
        self._save_prefs()
