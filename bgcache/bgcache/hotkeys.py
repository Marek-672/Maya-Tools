"""Your Maya hotkeys, so the player's keys match Maya's.

read_maya_hotkeys() runs in your Maya at Start: it asks the current hotkey set
which key runs each playback command (step a frame, jump to a key, play, go to
start/end, timeline scrub) and returns them for the player, falling back to
Maya's defaults for anything not found. The player turns them into Qt keys
with KeyMap (no Maya needed there).
"""

# action -> words that identify Maya's command for it (matched against the
# hotkey's name command, case-insensitive, first match wins)
ACTIONS = [
    ("scrub", ("timedraggertool", "timedragger")),
    ("prev_frame", ("previousframe", "prevframe", "stepbackward")),
    ("next_frame", ("nextframe", "stepforward")),
    ("prev_key", ("previouskey", "prevkey")),
    ("next_key", ("nextkey",)),
    ("play", ("playbacktoggle", "playtoggle", "playbackforward", "playforward")),
    ("start", ("gotominframe", "minframe", "playbackrangestart", "gotostart")),
    ("end", ("gotomaxframe", "maxframe", "playbackrangeend", "gotoend")),
]

# Maya's defaults, used for anything the hotkey set doesn't show
DEFAULTS = {
    "prev_frame": [{"key": ",", "alt": True}],
    "next_frame": [{"key": ".", "alt": True}],
    "prev_key": [{"key": ","}],
    "next_key": [{"key": "."}],
    "play": [{"key": "v", "alt": True}],
    "start": [{"key": "v", "alt": True, "shift": True}],
    "end": [],
    "scrub": [{"key": "k"}],
}

LETTERS = "abcdefghijklmnopqrstuvwxyz"
KEYS = (list(LETTERS) + list("0123456789") + list(",./;'[]\\-=`")
        + ["Left", "Right", "Up", "Down", "Home", "End", "Page_Up", "Page_Down"]
        + ["F%d" % i for i in range(1, 13)])


def classify(name):
    """Which player action a Maya name command is, or None."""
    low = (name or "").lower().replace("_", "").replace(" ", "")
    for action, words in ACTIONS:
        if any(w in low for w in words):
            return action
    return None


def spec_text(spec):
    """'Alt+,' style label for a key spec."""
    parts = []
    if spec.get("ctrl"):
        parts.append("Ctrl")
    if spec.get("alt"):
        parts.append("Alt")
    if spec.get("shift"):
        parts.append("Shift")
    key = spec.get("key", "")
    parts.append(key.upper() if len(key) == 1 and key.isalpha() else key.replace("_", " "))
    return "+".join(parts)


def read_maya_hotkeys(cmds=None):
    """{"actions": {action: [spec]}, "source": {action: "maya"|"default"}}.
    A spec is {"key", "alt", "ctrl", "shift"}. Never raises."""
    if cmds is None:
        import maya.cmds as cmds
    found = {action: [] for action, _ in ACTIONS}
    for key in KEYS:
        for alt in (False, True):
            for ctrl in (False, True):
                for shift in (False, True):
                    letter = len(key) == 1 and key.isalpha()
                    kwargs = {"keyShortcut": key.upper() if (shift and letter) else key,
                              "altModifier": alt, "ctrlModifier": ctrl,
                              "query": True, "name": True}
                    if shift and not letter:
                        kwargs["shiftModifier"] = True
                    try:
                        name = cmds.hotkey(**kwargs)
                    except Exception:  # no hotkey on this combination in this Maya
                        continue
                    action = classify(name)
                    if action:
                        found[action].append({"key": key, "alt": alt, "ctrl": ctrl, "shift": shift})
    source = {}
    for action, _ in ACTIONS:
        if found[action]:
            source[action] = "maya"
        else:
            found[action] = [dict(s) for s in DEFAULTS.get(action, [])]
            source[action] = "default"
    return {"actions": found, "source": source}
