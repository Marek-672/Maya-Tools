"""0.7.0: the player's drawing state (Qt stubbed): pen input mapped to the
frame, eraser, hold, linked people, rows, opacity, saving, ticks, keys."""
import os, sys, time, types, tempfile, json
from unittest import mock
TESTS = os.path.dirname(os.path.abspath(__file__))
root = tempfile.mkdtemp(); os.environ["HOME"] = os.environ["USERPROFILE"] = root
def qtmod(name):
    m = mock.MagicMock(); m.__name__ = name; return m
QtCore, QtGui, QtWidgets = qtmod("QtCore"), qtmod("QtGui"), qtmod("QtWidgets")
class Dummy(object):
    def __init__(self, *a, **k): pass
    def __getattr__(self, name): return mock.MagicMock()
for n in ("QWidget", "QFrame", "QLayout"): setattr(QtWidgets, n, Dummy)
class DummyLabel(Dummy):
    def setText(self, text): self._text = text
    def text(self): return getattr(self, "_text", "")
QtWidgets.QLabel = DummyLabel
class DummyToolButton(Dummy):
    def setChecked(self, on): self._on = bool(on)
    def isChecked(self): return getattr(self, "_on", False)
    def setCheckable(self, on): pass
    InstantPopup = 2; MenuButtonPopup = 1
QtWidgets.QToolButton = DummyToolButton
pyside = types.ModuleType("PySide2"); pyside.QtCore, pyside.QtGui, pyside.QtWidgets = QtCore, QtGui, QtWidgets
sys.modules.update({"PySide2": pyside, "PySide2.QtCore": QtCore, "PySide2.QtGui": QtGui, "PySide2.QtWidgets": QtWidgets})
sys.path.insert(0, os.path.dirname(TESTS))
from bgcache import drawui, drawing

shot_root = os.path.join(root, "jobs", "BIRDS", "sq050_0472", "maya", "bgcache")
drawing_root = drawing.drawings_root
drawing.drawings_root = lambda scene: shot_root if scene else drawing_root(scene)
drawui.drawing.drawings_root = drawing.drawings_root

class Rect:
    def __init__(s, x, y, w, h): s._x, s._y, s._w, s._h = x, y, w, h
    def x(s): return s._x
    def y(s): return s._y
    def width(s): return s._w
class Pt:
    def __init__(s, x, y): s._x, s._y = x, y
    def x(s): return s._x
    def y(s): return s._y

flashes = []
player = types.SimpleNamespace(
    cfg={"width": 960, "height": 540, "user": "artist", "original_scene": "/projects/BIRDS/sq050_0472/maya/scenes/a.mb",
         "cameras": [{"name": "|Assets|renderCam|camera", "label": "camera",
                      "gate": {"fw": 1.4449, "fh": 0.6053, "fit": 3, "aspect": 1.7778}}]},
    prefs={}, shot_ids=("BIRDS", "sq050_0472", "sq050"), live_shot="sq050_0472", view="|Assets|renderCam|camera",
    canvas=mock.MagicMock(), last_target=Rect(100, 50, 480, 270), frame=1142,
    _flash_message=lambda text, seconds=3.0: flashes.append(text), _save_prefs=lambda: None,
    update_draw_buttons=lambda: None, send_cmd=lambda *a, **k: None)
player.current_live_frame = lambda: player.frame
d = drawui.Drawer(player)
assert d.cam() == "camera" and d.mine_now().path == os.path.join(shot_root, "artist", "drawings", "camera", "layers.json")

# a stroke: canvas points map to frame pixels (picture shown at half size, offset 100,50)
assert d.press(Pt(100 + 50, 50 + 25))
d.move(Pt(100 + 100, 50 + 25)); d.move(Pt(100 + 150, 50 + 30))
d.release(Pt(100 + 150, 50 + 30))
mine = d.mine_now()
st = mine.active_layer()["frames"]["1142"][0]
assert st["p"][0][:2] == [100.0, 50.0] and st["w"] == 6.0 and st["c"] == drawing.COLORS[1]
assert os.path.isfile(mine.path)
print("ok: pen strokes land in frame pixels and are saved in the shot folder")

