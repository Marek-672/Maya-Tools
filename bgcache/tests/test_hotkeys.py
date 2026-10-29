"""0.7.0: the player follows your Maya hotkeys."""
import os, sys, types
from unittest import mock
TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(TESTS))
from bgcache import hotkeys as hk

# a fake Maya hotkey set: default playback keys plus a remap of next frame to Ctrl+Right
bound = {(".", True, False, False): "NextFrameNameCommand", (",", True, False, False): "PreviousFrameNameCommand",
         (".", False, False, False): "NextKeyNameCommand", (",", False, False, False): "PreviousKeyNameCommand",
         ("v", True, False, False): "PlaybackToggleNameCommand", ("k", False, False, False): "TimeDraggerToolActivateNameCommand",
         ("Right", False, True, False): "NameComNext_Frame", ("s", False, False, False): "SetKeyNameCommand"}
def hotkey(keyShortcut, altModifier, ctrlModifier, query, name, shiftModifier=False):
    key = keyShortcut.lower() if len(keyShortcut) == 1 else keyShortcut
    shift = shiftModifier or (len(keyShortcut) == 1 and keyShortcut.isupper())
    return bound.get((key, altModifier, ctrlModifier, shift))
cmds = types.SimpleNamespace(hotkey=hotkey)
keys = hk.read_maya_hotkeys(cmds)
a = keys["actions"]
assert {"key": ".", "alt": True, "ctrl": False, "shift": False} in a["next_frame"]
assert {"key": "Right", "alt": False, "ctrl": True, "shift": False} in a["next_frame"]
assert a["next_key"] == [{"key": ".", "alt": False, "ctrl": False, "shift": False}]
assert a["scrub"][0]["key"] == "k" and keys["source"]["scrub"] == "maya"
assert keys["source"]["end"] == "default" and keys["source"]["start"] == "default"
assert hk.classify("SetKeyNameCommand") is None
assert hk.spec_text({"key": ",", "alt": True}) == "Alt+," and hk.spec_text({"key": "v", "alt": True, "shift": True}) == "Alt+Shift+V"
print("ok: playback keys read from the hotkey set (remaps found, defaults for the rest):",
      ", ".join("%s=%s" % (k, "/".join(hk.spec_text(s) for s in v)) for k, v in sorted(a.items())))
cmds_broken = types.SimpleNamespace(hotkey=lambda **k: 1 / 0)
assert hk.read_maya_hotkeys(cmds_broken)["source"]["play"] == "default"
print("ok: if Maya can't be asked, Maya's default keys are used")
