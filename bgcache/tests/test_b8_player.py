"""0.9.0b8 player: your Maya's range as the focus (Sync), Match Maya, the
cut marked, never-rendered frames hatched (stand-in Qt)."""
import os, sys, json, time
TESTS = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(TESTS, "test_player.py")).read()
exec(src.split("assert P.shot_ids")[0])            # a Player P on a 1001-1340 shot, stand-in Qt
P.canvas = mock.MagicMock(); P.canvas.width.return_value = 1000; P.canvas.height.return_value = 300
P.status_label = mock.MagicMock()
P.b_match = mock.MagicMock()
P.cfg["cut"] = [1011, 1330]

# Sync on: Maya's range is the focus
P._set_sync(True)
common.write_json_atomic(P.p["maya_range"], {"range": [1100, 1200], "ts": time.time()})
P._follow_maya_range()
assert P.focus_range == (1100, 1200) and json.load(open(P.p["cameras"]))["focus"] == [1100, 1200]
assert json.load(open(P.p["cameras"]))["focus_from"] == "maya"
print("ok: Sync on: your Maya's playback range 1100-1200 becomes the focus (and goes to the background Maya)")
common.write_json_atomic(P.p["maya_range"], {"range": [1001, 1340], "ts": time.time() + 1})
P._follow_maya_range()
assert P.focus_range is None
print("ok: your Maya's range opened to the whole shot: no focus")

# Sync off: separate, a note once, Match Maya shown while they differ
P._set_sync(False)
P._flash_until = 0
common.write_json_atomic(P.p["maya_range"], {"range": [1150, 1180], "ts": time.time() + 2})
P._follow_maya_range()
assert P.focus_range is None and P.maya_range == (1150, 1180)
assert "Sync is off" in P._flash and P._flash_until > time.time()
assert P.b_match.setVisible.call_args[0][0] is True
first_note = P._flash_until
common.write_json_atomic(P.p["maya_range"], {"range": [1150, 1190], "ts": time.time() + 3})
P._follow_maya_range()
assert P._flash_until == first_note
print("ok: Sync off: the focus stays; the note shows once; Match Maya is on the playback bar")
P.match_maya_range()
assert P.focus_range == (1150, 1190) and P.b_match.setVisible.call_args[0][0] is False
print("ok: Match Maya makes the focus your Maya's range, and the button goes")
common.write_json_atomic(P.p["maya_range"], {"range": [1200, 1250], "ts": time.time() + 4})
P._follow_maya_range()
P._set_sync(True)
assert P.focus_range == (1200, 1250)
print("ok: turning Sync back on: the player matches your Maya")

# the bar: hatched (never rendered), red (out of date), green; purple outside the cut; the blue range
P.view = "|shotCam"; P.data["|shotCam"] = {f: b"x" for f in range(1001, 1101)}
P.dirty["|shotCam"] = set(range(1050, 1150))
painter = mock.MagicMock()
class Bar(object):
    def x(self): return 0
    def y(self): return 288
    def width(self): return 1000
    def height(self): return 12
    def bottom(self): return 299
    def right(self): return 999
fills = []
painter.fillRect.side_effect = lambda rect, color: fills.append(color)
P._paint_live_frames(painter, Bar(), 0, 340, P.data["|shotCam"], P.dirty["|shotCam"], 291)
assert len(fills) == 340 + 20, len(fills)          # a cell per frame, a stripe under each frame outside the cut
print("ok: bar: green rendered, red out of date, hatched never rendered; purple under the 20 frames outside the cut")
P.sync = False; P.maya_range = (1300, 1330)
pl.QtGui.QFontMetrics = lambda font: types.SimpleNamespace(horizontalAdvance=lambda t: 60, height=lambda: 14)
P._paint_maya_range(painter, Bar())
assert len(fills) == 360 + 3 + 1 and painter.drawText.called    # line, two ends, the label's box
print("ok: your Maya's range is drawn on the bar (labelled while Sync is off and it differs)")
assert P._outside_cut(1005) and not P._outside_cut(1100)
texts = P._range_texts()
assert texts[-1] == "1011 – 1330 (+20 outside the cut)", texts
print("ok: the range text gives the cut and the frames outside it; OUTSIDE THE CUT on those frames")

# a camera already picked when the player opens (as at the studio): the
# drawing strip asks where you draw before the reel exists (b8 crashed here)
common.write_json_atomic(P.p["cameras"], {"checked": ["|shotCam"], "view": "|shotCam"})
with mock.patch.object(pl.Player, "_poll", lambda self: None):
    P4 = pl.Player(session)
assert P4.view == "|shotCam" and P4.segments and P4.drawer.place()["key"] == "shotCam"
print("ok: the player opens with a camera already picked (the strip asks before the reel exists)")