player.frame = 1150                          # held: erasing here edits the drawing from 1142
d.tool = "eraser"
assert d.press(Pt(100 + 50, 50 + 25), whole=True); d.release()      # Shift: whole strokes
assert "1142" not in mine.active_layer()["frames"]
d.undo(); assert "1142" in mine.active_layer()["frames"]
d.eraser_size = 8                                           # a cut at the start: the rest stays
assert d.size == 8 and d.pen_size == 6.0
assert d.press(Pt(100 + 50, 50 + 25)); d.release()
left = mine.active_layer()["frames"]["1142"]
assert len(left) == 1 and left[0]["p"][0][0] > 103, left[0]["p"][0]
d.undo()
d.tool = "pen"
assert d.size == 6.0
print("ok: eraser cuts (Shift: whole strokes) on the held drawing; undo brings it back; pen and eraser sizes separate")

mine.set_layer(mine.active, locked=True)
assert not d.press(Pt(120, 70)) and "locked" in flashes[-1]
mine.set_layer(mine.active, locked=False)
player.frame = None
assert not d.press(Pt(120, 70))
player.frame = 1142
print("ok: no drawing on locked layers or off your shot")

# another person, linked
other = drawing.Drawings(drawing.layers_path(shot_root, "colleague", "camera"), (960, 540), owner="colleague")
other.add_stroke(1200, {"c": "#e85d4a", "w": 4.0, "p": [[10, 10, 1.0], [20, 20, 1.0]]}); other.save()
assert [p["user"] for p in d.find_people()] == ["colleague"]
d.set_linked("colleague", True)
keys = [r["key"] for r in d.rows()]
assert keys == ["me", "m:l1", "P:colleague", "p:colleague:l1"], keys
assert 1200 in d.ticks() and 1142 in d.ticks()
assert d.row_value("p:colleague:l1", "locked") is True              # imports are always locked
d.set_row("p:colleague:l1", opacity=0.6)
assert d.row_value("p:colleague:l1", "opacity") == 0.6
entry = player.prefs["drawing_rows"]["sq050_0472|camera"]["people"][0]
assert entry["user"] == "colleague" and entry["view"] == {"l1": {"opacity": 0.6}}
d.set_row("p:colleague:l1", visible=False); assert 1200 not in d.ticks()
d.set_row("m:l1", opacity=0.5); assert mine.layer("l1")["opacity"] == 0.5
d.set_row("p:colleague:l1", visible=True)
row = d.person("colleague")
assert row["status"] == "current" and row["seen"].startswith(d.seen_root)
print("ok: imported person: a heading plus one locked row per layer, each with its own opacity and eye (your view only)")

# ===== 0.7.5: updates offered, not applied; Revert; kept across restarts =====
time.sleep(0.01)
other.add_stroke(1210, {"c": "#e85d4a", "w": 4.0, "p": [[1, 1, 1.0]]}); other.save()
assert d.check_updates() and d.person("colleague")["status"] == "update"
assert 1210 not in d.ticks()                                     # nothing changes until you press Update
d2 = drawui.Drawer(player)                                       # restart: still the version you accepted
assert d2.cam() == "camera" and d2.mine_now() is not None
assert d2.person("colleague")["status"] == "update" and 1210 not in d2.ticks()
d.update_person("colleague")
assert 1210 in d.ticks() and d.person("colleague")["status"] == "revert"
d.revert_person("colleague")
assert 1210 not in d.ticks() and d.person("colleague")["status"] == "update"
d.update_person("colleague")
assert 1210 in d.ticks()
print("ok: someone saves -> their heading offers Update (also after a restart); Update shows it, Revert goes back")

# Duplicate to edit
lid = d.duplicate("p:colleague:l1")
copy_layer = mine.layer(lid)
assert copy_layer["name"] == "colleague: Layer 1 (copy)" and copy_layer["source"]["user"] == "colleague"
assert mine.active == lid and "1210" in copy_layer["frames"] and not copy_layer["locked"]
theirs = drawing.Drawings(drawing.layers_path(shot_root, "colleague", "camera"), (960, 540), read_only=True)
assert [l["name"] for l in theirs.layers] == ["Layer 1"]
assert d.undo() and mine.layer(lid) is None
assert d.redo() and mine.layer(lid) is not None
print("ok: Duplicate copies their layer into yours (named after them, editable, undoable); their file untouched")

# lock blocks undo and delete
mine.set_layer(lid, locked=True)
assert not d.undo() and "locked" in flashes[-1] and mine.layer(lid) is not None
assert not mine.delete_layer(lid)
mine.set_layer(lid, locked=False)
assert mine.delete_layer(lid) and d.undo()
print("ok: a locked layer blocks undo/redo and delete")

d.remove_row("P:colleague"); assert [r["key"] for r in d.rows()][0] == "me"
assert not any(k.startswith("P:") for k in [r["key"] for r in d.rows()])
assert os.path.isfile(drawing.layers_path(shot_root, "colleague", "camera"))
assert not os.path.isfile(d._seen_path("colleague", "camera"))
print("ok: removing a person leaves their files; your snapshot of them goes")

