"""Drawing in the player: the drawing strip's small widgets: buttons, size dot, colour swatches, the layer list's rows.

Part of drawui.py (the Drawer and the drawing strip); see DEVELOPER.md."""
from bgcache.drawui_common import *  # noqa: F401,F403 (Qt, drawing, profile, colours)
from bgcache.drawui_icons import icon  # noqa: F401

# --------------------------------------------------------------------------
# The side strip
# --------------------------------------------------------------------------
def _head(text):
    label = QtWidgets.QLabel(text.upper())
    label.setObjectName("head")
    return label


def _button(text=None, tip=None, kind=None, checkable=False, object_name=None):
    b = QtWidgets.QToolButton()
    if text:
        b.setText(text)
    if kind:
        b.setIcon(icon(kind))
    if tip:
        b.setToolTip(tip)
    b.setCheckable(checkable)
    if object_name:
        b.setObjectName(object_name)
    b.setFocusPolicy(Qt.NoFocus)
    return b


class SizeDot(QtWidgets.QWidget):
    def __init__(self, drawer):
        super(SizeDot, self).__init__()
        self.drawer = drawer
        self.setFixedSize(28, 28)

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        p.fillRect(self.rect(), QtGui.QColor(38, 38, 38))
        r = max(1.0, min(12.0, self.drawer.size / 2.0))
        if self.drawer.tool == "eraser":            # the eraser: an outline of its size
            p.setPen(QtGui.QPen(QtGui.QColor("#e6e6e6"), 1))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QtCore.QPointF(14, 14), r, r)
            p.end()
            return
        color = QtGui.QColor(self.drawer.color)
        p.setPen(QtGui.QPen(QtGui.QColor("#8a8a8a"), 1) if _is_dark(color) else Qt.NoPen)
        p.setBrush(color)
        p.drawEllipse(QtCore.QPointF(14, 14), r, r)
        p.end()


def _is_dark(color):
    try:
        return int(color.lightness()) < 70
    except Exception:  # not a QColor: treat as light
        return False


class CountBox(QtWidgets.QSpinBox):
    """A number box for the strip (b13): type a number or use its arrows.
    Its arrows are painted bright (the dark style's own can't be seen), and
    Enter or Escape hands the keyboard back to the player's keys."""
    ARROW = QtGui.QColor(230, 230, 230)

    def __init__(self):
        super(CountBox, self).__init__()
        self.setFocusPolicy(Qt.ClickFocus)          # a click to type; not a stop for Tab or the wheel
        self.setKeyboardTracking(False)             # a typed number counts when it's finished
        self.editingFinished.connect(self._done)

    def _done(self):
        if self.hasFocus():
            self.clearFocus()
            self.window().setFocus()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Escape):
            self.interpretText()
            self._done()
            event.accept()
            return
        super(CountBox, self).keyPressEvent(event)

    def mouseReleaseEvent(self, event):
        super(CountBox, self).mouseReleaseEvent(event)
        if any(r.contains(event.pos()) for r in self.arrow_rects()):
            self._done()                            # an arrow click doesn't keep the keyboard

    def arrow_rects(self):
        """(up, down) rectangles of the two arrow buttons."""
        try:
            opt = QtWidgets.QStyleOptionSpinBox()
            self.initStyleOption(opt)
            style = self.style()
            up = style.subControlRect(QtWidgets.QStyle.CC_SpinBox, opt, QtWidgets.QStyle.SC_SpinBoxUp, self)
            down = style.subControlRect(QtWidgets.QStyle.CC_SpinBox, opt, QtWidgets.QStyle.SC_SpinBoxDown, self)
            if up.width() > 4 and down.width() > 4:
                return up, down
        except (AttributeError, TypeError, RuntimeError):  # a style without them: the usual place
            pass
        w, h = self.width(), self.height()
        return QtCore.QRect(w - 16, 1, 15, h // 2 - 1), QtCore.QRect(w - 16, h // 2, 15, h - h // 2 - 1)

    def paintEvent(self, event):
        super(CountBox, self).paintEvent(event)
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        for rect, up in zip(self.arrow_rects(), (True, False)):
            p.fillRect(rect, QtGui.QColor(58, 58, 58))
            can = self.value() < self.maximum() if up else self.value() > self.minimum()
            color = QtGui.QColor(self.ARROW)
            if not (can and self.isEnabled()):
                color.setAlpha(70)
            p.setBrush(color)
            cx, cy = rect.center().x() + 0.5, rect.center().y() + 0.5
            tip = -2.5 if up else 2.5
            p.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(cx - 4, cy - tip), QtCore.QPointF(cx + 4, cy - tip),
                                           QtCore.QPointF(cx, cy + tip)]))
        p.end()


