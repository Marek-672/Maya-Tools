"""Drawing in the player: the small icons drawn for the strip's buttons, and painting strokes.

Part of drawui.py (the Drawer and the drawing strip); see DEVELOPER.md."""
from bgcache.drawui_common import *  # noqa: F401,F403 (Qt, drawing, profile, colours)


# --------------------------------------------------------------------------
# Icons
# --------------------------------------------------------------------------
def icon(kind, color="#d6d6d6", size=16):
    """A small line icon (16 px drawing, scaled to size) for the drawing
    strip and the player: kind is one of ICONS."""
    pm = QtGui.QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)
    pen = QtGui.QPen(QtGui.QColor(color), 1.4)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    s = size / 16.0
    p.scale(s, s)
    path = QtGui.QPainterPath()
    draw = ICONS.get(kind)
    if draw is not None:
        draw(p, path, color, kind)
    p.end()
    return QtGui.QIcon(pm)


def _icon_eye(p, path, color, kind):
    """An eye (layer shown); eye_off adds a slash (hidden)."""
    path.moveTo(1.5, 8)
    path.quadTo(8, 1.5, 14.5, 8)
    path.quadTo(8, 14.5, 1.5, 8)
    p.drawPath(path)
    p.drawEllipse(QtCore.QPointF(8, 8), 2.2, 2.2)
    if kind == "eye_off":
        p.drawLine(QtCore.QPointF(2.5, 13.5), QtCore.QPointF(13.5, 2.5))


def _icon_lock(p, path, color, kind):
    """A closed padlock with a tinted body: clearly locked."""
    body = QtCore.QRectF(3, 7.5, 10, 7)
    tint = QtGui.QColor(color)
    tint.setAlpha(70)
    p.fillRect(body.adjusted(0.5, 0.5, -0.5, -0.5), tint)
    p.drawRoundedRect(body, 1, 1)
    path.moveTo(5.5, 7.5)
    path.lineTo(5.5, 5)
    path.arcTo(QtCore.QRectF(5.5, 2.5, 5, 5), 180, -180)
    path.lineTo(10.5, 7.5)
    p.drawPath(path)


def _icon_unlock(p, path, color, kind):
    """An open padlock: body to the right, shackle swung open to the left."""
    p.drawRoundedRect(QtCore.QRectF(6, 8, 8, 6), 1, 1)
    path.moveTo(8.5, 8)
    path.lineTo(8.5, 5.5)
    path.arcTo(QtCore.QRectF(3.5, 3, 5, 5), 0, 180)
    path.lineTo(3.5, 7)
    p.drawPath(path)


def _icon_copy(p, path, color, kind):
    """Two sheets (duplicate)."""
    p.drawRoundedRect(QtCore.QRectF(2.5, 5.5, 8, 8.5), 1, 1)
    path.moveTo(5.5, 5.5)
    path.lineTo(5.5, 2.5)
    path.lineTo(13.5, 2.5)
    path.lineTo(13.5, 11)
    path.lineTo(10.5, 11)
    p.drawPath(path)


def _icon_person(p, path, color, kind):
    """Head and shoulders (someone's drawings)."""
    p.drawEllipse(QtCore.QPointF(8, 5.5), 2.6, 2.6)
    path.moveTo(3, 14)
    path.cubicTo(3.5, 10, 12.5, 10, 13, 14)
    p.drawPath(path)


def _icon_plus(p, path, color, kind):
    """A plus (new layer)."""
    p.drawLine(QtCore.QPointF(8, 3), QtCore.QPointF(8, 13))
    p.drawLine(QtCore.QPointF(3, 8), QtCore.QPointF(13, 8))


def _icon_arrow(p, path, color, kind):
    """A chevron pointing up or down (move a layer)."""
    y0, y1 = (10, 5) if kind == "up" else (6, 11)
    path.moveTo(4, y0)
    path.lineTo(8, y1)
    path.lineTo(12, y0)
    p.drawPath(path)