# Blue Pencil scale for this camera
assert abs(d._bp_k() - 2048 / 960.0) < 1e-3
d.show = False; assert d.ticks() == set()
d.show = True
print("ok: Blue Pencil placement from the camera's gate; Drawings off hides ticks")

# shot folder not writable -> home folder
os.chmod(os.path.join(shot_root, "artist", "drawings", "camera"), 0o500)
mine.layers[0]["frames"]["1300"] = [{"c": "#fff", "w": 2, "p": [[0, 0, 1]]}]
d.save()
if os.name != "nt" and os.geteuid() != 0:      # Windows: chmod can't make a folder read-only
    assert mine.path.startswith(d.fallback_root) and "home folder" in flashes[-1]
    print("ok: if the shot folder can't be written, drawings go to your home folder (and it says so)")
os.chmod(os.path.join(shot_root, "artist", "drawings", "camera"), 0o755)

# keys
km = drawui.KeyMap({"actions": {"next_frame": [{"key": ".", "alt": True}], "scrub": [{"key": "k"}]}})
assert "Alt+." in km.label("next_frame") and km.label("prev_key") == ","
print("ok: key labels for the strip and tooltips")

# ===== 0.7.3: black, custom colour, orange underline =====
assert drawing.COLORS[-1] == "#000000" and drawing.COLOR_NAMES[-1] == "black"
panel = drawui.DrawPanel(d, km)
black = dict(panel.swatches)["#000000"]
black.clicked  # exists
panel.set_color("#000000")
assert d.color == "#000000" and black.isChecked() and not panel.custom_swatch.isChecked()
picks = []
with mock.patch.object(drawui, "pick_color", lambda parent, initial: picks.append(initial) or "#8844ff"):
    panel.custom_clicked()                     # no custom colour yet: opens the picker
assert picks and d.custom == "#8844ff" and d.color == "#8844ff"
assert panel.custom_swatch.isChecked() and not black.isChecked()
assert player.prefs["drawing"]["custom_color"] == "#8844ff"     # remembered
panel.set_color(drawing.COLORS[0]); picks.clear()
with mock.patch.object(drawui, "pick_color", lambda parent, initial: picks.append(initial) or "#00ff00"):
    panel.custom_clicked()                     # not current: just use it
    assert d.color == "#8844ff" and not picks
    panel.custom_clicked()                     # current: change it
assert picks == ["#8844ff"] and d.color == d.custom == "#00ff00"
with mock.patch.object(drawui, "pick_color", lambda parent, initial: None):
    panel.custom_clicked()                     # cancelled: nothing changes
assert d.color == "#00ff00"
print("ok: black swatch, custom colour (first click picks, then use / click again to change), remembered")

# ===== 0.7.4: imported rows can be selected and removed with the trash button =====
other = drawing.layers_path(d.root, "lead", d.cam())
od = drawing.Drawings(other, (960, 540), owner="lead"); od.add_stroke(1142, {"c": "#fff", "w": 4, "p": [[1, 1, 1], [5, 5, 1]]}); od.save()
d.set_linked("lead", True)
key = "p:lead:l1"
assert any(r["key"] == key for r in d.rows())
layers_before = len(d.mine_now().layers)
row = drawui.LayerRow(panel, next(r for r in d.rows() if r["key"] == key))
ev = types.SimpleNamespace(button=lambda: drawui.Qt.LeftButton)
row.mousePressEvent(ev)
assert d.selected == key
panel.delete_layer()                      # trash: removes the import, not your layer
assert not any(r["key"] == key for r in d.rows()) and d.selected is None
assert len(d.mine_now().layers) == layers_before and os.path.isfile(other)   # their file untouched
d.set_linked("lead", True); d.selected = key
d.press(Pt(100 + 60, 50 + 25)); d.release(Pt(100 + 60, 50 + 25))
assert d.selected is None                 # drawing goes back to your own layer
print("ok: imported rows: click selects, trash removes from your list (files untouched); drawing reselects your layer")

