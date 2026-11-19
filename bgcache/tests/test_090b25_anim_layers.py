"""0.9.0b25: animation layers. A layer made after Start asks for a reload;
mute / solo / weight are followed by themselves."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from bgcache import refreshing as r

src = lambda name: open(os.path.join(os.path.dirname(HERE), "bgcache", name)).read()
old = {"references": {}, "constraints": 0, "deformers": 0, "objects": 5, "anim_layers": 0, "anim_layer_channels": 0}
new = dict(old, anim_layers=1, anim_layer_channels=3)
assert r.structure_changes(old, new) == ["1 animation layer added", "3 channels on animation layers added"]
assert r.structure_changes(new, dict(new, anim_layer_channels=4)) == ["1 channel on animation layers added"]
assert r.structure_changes(old, dict(old)) == []
print("ok: a layer made, or controls added to one, is something Refresh asks to reload for")
assert r.note(["anim-layer"]) == "Scene changed: an animation layer was made"
print("ok: making a layer shows the orange note")
s, a, w, c = src("scene.py"), src("controller_assets.py"), src("worker.py"), src("controller_scene.py")
assert "def anim_layer_values" in s and "def anim_layer_counts" in s and '"anim_layers": layers' in c
assert "self._send_anim_layers()" in a and '"op": "anim_layers"' in a and "layer in before and before[layer] != vals" in a
assert 'op == "anim_layers"' in w and "cmds.animLayer(layer, edit=True, **{flag: value})" in w
print("ok: mute, solo, weight and mode of the layers the background Maya has are sent by themselves")
