"""Small Qt pieces shared by the player and the continuity strip: drawn
icons for the playback buttons, tool buttons, the filmstrip checkbox style,
and a label that never widens the window."""
import os

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:  # Maya 2024 and earlier (PySide2)
    from PySide2 import QtCore, QtGui, QtWidgets

Qt = QtCore.Qt


def _icon(kind):
    pix = QtGui.QPixmap(16, 16)
    pix.fill(Qt.transparent)
    p = QtGui.QPainter(pix)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)
    p.setPen(Qt.NoPen)
    light, key = QtGui.QColor(214, 214, 214), QtGui.QColor(217, 164, 65)

    def tri(points, color=light):
        p.setBrush(color)
        p.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in points]))

    def bar(x):
        p.setBrush(light)
        p.drawRect(QtCore.QRectF(x, 3, 2, 10))

    def diamond(cx):
        tri([(cx, 5.5), (cx + 2, 8), (cx, 10.5), (cx - 2, 8)], key)

    if kind == "start":
        bar(3); tri([(13, 3), (13, 13), (6, 8)])
    elif kind == "prev_frame":
        tri([(10, 3), (10, 13), (4, 8)]); bar(11)
    elif kind == "prev_key":
        tri([(9, 3), (9, 13), (3, 8)]); diamond(12.5)
    elif kind == "play_back":
        tri([(12, 3), (12, 13), (4, 8)])
    elif kind == "play":
        tri([(4, 3), (4, 13), (12, 8)])
    elif kind == "pause":
        p.setBrush(light); p.drawRect(QtCore.QRectF(4, 3, 3, 10)); p.drawRect(QtCore.QRectF(9, 3, 3, 10))
    elif kind == "next_key":
        diamond(3.5); tri([(7, 3), (7, 13), (13, 8)])
    elif kind == "next_frame":
        bar(3); tri([(6, 3), (6, 13), (12, 8)])
    elif kind == "end":
        tri([(3, 3), (3, 13), (10, 8)]); bar(11)
    p.end()
    return QtGui.QIcon(pix)


_CHECK_STYLE = None


def _checkbox_style():
    """Filmstrip checkbox (standard size): white outline on a dark backing so it shows on
    any thumbnail; blue with a white tick when checked (same blue as ticked cards)."""
    global _CHECK_STYLE
    if _CHECK_STYLE is None:
        import tempfile
        path = os.path.join(tempfile.gettempdir(), "bgcache_check_%d.png" % os.getpid())
        pix = QtGui.QPixmap(10, 10)
        pix.fill(Qt.transparent)
        p = QtGui.QPainter(pix)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(1.6, 5.4), QtCore.QPointF(4.0, 7.8),
                                        QtCore.QPointF(8.4, 2.2)]))
        p.end()
        pix.save(path, "PNG")
        _CHECK_STYLE = """
QCheckBox { background: transparent; spacing: 0px; }
QCheckBox::indicator { width: 13px; height: 13px; border: 2px solid #ffffff;
                       border-radius: 3px; background: rgba(0, 0, 0, 170); }
QCheckBox::indicator:hover { border-color: #9cc8ee; background: rgba(40, 70, 100, 200); }
QCheckBox::indicator:checked { background: #2f86d6; border-color: #ffffff; image: url(%s); }
""" % path.replace("\\", "/")
    return _CHECK_STYLE


def _tool(text=None, checkable=False, tip=None, icon=None):
    b = QtWidgets.QToolButton()
    if text:
        b.setText(text)
    if icon:
        b.setIcon(_icon(icon))
        b.setFixedSize(32, 28)
    b.setCheckable(checkable)
    b.setFocusPolicy(Qt.NoFocus)
    if tip:
        b.setToolTip(tip)
    return b


def _text_width(metrics, text):
    return metrics.horizontalAdvance(text) if hasattr(metrics, "horizontalAdvance") else metrics.width(text)