# ===== 0.7.5: headings, Import menu, other camera =====
heads = [r for r in d.rows() if r["kind"] in ("me", "head")]
assert heads[0]["kind"] == "me" and any(h["key"] == "P:lead" for h in heads)
w = drawui.HeadRow(panel, heads[0]); w2 = drawui.HeadRow(panel, next(h for h in heads if h["key"] == "P:lead"))
panel.refresh()                                     # builds heading and layer rows without errors
dup_rows = [r for r in d.rows() if r["kind"] == "person"]
assert dup_rows and drawui.LayerRow(panel, dup_rows[0])
# another camera with drawings: noise_camera
noise = drawing.Drawings(drawing.layers_path(d.root, "mlopez", "noise_camera"), (960, 540), owner="mlopez")
noise.add_stroke(1001, {"c": "#fff", "w": 4, "p": [[1, 1, 1], [9, 9, 1]]}); noise.save()
assert "noise_camera" in drawing.drawn_cameras(d.root)
player.cfg["cameras"].append({"name": "|Assets|renderCam|noise_camera", "label": "noise_camera"})
assert panel._camera_named("noise_camera") == "|Assets|renderCam|noise_camera"
player.checked, player.start, player.end = ["|Assets|renderCam|camera"], 1001, 1010
player.loaded, player.dirty = {}, {}
assert panel._camera_state("|Assets|renderCam|noise_camera") == ""          # not cached: offer Cache
checked = []
player._set_checked = lambda cam, on: (checked.append(cam), player.checked.append(cam))
player._label = lambda cam: cam.split("|")[-1]
panel.cache_camera("|Assets|renderCam|noise_camera")
assert checked == ["|Assets|renderCam|noise_camera"] and player.view != "|Assets|renderCam|noise_camera"
player.loaded = {"|Assets|renderCam|noise_camera": {f: 1 for f in range(1001, 1006)}}
player.dirty = {"|Assets|renderCam|noise_camera": set(range(1006, 1011))}
assert panel._camera_state("|Assets|renderCam|noise_camera") == "caching 50%"
player.loaded = {"|Assets|renderCam|noise_camera": {f: 1 for f in range(1001, 1011)}}
player.dirty = {"|Assets|renderCam|noise_camera": set()}
assert panel._camera_state("|Assets|renderCam|noise_camera") == "loaded"
d.set_linked("mlopez", True, "noise_camera")          # tick them before switching
assert d.is_linked("mlopez", "noise_camera") and not d.is_linked("mlopez")
time.sleep(0.01); noise.add_stroke(1002, {"c": "#fff", "w": 4, "p": [[1, 1, 1]]}); noise.save()
d.check_updates()
assert d.person("mlopez", "noise_camera")["status"] == "update"
panel.fill_import_menu()                                # builds with both cameras without errors
print("ok: Import lists the other camera: Cache -> caching % -> loaded, ticks work before switching, update shown")

# permissions follow the folder; backups once per sitting
mode = os.stat(os.path.dirname(mine.path)).st_mode & 0o777
assert os.stat(mine.path).st_mode & 0o777 == mode & 0o666
n0 = len(os.listdir(mine.history_dir())) if os.path.isdir(mine.history_dir()) else 0
mine.last_backup = 0; mine.save()
hist = sorted(os.listdir(mine.history_dir()))
assert len(hist) == n0 + 1 and hist[-1].startswith("layers_")
mine.save(); assert len(os.listdir(mine.history_dir())) == n0 + 1      # same sitting: no new backup
r0 = mine.rev; mine.save(); assert mine.rev == r0 + 1 and drawing.file_rev(mine.path)[0] == mine.rev
print("ok: saved files get the folder's permissions; one backup per sitting in history/; rev counts saves")

# ===== 0.8.0b5: Paper: the movie fades to white under the drawings =====
painter = mock.MagicMock(); QtGui.QColor.reset_mock()
d.on, d.paper = False, 0.6
d.paint_paper(painter, "rect")
assert not painter.fillRect.called                      # only in Draw mode
d.on = True
d.paint_paper(painter, "rect")
painter.fillRect.assert_called_once()
QtGui.QColor.assert_called_with(255, 255, 255, 153)     # 60 % white over the picture
d.paper = 0.0; painter.reset_mock()
d.paint_paper(painter, "rect")
assert not painter.fillRect.called                      # 0 = the movie as it is
d.paper = 0.35
d.on = False; d.on = True                                # Draw off and on again: Paper stays
painter.reset_mock(); d.paint_paper(painter, "rect")
QtGui.QColor.assert_called_with(255, 255, 255, 89)
d.save_prefs()
assert "paper" not in player.prefs["drawing"]          # never saved
player.prefs["drawing"]["paper"] = 0.8                  # even an old saved value is ignored
d2 = drawui.Drawer(player)
assert d2.paper == 0.0                                   # a new Start begins at 0
d.on = False
print("ok: Paper fades the picture to white (0-100 %) under the drawings, in Draw mode only; kept while Draw toggles, back to 0 at the next Start")
