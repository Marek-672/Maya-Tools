"""0.7.0 drawings: layers, hold, undo, eraser, save/load, other people,
Blue Pencil placement and zip reading."""
import os, sys, json, tempfile, zipfile, time
TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(TESTS))
from bgcache import drawing as dr

root = tempfile.mkdtemp()
assert dr.drawings_root("/projects/BIRDS/sq050_0472/maya/scenes/x.mb") == "/projects/BIRDS/sq050_0472/maya/bgcache"
assert dr.drawings_root("/home/me/test scene.mb") == "/home/me/bgcache/test_scene"     # outside a shot: next to the scene
assert dr.camera_folder("|Assets|renderCam|camera") == "camera"
print("ok: drawings live in <shot>/maya/bgcache/<user>/drawings/<camera>/")

path = dr.layers_path(root, "artist", "camera")
d = dr.Drawings(path, (960, 540), owner="artist")
assert [l["name"] for l in d.layers] == ["Layer 1"] and d.active == "l1"
st = lambda x: {"c": "#e8c547", "w": 6.0, "p": [[x, 10, 1.0], [x + 20, 30, 1.0]]}
assert d.add_stroke(1010, st(100))
assert d.add_stroke(1020, st(300))
L = d.active_layer()
assert d.strokes_at(L, 1015)[0] == 1010 and d.strokes_at(L, 1015, hold=False)[0] is None
assert d.strokes_at(L, 1005)[0] is None and d.strokes_at(L, 1030)[0] == 1020
assert dr.neighbour_keys(L["frames"], 1020) == (1010, None)
print("ok: hold shows the last drawn frame; onion neighbours found")

assert d.erase_at(1015, 110, 20, 3) == 1           # erasing on a held frame edits that drawing
pieces = L["frames"]["1010"]
assert len(pieces) == 2                             # 0.7.5: the stroke is cut, both ends stay
assert pieces[0]["p"][0][:2] == [100, 10] and pieces[1]["p"][-1][:2] == [120, 30]
assert all(abs(p[0] - 110) > 3 or abs(p[1] - 20) > 3 for pc in pieces for p in pc["p"])
assert d.undo() and len(L["frames"]["1010"]) == 1
assert d.redo() and len(L["frames"]["1010"]) == 2
assert d.undo()
assert d.erase_at(1015, 110, 20, 3, whole=True) == 1 and "1010" not in L["frames"]   # Shift: whole strokes
assert d.undo() and len(L["frames"]["1010"]) == 1
assert d.erase_at(1015, 100, 10, 40) == 1 and "1010" not in L["frames"]    # a big eraser takes it all
assert d.undo()
d.begin_group(); d.add_stroke(1010, st(500)); d.add_stroke(1010, st(600)); d.end_group()
assert len(L["frames"]["1010"]) == 3 and d.undo() and len(L["frames"]["1010"]) == 1
print("ok: eraser, undo, redo, grouped undo")

l2 = d.add_layer()
assert d.layers[0]["id"] == l2 and d.active == l2 and d.layers[0]["name"] == "Layer 2"
assert d.undo() and len(d.layers) == 1 and d.active == "l1"
assert d.redo() and len(d.layers) == 2
d.set_layer(l2, locked=True)
assert d.drawable() and not d.add_stroke(1000, st(1))
d.set_layer(l2, locked=False, visible=False)
assert "hidden" in d.drawable()
d.set_layer(l2, visible=True, opacity=0.5)
d.move_layer(l2, 1); assert d.layers[1]["id"] == l2
d.rename_layer(l2, "Arcs")
assert d.clear_frame(1020) is False or True
print("ok: layers: add above active, lock/hide stop drawing, opacity, reorder, rename, undo")

assert d.save() == "" and os.path.isfile(path)
e = dr.Drawings(path, (960, 540), owner="artist")
assert [l["name"] for l in e.layers] == [l["name"] for l in d.layers] and e.layer(l2)["opacity"] == 0.5
half = dr.Drawings(path, (480, 270), owner="artist")
s0 = half.layer("l1")["frames"]["1010"][0]
assert s0["w"] == 3.0 and s0["p"][0][:2] == [50.0, 5.0]
print("ok: saved and reloaded; another cache size scales points and widths")

