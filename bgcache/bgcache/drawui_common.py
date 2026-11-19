"""Drawing in the player: shared imports and colours (drawui.py and its
topic files, drawui_*.py)."""
import collections
import os
import re
import time
import zipfile

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:  # Maya 2024 and earlier (PySide2)
    from PySide2 import QtCore, QtGui, QtWidgets

from bgcache import drawing
from bgcache import hotkeys
from bgcache import profile

Qt = QtCore.Qt
ORANGE = QtGui.QColor(224, 138, 69)
DRAW_STYLE = """
QWidget#drawStrip { background: #1e1e1e; border-left: 1px solid #333; }
QLabel#head { color: #9a9a9a; font-size: 11px; }
QLabel#hint { color: #a8a8a8; font-size: 11px; background: #262626; border-radius: 3px; padding: 6px; }
QToolButton#swatch { background: transparent; border: none; padding: 0; }
QScrollArea#layers { background: #1e1e1e; border: 1px solid #2c2c2c; border-radius: 3px; }
QWidget#layersView, QWidget#layerList { background: #1e1e1e; }
QLabel { color: #cfcfcf; }
QToolButton { color: #ebebeb; background: #343434; border: 1px solid #4a4a4a; border-radius: 3px; padding: 3px 8px; font-size: 12px; }
QToolButton:checked { background: #3d5a73; border-color: #4f7393; color: #f0f0f0; }
QToolButton:hover { background: #3d3d3d; }
QToolButton:checked:hover { background: #46667f; }
QToolButton::menu-indicator { image: none; }
QToolButton#flat { background: transparent; border: none; padding: 1px; }
QToolButton#flat:hover { background: #3a3a3a; }
QToolButton#opacity { background: transparent; border: none; color: #bdbdbd; font-size: 10px; padding: 1px 3px; }
QToolButton#opacity:hover { background: #3a3a3a; }
QToolButton#dup { padding: 1px 3px; }
QFrame#row { border: 1px solid transparent; border-radius: 3px; }
QFrame#row[active="true"] { background: #3a4f63; border-color: #5f84a8; }
QFrame#head { border: 1px solid transparent; border-top-color: #333; border-radius: 0; }
QFrame#head[update="true"] { background: #3a2c1e; border: 1px solid #b8662a; border-radius: 3px; }
QToolButton#update { background: #b8662a; border: 1px solid #e08a45; color: #fff4e8; font-weight: bold; font-size: 11px; padding: 1px 9px; }
QToolButton#update:hover { background: #c9733a; }
QToolButton#revert { font-size: 11px; padding: 1px 9px; }
QToolButton#save { background: #b8662a; border: 1px solid #e08a45; color: #fff4e8; font-weight: bold; padding: 6px 8px; }
QToolButton#save:hover { background: #c9733a; }
QToolButton#save:disabled { background: #2c2c2c; border-color: #3a3a3a; color: #777; font-weight: normal; }
QLabel#unsaved { color: #f5c27a; font-size: 11px; }
QSpinBox { background: #262626; color: #e6e6e6; border: 1px solid #4a4a4a; border-radius: 3px; font-size: 12px; }
QSlider::groove:horizontal { height: 4px; background: #444; border-radius: 2px; }
QSlider::handle:horizontal { background: #9ec3e6; width: 12px; margin: -5px 0; border-radius: 6px; }
"""


# --------------------------------------------------------------------------
# Keys: your Maya hotkeys in the player
# --------------------------------------------------------------------------

__all__ = ['DRAW_STYLE', 'ORANGE', 'Qt', 'QtCore', 'QtGui', 'QtWidgets', 'collections', 'drawing', 'hotkeys', 'os', 'profile', 're', 'time', 'zipfile']
