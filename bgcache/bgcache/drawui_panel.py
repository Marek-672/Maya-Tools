"""Drawing in the player: the drawing strip (DrawPanel): tools, colours, Show, layers, sharing.

Part of drawui.py (the Drawer and the drawing strip); see DEVELOPER.md."""
from bgcache.drawui_common import *  # noqa: F401,F403 (Qt, drawing, profile, colours)
from bgcache.drawui_icons import icon  # noqa: F401
from bgcache.drawui_widgets import *  # noqa: F401,F403
from bgcache.drawui_widgets import _head, _button, _is_dark, _line  # noqa: F401

class DrawPanel(QtWidgets.QWidget):
    """Side strip shown in Draw mode."""

    def __init__(self, drawer, keymap):
        super(DrawPanel, self).__init__()
        self.drawer, self.keymap = drawer, keymap
        drawer.panel = self
        self.setObjectName("drawStrip")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(DRAW_STYLE)
        self.setFixedWidth(256)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        self._build_tool_and_size(lay)
        self._build_colours(lay)
        self._build_show(lay)
        _line(lay)
        self._build_layers(lay)
        _line(lay)
        self._build_share(lay)
        self.hint = QtWidgets.QLabel("")
        self.hint.setObjectName("hint")
        self.hint.setWordWrap(True)
        lay.addWidget(self.hint)
        self._build_save(lay)
        self.setVisible(False)
        self.refresh()

    def _build_save(self, lay):
        """Save at the bottom (0.9.0b3): nothing is shared until you save."""
        self.unsaved_label = QtWidgets.QLabel("\u25cf Unsaved: only you see these changes until you save")
        self.unsaved_label.setObjectName("unsaved")
        self.unsaved_label.setWordWrap(True)
        lay.addWidget(self.unsaved_label)
        row = QtWidgets.QHBoxLayout()
        self.b_save = _button("Save drawings  (Ctrl+S)", "Save your drawings: others see them after they press Update",
                              object_name="save")
        self.b_save.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.b_save.clicked.connect(self.drawer.save_now)
        self.b_history = _button("History", "Your earlier saves of this camera's drawings: restore one")
        self.b_history.clicked.connect(self.show_history)
        row.addWidget(self.b_save, 1)
        row.addWidget(self.b_history)
        lay.addLayout(row)

    def refresh_save(self):
        mine = self.drawer.mine_now()
        dirty = bool(mine is not None and mine.dirty)
        self.unsaved_label.setVisible(dirty)
        self.b_save.setEnabled(dirty)
        self.b_history.setEnabled(mine is not None and os.path.isfile(mine.path))

    def show_history(self):
        """Your earlier saves, newest first; Restore brings one back (and is
        itself a save, so it can be undone the same way)."""
        mine = self.drawer.mine_now()
        if mine is None:
            return
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Drawing history")
        dlg.setStyleSheet(DRAW_STYLE + "QDialog { background: #2c2c2c; } QListWidget { background: #1e1e1e; color: #e6e6e6; border: 1px solid #444; }")
        lay = QtWidgets.QVBoxLayout(dlg)
        head = QtWidgets.QLabel("Your saves of %s, newest first. The last %d are kept; a restore is a save "
                                "too, so it can be undone." % (self.drawer.cam(), drawing.VERSIONS_KEPT))
        head.setWordWrap(True)
        lay.addWidget(head)
        lst = QtWidgets.QListWidget()
        versions = mine.versions()
        for v in versions:
            when = time.strftime("%a %d %b %H:%M", time.localtime(v["saved"]))
            frames = "frames %d-%d" % v["frames"] if v["frames"] else "no drawings"
            lst.addItem("%s  \u00b7  %s%s" % (when, frames, "   (current)" if v["current"] else ""))
        lay.addWidget(lst, 1)
        row = QtWidgets.QHBoxLayout()
        restore = _button("Restore", "Bring this version back and save it")
        close = _button("Close")
        row.addStretch(1)
        row.addWidget(restore)
        row.addWidget(close)
        lay.addLayout(row)
        close.clicked.connect(dlg.reject)

        def go():
            i = lst.currentRow()
            if 0 < i < len(versions):
                self.drawer.restore_version(versions[i]["path"])
                dlg.accept()
        restore.clicked.connect(go)
        lst.currentRowChanged.connect(lambda i: restore.setEnabled(0 < i < len(versions)))
        restore.setEnabled(False)
        dlg.resize(420, 320)
        (getattr(dlg, "exec", None) or dlg.exec_)()

    def _build_tool_and_size(self, lay):
        """Tool (Pen / Eraser) and Size."""
        lay.addWidget(_head("Tool"))
        row = QtWidgets.QHBoxLayout()
        self.b_pen = _button("Pen", checkable=True)
        self.b_eraser = _button("Eraser", checkable=True)
        for b in (self.b_pen, self.b_eraser):
            b.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            row.addWidget(b)
        self.b_pen.clicked.connect(lambda: self.set_tool("pen"))
        self.b_eraser.clicked.connect(lambda: self.set_tool("eraser"))
        lay.addLayout(row)

        lay.addWidget(_head("Size"))
        row = QtWidgets.QHBoxLayout()
        self.dot = SizeDot(self.drawer)
        self.slider = QtWidgets.QSlider(Qt.Horizontal)
        self.slider.setRange(1, 40)
        self.spin = CountBox()
        self.spin.setRange(1, 40)
        self.spin.setFixedWidth(46)
        for w in (self.dot, self.slider, self.spin):
            row.addWidget(w)
        row.addWidget(QtWidgets.QLabel("px"))
        self.slider.valueChanged.connect(self.set_size)
        self.spin.valueChanged.connect(self.set_size)
        lay.addLayout(row)

    def _build_colours(self, lay):
        """Colour: the swatches and your custom colour."""
        lay.addWidget(_head("Colour"))
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(2)
        self.swatches = []
        for color, name in zip(drawing.COLORS, drawing.COLOR_NAMES):
            b = Swatch(color, name)
            b.clicked.connect(lambda checked=False, c=color: self.set_color(c))
            row.addWidget(b)
            self.swatches.append((color, b))
        divider = QtWidgets.QFrame()
        divider.setFixedSize(1, 26)
        divider.setStyleSheet("background: #444")
        row.addSpacing(3)
        row.addWidget(divider)
        row.addSpacing(3)
        self.custom_swatch = Swatch(self.drawer.custom, "Custom colour: click to use it, click again to change it",
                                    custom=True)
        self.custom_swatch.clicked.connect(self.custom_clicked)
        row.addWidget(self.custom_swatch)
        row.addStretch(1)
        lay.addLayout(row)

    def _build_show(self, lay):
        """Show (Hold, Onion skin), step through drawings, Paper, Undo/Redo/Clear."""
        lay.addWidget(_head("Show"))
        row = QtWidgets.QHBoxLayout()
        self.b_hold = _button("Hold", "Each drawing stays until the next drawn frame", checkable=True)
        self.b_onion = _button("Onion skin", "Faint drawings from the drawn frames before (red) and after (blue)",
                               checkable=True)
        for b in (self.b_hold, self.b_onion):
            b.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            row.addWidget(b)
        self.b_hold.clicked.connect(lambda c: self._set("hold", c))
        self.b_onion.clicked.connect(lambda c: self._set("onion", c))
        lay.addLayout(row)

        # b12: how many drawings onion skin shows, before and after
        row = QtWidgets.QHBoxLayout()
        self.onion_spins = {}
        for name, text, tip in (("onion_before", "Before", "Onion skin: how many drawings before this one (red)"),
                                ("onion_after", "After", "Onion skin: how many drawings after this one (blue)")):
            label = QtWidgets.QLabel(text)
            label.setToolTip(tip)
            spin = CountBox()
            spin.setRange(0, drawing.ONION_MAX)
            spin.setFixedWidth(42)
            spin.setToolTip(tip + ". Counted in drawings, not frames; the nearest is the strongest")
            spin.valueChanged.connect(lambda v, n=name: self._set(n, int(v)))
            self.onion_spins[name] = spin
            row.addWidget(label)
            row.addWidget(spin)
        lay.addLayout(row)

        # Step through the drawings (the orange marks on the bar), cycling round
        row = QtWidgets.QHBoxLayout()
        self.b_prev_drawing = _button("◀ Drawing", "Previous drawing")
        self.b_next_drawing = _button("Drawing ▶", "Next drawing (after the last, back to the first)")
        for b, step in ((self.b_prev_drawing, -1), (self.b_next_drawing, 1)):
            b.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            b.clicked.connect(lambda _=False, s=step: self.drawer.player.step_drawing(s))
            row.addWidget(b)
        lay.addLayout(row)

        # Paper: fade the movie towards white so the drawings read better
        row = QtWidgets.QHBoxLayout()
        paper_label = QtWidgets.QLabel("Paper")
        paper_label.setToolTip("Fade the picture towards white, like paper over the movie, so drawings read better")
        self.paper_slider = QtWidgets.QSlider(Qt.Horizontal)
        self.paper_slider.setRange(0, 100)
        self.paper_slider.setToolTip(paper_label.toolTip())
        self.paper_value = QtWidgets.QLabel("0%")
        self.paper_value.setFixedWidth(34)
        for w in (paper_label, self.paper_slider, self.paper_value):
            row.addWidget(w)
        self.paper_slider.valueChanged.connect(self.set_paper)
        lay.addLayout(row)

        row = QtWidgets.QHBoxLayout()
        for text, tip, fn in (("Undo", "Undo (Ctrl+Z)", self.drawer.undo), ("Redo", "Redo (Ctrl+Shift+Z)", self.drawer.redo),
                              ("Clear", "Clear this frame's drawing on the active layer", self.drawer.clear)):
            b = _button(text, tip)
            b.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            b.clicked.connect(fn)
            row.addWidget(b)
        lay.addLayout(row)

    def _build_layers(self, lay):
        """Layers: the buttons and the scrolling layer list."""
        row = QtWidgets.QHBoxLayout()
        row.addWidget(_head("Layers"), 1)
        for kind, tip, fn in (("plus", "New layer", self.add_layer),
                              ("up", "Move layer up", lambda: self.move_layer(-1)),
                              ("down", "Move layer down", lambda: self.move_layer(1)),
                              ("trash", "Delete layer", self.delete_layer)):
            b = _button(kind=kind, tip=tip)
            b.clicked.connect(fn)
            row.addWidget(b)
        lay.addLayout(row)
        self.rows_box = QtWidgets.QVBoxLayout()
        self.rows_box.setSpacing(2)
        rows_widget = QtWidgets.QWidget()
        rows_widget.setObjectName("layerList")
        rows_widget.setAttribute(Qt.WA_StyledBackground, True)
        rows_widget.setLayout(self.rows_box)
        scroll = QtWidgets.QScrollArea()
        scroll.setObjectName("layers")
        scroll.viewport().setObjectName("layersView")
        scroll.setWidgetResizable(True)
        scroll.setWidget(rows_widget)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lay.addWidget(scroll, 1)

    def _build_share(self, lay):
        """Share: Export to Blue Pencil and Import."""
        lay.addWidget(_head("Share"))
        row = QtWidgets.QHBoxLayout()
        self.b_export = _button("Export to Blue Pencil...", "Save the visible layers as a Blue Pencil zip for Maya")
        self.b_import = _button("Import", "Other people's drawings or a Blue Pencil zip")
        self.b_import.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.import_menu = QtWidgets.QMenu(self)
        self.import_menu.aboutToShow.connect(self.fill_import_menu)
        self.b_import.setMenu(self.import_menu)
        self.b_export.clicked.connect(self.export)
        row.addWidget(self.b_export, 1)
        row.addWidget(self.b_import)
        lay.addLayout(row)

    # ------------------------------------------------------------ settings
    def _set(self, name, value):
        setattr(self.drawer, name, value)
        self.drawer.save_prefs()
        self.refresh(rows=False)
        self.drawer.player.canvas.update()

    def set_tool(self, tool):
        self._set("tool", tool)

    def set_paper(self, value):
        """Paper slider, 0-100 %."""
        self.drawer.paper = min(max(value, 0), 100) / 100.0
        self.paper_value.setText("%d%%" % int(value))
        self.drawer.player.canvas.update()

    def set_size(self, value):
        if int(value) != int(self.drawer.size):
            self._set("size", float(value))

    def set_color(self, color):
        self._set("color", color)
        if self.drawer.tool != "pen":
            self.set_tool("pen")

    def custom_clicked(self):
        """First click uses the custom colour; clicking it while it's the
        current colour (or before one is picked) opens the picker."""
        d = self.drawer
        if d.custom and (d.color or "").lower() != d.custom.lower():
            self.set_color(d.custom)
            return
        picked = pick_color(self, d.custom or d.color)
        if picked:
            d.custom = picked
            self.set_color(picked)
        else:
            self.refresh(rows=False)

    def add_layer(self):
        mine = self.drawer.mine_now()
        if mine:
            mine.add_layer()
            self.drawer.edited()
            self.drawer.changed()

    def move_layer(self, delta):
        mine = self.drawer.mine_now()
        if mine and mine.active:
            mine.move_layer(mine.active, delta)
            self.drawer.edited()
            self.drawer.changed()

    def delete_layer(self):
        d = self.drawer
        if d.selected and any(r["key"] == d.selected for r in d.rows()):
            key, d.selected = d.selected, None
            d.remove_row(key)               # imported: off your list, their files untouched
            d.player._flash_message("Removed from your list (the files are untouched)")
            return
        d.selected = None
        mine = self.drawer.mine_now()
        layer = mine.active_layer() if mine else None
        if layer is None:
            return
        if layer.get("locked"):
            d.player._flash_message("Layer %s is locked: unlock it to delete it" % layer["name"])
            return
        if layer["frames"]:
            answer = QtWidgets.QMessageBox.question(
                self, "Delete layer", "Delete layer %s and its drawings?\n(Undo brings it back.)" % layer["name"])
            if answer != QtWidgets.QMessageBox.Yes:
                return
        mine.delete_layer(layer["id"])
        self.drawer.edited()
        self.drawer.changed()

    def opacity_popup(self, key, button):
        menu = QtWidgets.QMenu(self)
        holder = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(holder)
        row.setContentsMargins(10, 6, 10, 6)
        row.addWidget(QtWidgets.QLabel("Opacity"))
        slider = QtWidgets.QSlider(Qt.Horizontal)
        slider.setRange(0, 100)
        slider.setFixedWidth(130)
        slider.setValue(int(round(100 * float(self.drawer.row_value(key, "opacity") or 0))))
        value = QtWidgets.QLabel("%d%%" % slider.value())
        row.addWidget(slider)
        row.addWidget(value)

        def changed(v):
            value.setText("%d%%" % v)
            button.setText("%d%%" % v)
            self.drawer.set_row(key, opacity=v / 100.0)
        slider.valueChanged.connect(changed)
        action = QtWidgets.QWidgetAction(menu)
        action.setDefaultWidget(holder)
        menu.addAction(action)
        run = getattr(menu, "exec", None) or menu.exec_
        run(button.mapToGlobal(QtCore.QPoint(0, button.height())))

    # ------------------------------------------------------------ import / export
    def fill_import_menu(self):
        menu = self.import_menu
        menu.clear()
        d = self.drawer
        cam = d.cam()
        other_shot = cam.split("@", 1)[1] if cam and "@" in cam else None
        head = menu.addAction("On %s · %s" % (other_shot or d.player.live_shot or "this shot",
                                              d._folder_of(cam) if cam else "-"))
        head.setEnabled(False)
        people = d.find_people()
        if not people:
            none = menu.addAction("   no one else has drawings for this camera")
            none.setEnabled(False)
        for person in people:
            self._person_action(menu, person, cam)
        # the other cameras: people (and you) with drawings there (your own shot)
        for other in ([] if other_shot else sorted(drawing.drawn_cameras(d.root) - {cam})):
            found = d.find_people(other, include_me=True)
            if not found:
                continue
            menu.addSeparator()
            full = self._camera_named(other)
            state = self._camera_state(full)
            title = menu.addAction("On %s%s" % (other, ("    · " + state) if state else ""))
            title.setEnabled(False)
            if full and not state:
                menu.addAction("   Cache %s" % other, lambda _checked=False, f=full: self.cache_camera(f))
            elif not full:
                note = menu.addAction("   (not a camera in your scene)")
                note.setEnabled(False)
            for person in found:
                if person["user"] == d.user:
                    you = menu.addAction("   you      %d layer%s" % (person["layers"], "" if person["layers"] == 1 else "s"))
                    you.setEnabled(False)
                else:
                    self._person_action(menu, person, other)
        menu.addSeparator()
        menu.addAction("Blue Pencil zip...", self.import_blue)

    def _person_action(self, menu, person, cam):
        d = self.drawer
        linked = d.is_linked(person["user"], cam)
        row = d.person(person["user"], cam) if linked else None
        tag = "update" if row is not None and row["status"] == "update" else \
            "%d layer%s" % (person["layers"], "" if person["layers"] == 1 else "s")
        act = menu.addAction("%s      %s" % (person["user"], tag))
        act.setCheckable(True)
        act.setChecked(linked)
        act.toggled.connect(lambda on, u=person["user"], c=cam: d.set_linked(u, on, c))
        return act

    def _camera_named(self, folder):
        for c in self.drawer.player.cfg.get("cameras") or []:
            if drawing.camera_folder(c.get("name")) == folder:
                return c.get("name")
        return None

    def _camera_state(self, full):
        """"" (not cached), "caching 62%" or "loaded" for one of your cameras."""
        pl = self.drawer.player
        if not full or full not in (pl.checked or []):
            return ""
        total = max(1, int(pl.end) - int(pl.start) + 1)
        have = len(pl.loaded.get(full, {})) if hasattr(pl, "loaded") else 0
        dirty = len(pl.dirty.get(full, ())) if hasattr(pl, "dirty") else 0
        done = min(have, total - dirty) if have else 0
        if done >= total and not dirty:
            return "loaded"
        return "caching %d%%" % int(100.0 * done / total)

    def cache_camera(self, full):
        """Start caching another camera in the background (after the one
        you're viewing); you switch to it yourself with the Camera menu."""
        pl = self.drawer.player
        pl._set_checked(full, True)
        pl._flash_message("Caching %s in the background: switch to it in the Camera menu when it's loaded"
                          % pl._label(full), 5.0)

    def import_blue(self):
        path, _filter = QtWidgets.QFileDialog.getOpenFileName(
            self, "Show a Blue Pencil zip over the playback", os.path.expanduser("~"), "Blue Pencil (*.zip)")
        if path:
            self.drawer.add_blue(path)

    def export(self):
        d = self.drawer
        mine = d.mine_now()
        if mine is None or not (mine.drawn_frames() or d.ticks()):
            d.player._flash_message("Nothing visible to export")
            return
        if not d._gate():
            d.player._flash_message("No camera details from Maya: placement assumes the frame fills Blue Pencil's width", 5.0)
        folder = os.path.dirname(mine.path)
        default = os.path.join(folder, "bluepencil_%s_%s_%s.zip" % (
            d.player.live_shot or "shot", d.cam(), time.strftime("%m%d_%H%M")))
        path, _filter = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export to Blue Pencil", default, "Blue Pencil (*.zip)")
        if not path:
            return
        if not path.lower().endswith(".zip"):
            path += ".zip"
        try:
            if not os.path.isdir(os.path.dirname(path)):
                os.makedirs(os.path.dirname(path))
            frames, layers = d.export_blue_pencil(path)
        except Exception as error:
            d.player._flash_message("Export failed: %s" % error, 6.0)
            return
        d.player.send_cmd("bp_import", path=path)
        d.player._flash_message("Saved %d drawings on %d layers. In Maya: pick the file in Blue Pencil's "
                                "import (its path is on your clipboard)" % (frames, layers), 8.0)

    # ------------------------------------------------------------ refresh
    def refresh(self, rows=True):
        d = self.drawer
        self.b_pen.setChecked(d.tool == "pen")
        self.b_eraser.setChecked(d.tool == "eraser")
        for w, v in ((self.slider, d.size), (self.spin, d.size)):
            w.blockSignals(True)
            w.setValue(int(v))
            w.blockSignals(False)
        current = (d.color or "").lower()
        preset = False
        for color, b in self.swatches:
            b.setChecked(color.lower() == current)
            preset = preset or color.lower() == current
        self.custom_swatch.set_color(d.custom)
        self.custom_swatch.setChecked(not preset and bool(d.custom) and d.custom.lower() == current)
        self.b_hold.setChecked(d.hold)
        self.b_onion.setChecked(d.onion)
        for name, spin in self.onion_spins.items():
            spin.blockSignals(True)
            spin.setValue(int(getattr(d, name)))
            spin.setEnabled(bool(d.onion))
            spin.blockSignals(False)
        self.paper_slider.blockSignals(True)
        self.paper_slider.setValue(int(round(d.paper * 100)))
        self.paper_slider.blockSignals(False)
        self.paper_value.setText("%d%%" % int(round(d.paper * 100)))
        self.dot.update()
        prev_key, next_key = self.keymap.label("prev_key"), self.keymap.label("next_key")
        self.b_prev_drawing.setToolTip("Previous drawing (%s)" % prev_key)
        self.b_next_drawing.setToolTip("Next drawing (%s); after the last, back to the first" % next_key)
        self.hint.setText("Scrub: %s + drag or middle-drag · Step: %s / %s · Drawings: %s / %s\n(your Maya hotkeys)" % (
            self.keymap.label("scrub"), self.keymap.label("prev_frame"), self.keymap.label("next_frame"),
            prev_key, next_key))
        self.refresh_save()
        if not rows:
            return
        for _ in range(int(self.rows_box.count())):
            item = self.rows_box.takeAt(0)
            if item.widget():
                item.widget().hide()          # gone at once, not when Qt gets round to deleting it
                item.widget().deleteLater()
        for row in d.rows():
            self.rows_box.addWidget(HeadRow(self, row) if row["kind"] in ("me", "head") else LayerRow(self, row))
        self.rows_box.addStretch(1)
