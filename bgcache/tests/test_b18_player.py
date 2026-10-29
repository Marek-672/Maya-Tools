"""0.8.0b18 player: the focus range code runs (stand-in Qt)."""
import os, sys, json
TESTS = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(TESTS, "test_player.py")).read()
exec(src.split("assert P.shot_ids")[0])            # a Player P on a 1001-1340 shot, stand-in Qt
P.canvas = mock.MagicMock(); P.canvas.width.return_value = 1000; P.canvas.height.return_value = 300
P.status_label = mock.MagicMock()
P.set_focus(1100, 1150)
assert P.focus_range == (1100, 1150)
assert json.load(open(P.p["cameras"]))["focus"] == [1100, 1150]
P.set_focus(last=1050)                              # past the start: the ends swap
assert P.focus_range == (1050, 1100)
P.set_focus(first=1001, last=1340)                  # the whole shot = no focus
assert P.focus_range is None and json.load(open(P.p["cameras"]))["focus"] is None
print("ok: set_focus: start/end, swapped if crossed, the whole shot means no focus; written for the background Maya")
P.view = "|shotCam"; P.dirty["|shotCam"] = set(range(1001, 1341))
P.set_focus(1100, 1109)
assert P._dirty_in_focus() == set(range(1100, 1110))
P.state = "rendering"; P._update_status()
text = P.status_label.setText.call_args[0][0]
assert "focus 1100-1109 · 330 frames waiting outside" in text, text
print("ok: status: focus 1100-1109 · 330 frames waiting outside; health checks count only frames in focus")
painter = mock.MagicMock()
class Bar(object):
    def x(self): return 0
    def y(self): return 288
    def width(self): return 1000
    def height(self): return 12
    def bottom(self): return 299
P._paint_focus(painter, Bar())
assert painter.fillRect.called
print("ok: the cache bar draws the focus handles and dims outside")
P.pos = 50; P._focus_key("in")
assert P.focus_range[0] == 1051
P.set_focus(clear=True)
assert P.focus_range is None
print("ok: I at frame 1051 moves the start there; Clear focus range caches the whole shot again")

# ---- b19: a handle drag writes the range once, when you let go
before = open(P.p["cameras"]).read()
P._handle_drag = "in"
ev = mock.MagicMock()
P._frame_at = lambda canvas, event: 1200
P.canvas_move(P.canvas, ev)
assert P.focus_range[0] == 1200 and open(P.p["cameras"]).read() == before
P.canvas_release(P.canvas, ev)
assert json.load(open(P.p["cameras"]))["focus"][0] == 1200
print("ok: b19: dragging a handle updates the bar; the range is sent once, when you let go")
