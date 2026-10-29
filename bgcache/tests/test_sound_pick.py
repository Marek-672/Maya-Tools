"""0.8.0b8: a shot with several sound tracks (full mix + stems) and none
picked on the time slider plays the profile's preferred track (studio: _ax_)
instead of nothing; muted tracks are skipped; a picked track still wins."""
import os, sys, types, tempfile
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
exec(open(os.path.join(TESTS, "test_sync.py")).read().split("sys.path.insert")[0])   # Maya/Qt stubs + temp root
sys.path.insert(0, REPO)
os.environ.setdefault("BGCACHE_PROFILE", os.path.join(TESTS, "fixtures", "studio_profile.json"))
from unittest import mock
from bgcache import controller, profile

wav = os.path.join(tempfile.mkdtemp(), "AUD_sq080_0100_ax_v007.wav")
open(wav, "wb").write(b"RIFF")
stems = ["AUD_sq080_0100_ax_v007", "AUD_sq080_0100_dx_v007", "AUD_sq080_0100_mx_v007",
         "AUD_sq080_0100_sfx_v007", "AUD_sq080_0100_sfxdx_v007"]
attrs = {n + ".filename": wav for n in stems}
muted = set()
def getAttr(plug):
    if plug.endswith(".mute"):
        return plug.split(".")[0] in muted
    return attrs.get(plug, 0.0)
cmds.getAttr = getAttr
cmds.ls = lambda *a, **k: list(stems) if k.get("type") == "audio" else []
slider = {"sound": ""}
cmds.timeControl = lambda *a, **k: slider["sound"]
mel.eval = lambda s: "timeControl1"

# studio profile (fixture): prefers _ax_
assert profile.get("sound_preference") == ["_ax_"], profile.get("sound_preference")
info = controller.find_audio()
assert info and info["node"] == "AUD_sq080_0100_ax_v007", info
print("ok: five tracks, none on the time slider: plays the ax full mix (studio profile)")

muted.add("AUD_sq080_0100_ax_v007")
assert controller.find_audio()["node"] == "AUD_sq080_0100_dx_v007"
print("ok: ax muted: the first unmuted track instead")
muted.clear()

slider["sound"] = "AUD_sq080_0100_mx_v007"
assert controller.find_audio()["node"] == "AUD_sq080_0100_mx_v007"
print("ok: a track picked on the time slider still wins")
slider["sound"] = ""

with mock.patch.object(profile, "get", lambda name: [] if name == "sound_preference" else profile.DEFAULT.get(name)):
    assert controller.pick_sound_node(stems) == stems[0]
    assert controller.pick_sound_node(stems, lambda n: True) is None
print("ok: generic profile: the first unmuted track; all muted: none")

src = open(os.path.join(REPO, "bgcache", "player.py")).read()
assert '"sound on, except your shot (%s)"' in src
print("ok: the player says when your shot is silent while neighbours play")