class FitLabel(QtWidgets.QLabel):
    """A label that never makes the window wider: it shows the first of its
    texts that fits, cut short with "..." if none does, with the full text on
    hover. (A plain QLabel won't shrink below its text, so a long line of shot
    names forced the player's minimum width.)"""

    def __init__(self, elide=None):
        super(FitLabel, self).__init__("")
        self._texts = [""]
        self._elide = Qt.ElideRight if elide is None else elide
        self.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        self.setMinimumWidth(40)

    def set_texts(self, texts):
        texts = [t for t in (texts if isinstance(texts, (list, tuple)) else [texts]) if t is not None] or [""]
        self._texts = list(texts)
        self.setToolTip(texts[0] if len(texts[0]) > 0 else "")
        self._fit()

    def setText(self, text):
        self.set_texts([text])

    def text_full(self):
        return self._texts[0]

    def sizeHint(self):
        hint = super(FitLabel, self).sizeHint()
        return QtCore.QSize(_text_width(self.fontMetrics(), self._texts[0]) + 8, hint.height())

    def minimumSizeHint(self):
        return QtCore.QSize(40, super(FitLabel, self).minimumSizeHint().height())

    def resizeEvent(self, event):
        super(FitLabel, self).resizeEvent(event)
        self._fit()

    def _fit(self):
        fm, room = self.fontMetrics(), max(0, int(self.width()) - 4)
        pick = next((t for t in self._texts if int(_text_width(fm, t)) <= room), None)
        if pick is None:
            pick = fm.elidedText(self._texts[-1], self._elide, room)
        QtWidgets.QLabel.setText(self, pick)


class FlowLayout(QtWidgets.QLayout):
    """A row of widgets that wraps onto more rows when the window is too
    narrow for it, so a long toolbar never stops the window from shrinking.
    addStretch() marks where a row's spare width goes (the toolbar's right
    group stays right-aligned while everything fits on one row)."""

    STRETCH = "stretch"

    def __init__(self, parent=None, spacing=8, margins=(10, 4, 10, 4)):
        super(FlowLayout, self).__init__(parent)
        self._items = []
        self._space = spacing
        self.setContentsMargins(*margins)

    # QLayout plumbing
    def addItem(self, item):
        self._items.append(item)

    def addStretch(self, _factor=1):
        self._items.append(self.STRETCH)

    def count(self):
        return len([i for i in self._items if i is not self.STRETCH])

    def _real(self):
        return [i for i in self._items if i is not self.STRETCH]

    def itemAt(self, index):
        real = self._real()
        return real[index] if 0 <= index < len(real) else None

    def takeAt(self, index):
        real = self._real()
        if 0 <= index < len(real):
            item = real[index]
            self._items.remove(item)
            return item
        return None

    def expandingDirections(self):
        return Qt.Orientations(0) if hasattr(Qt, "Orientations") else Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QtCore.QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect):
        super(FlowLayout, self).setGeometry(rect)
        self._do_layout(rect, apply=True)

    def sizeHint(self):
        m = self.contentsMargins()
        w = sum(i.sizeHint().width() + self._space for i in self._real()) - self._space
        h = max([i.sizeHint().height() for i in self._real()] or [0])
        return QtCore.QSize(w + m.left() + m.right(), h + m.top() + m.bottom())

    def minimumSize(self):
        m = self.contentsMargins()
        w = max([i.minimumSize().width() for i in self._real()] or [0])
        h = max([i.minimumSize().height() for i in self._real()] or [0])
        return QtCore.QSize(w + m.left() + m.right(), h + m.top() + m.bottom())

    def _lines(self, width):
        """The items in rows that fit `width` (stretch markers kept in place)."""
        lines, line, used = [], [], 0
        for item in self._items:
            if item is self.STRETCH:
                line.append(item)
                continue
            widget = item.widget()
            if widget is not None and widget.isHidden():
                continue
            w = item.sizeHint().width()
            need = w if not used else used + self._space + w
            if line and used and need > width:
                lines.append(line)
                line, used = [], 0
                need = w
            line.append(item)
            used = need
        if line:
            lines.append(line)
        return lines

    def _do_layout(self, rect, apply):
        m = self.contentsMargins()
        area = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        y = area.y()
        for line in self._lines(area.width()):
            items = [i for i in line if i is not self.STRETCH]
            if not items:
                continue
            row_h = max(i.sizeHint().height() for i in items)
            used = sum(i.sizeHint().width() for i in items) + self._space * (len(items) - 1)
            spare = max(0, area.width() - used)
            x = area.x()
            for item in line:
                if item is self.STRETCH:
                    x += spare
                    spare = 0
                    continue
                size = item.sizeHint()
                if apply:
                    item.setGeometry(QtCore.QRect(QtCore.QPoint(x, y + (row_h - size.height()) // 2), size))
                x += size.width() + self._space
            y += row_h + self._space
        return y - self._space - rect.y() + m.bottom()
