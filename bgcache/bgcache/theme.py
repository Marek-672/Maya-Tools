"""The player's dark colour scheme, for the whole app.

The player window has its own style sheet (player.STYLE), but dialogs and
popups (rename layer, delete layer, file pickers, the colour picker) are
separate windows and don't get it, and plain widgets inside scroll areas fall
back to the system palette, which in mayapy is light grey/white. apply()
sets a dark Fusion palette and a small style sheet on the application, so
every window bgcache's player opens uses the same colours.
"""

# One set of colours for everything (the player's STYLE uses the same values)
BG = "#121212"          # behind the picture
PANEL = "#1e1e1e"       # side strip, lists, dialogs
BAR = "#232323"         # toolbar, playback bar
FIELD = "#262626"       # text fields, spin boxes
BUTTON = "#343434"
BORDER = "#4a4a4a"
TEXT = "#ebebeb"
TEXT_DIM = "#9a9a9a"
DISABLED = "#6a6a6a"
SELECT = "#3d5a73"      # selection, checked buttons
ORANGE = "#e08a45"      # Draw mode

APP_STYLE = """
QToolTip { color: %(TEXT)s; background: #2c2c2c; border: 1px solid #555; padding: 3px; }
QMenu { background: #2c2c2c; color: %(TEXT)s; border: 1px solid #555; }
QMenu::item:selected { background: %(SELECT)s; }
QMenu::item:disabled { color: %(TEXT_DIM)s; }
QMenu::separator { height: 1px; background: #444; margin: 4px 6px; }
QDialog { background: %(PANEL)s; }
QDialog QLabel { color: %(TEXT)s; }
QDialog QPushButton { color: %(TEXT)s; background: %(BUTTON)s; border: 1px solid %(BORDER)s;
                      border-radius: 3px; padding: 4px 12px; font-size: 12px; min-width: 60px; }
QDialog QPushButton:hover { background: #3d3d3d; }
QDialog QPushButton:default { border-color: %(ORANGE)s; }
QLineEdit, QSpinBox, QComboBox { background: %(FIELD)s; color: %(TEXT)s; border: 1px solid %(BORDER)s;
                                 border-radius: 3px; padding: 2px 4px; selection-background-color: %(SELECT)s; }
QAbstractItemView { background: %(PANEL)s; color: %(TEXT)s; selection-background-color: %(SELECT)s;
                    alternate-background-color: #242424; }
QHeaderView::section { background: %(BAR)s; color: %(TEXT_DIM)s; border: none; padding: 3px; }
QScrollBar:horizontal { background: #2b2b2b; height: 12px; margin: 0; border: none; }
QScrollBar:vertical { background: #2b2b2b; width: 12px; margin: 0; border: none; }
QScrollBar::handle:horizontal { background: #5d5d5d; min-width: 30px; border-radius: 3px; margin: 2px; }
QScrollBar::handle:vertical { background: #5d5d5d; min-height: 30px; border-radius: 3px; margin: 2px; }
QScrollBar::handle:hover { background: #727272; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; border: none; background: none; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
""" % dict(TEXT=TEXT, TEXT_DIM=TEXT_DIM, SELECT=SELECT, PANEL=PANEL, BUTTON=BUTTON,
           BORDER=BORDER, ORANGE=ORANGE, FIELD=FIELD, BAR=BAR)


def palette(QtGui):
    """A dark QPalette (Fusion uses it for anything a style sheet doesn't cover)."""
    C = QtGui.QColor
    P = QtGui.QPalette
    pal = P()
    for role, color in ((P.Window, PANEL), (P.WindowText, TEXT), (P.Base, FIELD),
                        (P.AlternateBase, "#242424"), (P.ToolTipBase, "#2c2c2c"), (P.ToolTipText, TEXT),
                        (P.Text, TEXT), (P.Button, BUTTON), (P.ButtonText, TEXT), (P.BrightText, "#ffffff"),
                        (P.Highlight, SELECT), (P.HighlightedText, "#ffffff"), (P.Link, "#9cc8ee"),
                        (P.Light, "#4a4a4a"), (P.Midlight, "#3a3a3a"), (P.Mid, "#2c2c2c"),
                        (P.Dark, "#161616"), (P.Shadow, "#000000")):
        pal.setColor(role, C(color))
    for role in (P.WindowText, P.Text, P.ButtonText):
        pal.setColor(P.Disabled, role, C(DISABLED))
    return pal


def apply(app, QtGui, QtWidgets):
    """Dark Fusion look for the whole player app (all its windows). Never raises."""
    try:
        style = QtWidgets.QStyleFactory.create("Fusion")
        if style is not None:
            app.setStyle(style)
    except Exception:  # the look is cosmetic: never stop the player for it
        pass
    try:
        app.setPalette(palette(QtGui))
    except Exception:  # the look is cosmetic: never stop the player for it
        pass
    try:
        app.setStyleSheet(APP_STYLE)
    except Exception:  # the look is cosmetic: never stop the player for it
        pass
