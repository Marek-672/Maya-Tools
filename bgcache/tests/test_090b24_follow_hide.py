"""0.9.0b24: Ctrl+H / Shift+H on what you've selected, and display layers,
are followed without Refresh."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
src = lambda name: open(os.path.join(os.path.dirname(HERE), "bgcache", name)).read()
a, e = src("controller_assets.py"), src("controller_edits.py")
assert "def _note_selected" in a and "self._note_selected(selected)" in e and "_note_transform" in e
assert "self.vis_base.get(node)" in a and "def _layer_changes" in a
assert "changed += [v for v in self._selected_changes()" in a and "layers = self._layer_changes()" in a
print("ok: the things you select are watched for show / hide, against what the background Maya was given")
assert "self._refresh_sent[plug] = value" in a and "self.vis_base[plug[:-len" in a
print("ok: what's sent by itself isn't sent again by Refresh")
assert "WATCHED_MAX = 400" in a and "scene._mouse_held()" in a
print("ok: bounded (400 things, once a second, not while a mouse button is down)")