class Swatch(QtWidgets.QToolButton):
    """A colour circle (26 px). The selected one has an orange bar under it.
    custom=True: the custom colour, a rainbow ring (36 px) around it with a
    1 px black ring between; dark with a white + until a colour is picked."""
    DOT = 26
    RING = 36

    def __init__(self, color=None, tip=None, custom=False):
        super(Swatch, self).__init__()
        self.color, self.custom = color, custom
        self.setObjectName("swatch")
        self.setCheckable(True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.PointingHandCursor)
        if tip:
            self.setToolTip(tip)
        self.setFixedSize((self.RING if custom else self.DOT) + 2, self.RING + 8)

    def set_color(self, color):
        self.color = color
        self.update()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        c = QtCore.QPointF(self.width() / 2.0, self.RING / 2.0 + 1)
        r = self.DOT / 2.0
        if self.custom:
            grad = QtGui.QConicalGradient(c, 90)
            for i in range(7):
                grad.setColorAt(i / 6.0, QtGui.QColor.fromHsvF((i % 6) / 6.0, 0.85, 0.95))
            p.setPen(Qt.NoPen)
            p.setBrush(QtGui.QBrush(grad))
            p.drawEllipse(c, self.RING / 2.0, self.RING / 2.0)
            p.setBrush(QtGui.QColor("#000000"))          # 1 px black ring
            p.drawEllipse(c, r + 1, r + 1)
            p.setBrush(QtGui.QColor(self.color) if self.color else QtGui.QColor("#2a2a2a"))
            p.drawEllipse(c, r, r)
            if not self.color:
                p.setPen(QtGui.QPen(QtGui.QColor("#ffffff"), 2))
                p.drawLine(QtCore.QPointF(c.x() - 5, c.y()), QtCore.QPointF(c.x() + 5, c.y()))
                p.drawLine(QtCore.QPointF(c.x(), c.y() - 5), QtCore.QPointF(c.x(), c.y() + 5))
        else:
            color = QtGui.QColor(self.color)
            # black (or any dark colour) gets a grey outline so it shows on the dark strip
            p.setPen(QtGui.QPen(QtGui.QColor("#8a8a8a"), 1) if _is_dark(color) else Qt.NoPen)
            p.setBrush(color)
            p.drawEllipse(c, r - 0.5, r - 0.5)
        if self.isChecked():
            p.setPen(Qt.NoPen)
            p.setBrush(ORANGE)
            p.drawRoundedRect(QtCore.QRectF(c.x() - 10, self.height() - 4, 20, 3), 1.5, 1.5)
        p.end()


def pick_color(parent, initial):
    """Qt's own colour picker in the player's dark colours (basic colours,
    colour square and hue strip, hex field, pick from the screen).
    Returns '#rrggbb', or None if cancelled."""
    dlg = QtWidgets.QColorDialog(QtGui.QColor(initial or "#e8c547"), parent)
    dlg.setWindowTitle("Drawing colour")
    dlg.setOption(QtWidgets.QColorDialog.DontUseNativeDialog, True)
    try:
        for box in dlg.findChildren(QtWidgets.QDialogButtonBox):
            ok = box.button(QtWidgets.QDialogButtonBox.Ok)
            if ok is not None:
                ok.setText("Use colour")
    except Exception:  # cosmetic only (the OK button's label)
        pass
    run = getattr(dlg, "exec", None) or dlg.exec_
    if run() != QtWidgets.QDialog.Accepted:
        return None
    color = dlg.currentColor()
    return color.name() if color.isValid() else None


