"""0.8.0b12: Sync kept dropping at the studio: bare S in the player toggled it
(remembered), and S is Set Key in Maya. No single-letter key for Sync or the
live/reference flip (R, Maya's scale) any more; an orange SYNC OFF tag shows on
the picture while it's off. Also: your shot's card shows the chosen movie with
an orange REF tag."""
import os
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
p = open(os.path.join(REPO, "bgcache", "player.py")).read()
keys = p.split("def keyPressEvent")[1].split("def keyReleaseEvent")[0]
bare = [l for l in keys.splitlines() if ("Qt.Key_S " in l or "Qt.Key_S)" in l or "Qt.Key_S:" in l or "Qt.Key_R " in l or "Qt.Key_R)" in l)
        and "ctrl and" not in l]
assert not bare, bare
print("ok: no bare S (Set Key in Maya) or R (scale) in the player (Ctrl+S saves drawings)")
assert 'self._overlay_tag(p, target, "SYNC OFF", y=tag_y)' in p and "if live and not self.sync:" in p
print("ok: SYNC OFF tag on the picture while Sync is off")
u = open(os.path.join(REPO, "bgcache", "continuity", "ui.py")).read()
assert "def set_reference_tag" in u and '"REF \\u00b7 %s"' in u and "card.set_reference(image" in u
print("ok: your shot's card shows the reference movie's frame with an orange REF tag")