def _icon_trash(p, path, color, kind):
    """A bin (delete)."""
    p.drawLine(QtCore.QPointF(3, 4.5), QtCore.QPointF(13, 4.5))
    path.moveTo(6.5, 4.5)
    path.lineTo(6.5, 2.5)
    path.lineTo(9.5, 2.5)
    path.lineTo(9.5, 4.5)
    path.moveTo(4.5, 4.5)
    path.lineTo(5.3, 14)
    path.lineTo(10.7, 14)
    path.lineTo(11.5, 4.5)
    p.drawPath(path)


def _icon_reload(p, path, color, kind):
    """A circular arrow (update)."""
    p.drawArc(QtCore.QRectF(3, 3, 10, 10), 30 * 16, 290 * 16)
    path.moveTo(13, 2.5)
    path.lineTo(13, 6)
    path.lineTo(9.5, 6)
    p.drawPath(path)


def _icon_pen(p, path, color, kind):
    """A pen (Draw)."""
    path.moveTo(3, 13)
    path.lineTo(4, 9.5)
    path.lineTo(11, 2.5)
    path.lineTo(13.5, 5)
    path.lineTo(6.5, 12)
    path.closeSubpath()
    p.drawPath(path)


def _icon_x(p, path, color, kind):
    """A cross (remove)."""
    p.drawLine(QtCore.QPointF(4.5, 4.5), QtCore.QPointF(11.5, 11.5))
    p.drawLine(QtCore.QPointF(11.5, 4.5), QtCore.QPointF(4.5, 11.5))


def _icon_opacity(p, path, color, kind):
    """A half-filled circle (opacity)."""
    p.drawEllipse(QtCore.QPointF(8, 8), 5.5, 5.5)
    half = QtGui.QPainterPath()
    half.moveTo(8, 2.5)
    half.arcTo(QtCore.QRectF(2.5, 2.5, 11, 11), 90, -180)
    half.closeSubpath()
    p.fillPath(half, QtGui.QBrush(QtGui.QColor(color)))


ICONS = {
    "eye": _icon_eye,
    "eye_off": _icon_eye,
    "lock": _icon_lock,
    "unlock": _icon_unlock,
    "copy": _icon_copy,
    "person": _icon_person,
    "plus": _icon_plus,
    "up": _icon_arrow,
    "down": _icon_arrow,
    "trash": _icon_trash,
    "reload": _icon_reload,
    "pen": _icon_pen,
    "x": _icon_x,
    "opacity": _icon_opacity,
}


# --------------------------------------------------------------------------
# Painting strokes
# --------------------------------------------------------------------------
def paint_strokes(p, strokes, opacity=1.0, tint=None):
    """Strokes in frame pixels; the painter is already mapped to the frame."""
    if not strokes or opacity <= 0:
        return
    p.save()
    p.setOpacity(p.opacity() * opacity)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)
    for st in strokes:
        pts = st.get("p") or []
        if not pts:
            continue
        color = QtGui.QColor(tint or st.get("c") or "#e8c547")
        width = float(st.get("w", 4.0))
        pressures = [pt[2] if len(pt) > 2 else 1.0 for pt in pts]
        if len(pts) == 1:
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            r = width * pressures[0] / 2.0
            p.drawEllipse(QtCore.QPointF(pts[0][0], pts[0][1]), r, r)
            continue
        if min(pressures) > 0.999:
            path = QtGui.QPainterPath(QtCore.QPointF(pts[0][0], pts[0][1]))
            for pt in pts[1:]:
                path.lineTo(pt[0], pt[1])
            pen = QtGui.QPen(color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
        else:
            for a, b, pa, pb in zip(pts, pts[1:], pressures, pressures[1:]):
                pen = QtGui.QPen(color, max(0.5, width * (pa + pb) / 2.0), Qt.SolidLine, Qt.RoundCap)
                p.setPen(pen)
                p.drawLine(QtCore.QPointF(a[0], a[1]), QtCore.QPointF(b[0], b[1]))
    p.restore()