class ElideLabel(QtWidgets.QLabel):
    """A name that's cut short with "..." instead of widening the row (a long
    Blue Pencil file name pushed the opacity and x buttons out of sight)."""

    def __init__(self, text):
        super(ElideLabel, self).__init__(text)
        self._full = text
        self.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        self.setMinimumWidth(20)
        self.setToolTip(text)

    def minimumSizeHint(self):
        return QtCore.QSize(20, super(ElideLabel, self).minimumSizeHint().height())

    def resizeEvent(self, event):
        super(ElideLabel, self).resizeEvent(event)
        QtWidgets.QLabel.setText(self, self.fontMetrics().elidedText(self._full, Qt.ElideMiddle,
                                                                     max(0, int(self.width()))))


class HeadRow(QtWidgets.QFrame):
    """A heading in the layer list: "you", or a person you import (orange
    with Update when they've saved newer drawings; Revert after an update)."""

    def __init__(self, panel, row):
        super(HeadRow, self).__init__()
        self.panel, self.row, self.key = panel, row, row["key"]
        d = panel.drawer
        self.setObjectName("head")
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(4, 3, 4, 3)
        lay.setSpacing(5)
        me = row["kind"] == "me"
        person = None if me else row["row"]
        status = person["status"] if person else "current"
        self.setProperty("update", "true" if status == "update" else "false")
        pic = QtWidgets.QLabel()
        pic.setPixmap(icon("person", "#f0c890" if status == "update" else ("#d6d6d6" if me else "#b9c7d6"),
                           12).pixmap(12, 12))
        lay.addWidget(pic)
        key = d.cam() or ""
        on = " · on %s" % key.split("@", 1)[1] if "@" in key else ""      # b8: drawing on another shot
        dot = " \u25cf" if status == "update" else ""                   # b8: they've saved newer drawings
        label = ElideLabel("%s (you)%s" % (d.user, on) if me else person["user"] + dot)
        label.setStyleSheet("font-size: 12px; font-weight: bold; color: %s;" % (
            "#f5d7a8" if status == "update" else "#f2f2f2"))
        lay.addWidget(label, 1)
        if person:
            shown = d.person_visible(person)
            eye = _button(kind="eye" if shown else "eye_off", object_name="flat",
                          tip=("Hide %s's drawings" if shown else "Show %s's drawings") % person["user"])
            eye.clicked.connect(lambda: d.set_person_visible(person["user"], not d.person_visible(person)))
            lay.addWidget(eye)
            if status == "update":
                b = _button("Update", "%s has saved newer drawings: show them" % person["user"], object_name="update")
                b.clicked.connect(lambda: d.update_person(person["user"]))
                lay.addWidget(b)
            elif status == "revert":
                b = _button("Revert", "Go back to the %s drawings you had before updating" % person["user"],
                            object_name="revert")
                b.clicked.connect(lambda: d.revert_person(person["user"]))
                lay.addWidget(b)
            rm = _button(kind="x", tip="Remove %s from your list (their files are untouched)" % person["user"],
                         object_name="flat")
            rm.clicked.connect(lambda: d.remove_row(self.key))
            lay.addWidget(rm)


