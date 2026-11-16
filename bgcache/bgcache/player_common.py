"""The player's shared imports, colours and small helpers (used by
player.py and its topic files, player_*.py)."""
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
MAYA_RANGE = QtGui.QColor(143, 192, 232)  # b8: your Maya's playback range, under the handles
OUTSIDE_CUT = QtGui.QColor(160, 120, 220) # b8: frames outside the shot's cut (animated past it)
NOT_RENDERED = QtGui.QColor(66, 66, 66)   # b8: hatching on frames never rendered yet
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

__all__ = ['BAR_H', 'FOCUS', 'FitLabel', 'FlowLayout', 'GREEN', 'LRU_SIZE', 'MAYA_RANGE', 'NOT_RENDERED', 'OUTSIDE_CUT', 'Qt', 'QtCore', 'QtGui', 'QtWidgets', 'RED', 'STAGED', 'STYLE', 'TAB_H', 'TAB_W', 'TICK', 'TICK_EDGE', '_QAction', '__version__', '_check_item', '_checkbox_style', '_icon', '_menu_section', '_separator', '_shift', '_tool', 'collections', 'common', 'os', 'sys', 'time']