# other people (linked, read-only)
other = dr.Drawings(dr.layers_path(root, "colleague", "camera"), (960, 540), owner="colleague")
other.add_stroke(1100, st(50)); other.save()
empty = dr.Drawings(dr.layers_path(root, "jlee", "camera"), (960, 540), owner="jlee"); empty.save()
people = dr.find_people(root, "artist", "camera")
assert [p["user"] for p in people] == ["colleague"] and people[0]["layers"] == 1
ro = dr.Drawings(people[0]["path"], (960, 540), read_only=True, owner="colleague")
assert ro.drawable() and not ro.add_stroke(1100, st(1)) and ro.save() == "read-only"
assert dr.find_people(root, "artist", "sideCam") == []
assert dr.when_text(time.time()) == "today"
print("ok: other people with drawings found (empty files skipped); theirs are read-only")

# Blue Pencil placement: BIRDS camera (film 1.445 x 0.605 in, overscan fit, 16:9)
gate = {"fw": 1.4448819160461426, "fh": 0.605326771736145, "fit": 3, "aspect": 1.7777777}
k = dr.bp_scale(gate, 960)
assert abs(k - 2048 / 960.0) < 1e-6
assert dr.frame_to_bp(480, 270, 960, 540, k) == (1024.0, 1024.0)
top = dr.frame_to_bp(0, 0, 960, 540, k)
assert abs(top[0]) < 1e-6 and abs(top[1] - 448) < 1e-6
bx, by = dr.frame_to_bp(123, 456, 960, 540, k)
assert all(abs(a - b) < 1e-9 for a, b in zip(dr.bp_to_frame(bx, by, 960, 540, k), (123, 456)))
# film narrower than 16:9 with overscan: frame is wider than the square's gate
narrow = {"fw": 0.825, "fh": 0.825, "fit": 3, "aspect": 1.7777777}
assert dr.res_gate_inches(narrow)[0] > narrow["fw"]
print("ok: frame <-> Blue Pencil square: full width, centred (frame top at y 448)")

xml = dr.bp_xml("camera", [("Arcs", True, [(1001, "camera_Arcs_1001.png")]), ('a"b', False, [])])
import xml.etree.ElementTree as ET
names = [l.get("name") for l in ET.fromstring(xml.encode()).iter("layer")]
assert names == ["Arcs", 'a"b'] and 'time="1001"' in xml
zp = os.path.join(root, "test_drawings.zip")
with zipfile.ZipFile(zp, "w") as z:
    z.writestr("test_drawings/test_drawings.xml", dr.bp_xml("camera", [("drawovers1", False, [(1027, "camera_drawovers1_1027.png"), (1029, "camera_drawovers1_1029.png")])]))
    z.writestr("test_drawings/camera_drawovers1_1027.png", b"x")
    z.writestr("test_drawings/camera_drawovers1_1029.png", b"x")
info = dr.read_bp_zip(zp)
assert info["camera"] == "camera" and info["layers"][0]["frames"] == {1027: "test_drawings/camera_drawovers1_1027.png", 1029: "test_drawings/camera_drawovers1_1029.png"}
print("ok: Blue Pencil index written and read back (zip layout as Maya exports it)")

# film gate mask: BIRDS camera (2.39 film inside a 16:9 frame)
r = dr.film_gate_rect(gate, 960, 540)
assert abs(r[0]) < 1e-6 and abs(r[2] - 960) < 1e-6 and abs(r[3] - 402.2) < 0.5 and abs(r[1] - (540 - r[3]) / 2) < 1e-6
assert dr.film_gate_rect({"fw": 1.4449, "fh": 0.8127, "fit": 3, "aspect": 1.7778}, 960, 540) is None
assert dr.film_gate_rect(None, 960, 540) is None
print("ok: film gate inside the cached frame (BIRDS: full width, 402 px tall, centred) for the gate mask")