class LayerRow(QtWidgets.QFrame):
    def __init__(self, panel, row):
        super(LayerRow, self).__init__()
        self.panel, self.row, self.key = panel, row, row["key"]
        d = panel.drawer
        self.setObjectName("row")
        mine = row["kind"] == "mine"
        # Your active layer (the pen draws there) is highlighted, unless an
        # imported row is selected (clicked): then that one is, for the trash
        # button. Imported layers are always locked: duplicate one to edit it.
        selected = d.selected == self.key
        active = mine and d.selected is None and d.mine_now().active == row["layer"]["id"]
        self.setProperty("active", "true" if (active or selected) else "false")
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(18 if row["kind"] in ("mine", "person") else 4, 1, 4, 1)
        lay.setSpacing(3)
        visible = d.row_value(self.key, "visible")
        eye = _button(kind="eye" if visible else "eye_off", tip="Show or hide", object_name="flat")
        eye.clicked.connect(lambda: d.set_row(self.key, visible=not d.row_value(self.key, "visible")) or panel.refresh())
        lay.addWidget(eye)
        locked = bool(row["layer"].get("locked")) if mine else True
        if mine:
            lock = _button(kind="lock" if locked else "unlock",
                           tip="Locked: click to unlock" if locked else "Unlocked: click to lock (no drawing, "
                               "erasing, clearing, undo or deleting)", object_name="flat")
            lock.setIcon(icon("lock", ORANGE.name()) if locked else icon("unlock", "#8a8a8a"))
            lock.clicked.connect(lambda: d.set_row(self.key, locked=not d.row_value(self.key, "locked")) or panel.refresh())
        else:
            lock = _button(kind="lock", tip="Someone else's drawing: always locked. Duplicate it to edit."
                           if row["kind"] == "person" else "A Blue Pencil file: read-only", object_name="flat")
            lock.setIcon(icon("lock", ORANGE.name()))
        lay.addWidget(lock)
        if row["kind"] in ("mine", "person"):
            name = row["layer"]["name"]
        else:
            name = "BP: " + row["row"].name
        label = ElideLabel(name)
        dim = not visible or (mine and locked)
        style = "font-size: 12px; color: %s;" % ("#8a8a8a" if dim else "#f0f0f0")
        if active or selected:
            style += " font-weight: bold;"
        if not mine:
            style += " font-style: italic;"
        if row["kind"] == "blue":
            pic = QtWidgets.QLabel()
            pic.setPixmap(icon("pen", "#b9c7d6", 12).pixmap(12, 12))
            lay.addWidget(pic)
        label.setStyleSheet(style)
        source = row["layer"].get("source") if mine else None
        if mine:
            tip = "%s\nDouble-click to rename" % name
            if source:
                tip += "\nCopied from %s's %s" % (source.get("user"), source.get("layer"))
        else:
            tip = "%s\nRead-only. Click to select; the trash removes it from your list (the files are untouched)" % name
        label.setToolTip(tip)
        lay.addWidget(label, 1)
        if active:
            mark = QtWidgets.QLabel()
            mark.setPixmap(icon("pen", ORANGE.name(), 12).pixmap(12, 12))
            mark.setToolTip("You're drawing on this layer")
            lay.addWidget(mark)
        if row["kind"] == "person":
            dup = _button(kind="copy", tip="Duplicate to my layers (to edit it)")
            dup.setObjectName("dup")
            dup.clicked.connect(lambda: d.duplicate(self.key))
            lay.addWidget(dup)
        pct = int(round(100 * float(d.row_value(self.key, "opacity") or 0)))
        op = _button("%d%%" % pct, "Opacity", "opacity", object_name="opacity")
        op.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        op.setIconSize(QtCore.QSize(12, 12))
        op.clicked.connect(lambda: panel.opacity_popup(self.key, op))
        lay.addWidget(op)
        if row["kind"] == "blue":
            rm = _button(kind="x", tip="Remove from the list (the file is untouched)", object_name="flat")
            rm.clicked.connect(lambda: d.remove_row(self.key))
            lay.addWidget(rm)
        self.mine = mine

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        d = self.panel.drawer
        if self.mine:
            d.selected = None
            d.mine_now().active = self.row["layer"]["id"]     # picking a layer isn't a change to save
        else:
            d.selected = self.key           # imported: select it (for the trash button)
        self.panel.refresh()

    def mouseDoubleClickEvent(self, event):
        if not self.mine:
            return
        layer = self.row["layer"]
        name, ok = QtWidgets.QInputDialog.getText(self, "Rename layer", "Name:", text=layer["name"])
        if ok and name.strip():
            self.panel.drawer.mine_now().rename_layer(layer["id"], name.strip())
            self.panel.drawer.edited()
            self.panel.refresh()


def _line(lay):
    """A thin horizontal line between sections of the drawing strip."""
    line = QtWidgets.QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet("background: #333")
    lay.addWidget(line)
