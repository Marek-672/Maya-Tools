"""bgcache torture test: run a build through what users do, and do by accident,
in a real Maya, start to finish, and write down what happened.

Run it in an interactive Maya that is on an EMPTY, UNSAVED scene (it refuses
otherwise: it never touches a saved scene), from the Script Editor's Python tab:

    TORTURE_DIR = r"C:\\temp\\bgcache_torture"            # where the report goes (made if missing)
    BUILD = r"C:\\temp\\bgcache-windows-full.zip"         # optional: a download to test
    exec(open(r"C:\\temp\\maya_torture.py").read())

Without BUILD it tests the bgcache that's installed in this Maya.
It runs in a background thread, so Maya stays usable (don't use it meanwhile:
the test selects, keys, hides and deletes things in its own throwaway scene).
Results: TORTURE_DIR/torture_report.json and torture_report.txt.
Takes about ten minutes. At the end Maya is back on an empty scene, the
build's code is unloaded, and only your Maya is left running.

Each scenario is one thing a user might do. It PASSES when bgcache did the
right thing; FAILS when it didn't, or when anything wrote a Python error
(the Script Editor's history and the background Maya's log are both read
after every scenario). OBSERVED scenarios have no right answer yet: what
happened is written down for a person to judge.
"""
import ctypes
import glob
import json
import os
import random
import shutil
import subprocess
import sys
import threading
import time
import traceback
import zipfile

import maya.cmds as cmds
import maya.utils

import tempfile
HERE = globals().get("TORTURE_DIR") or os.path.join(tempfile.gettempdir(), "bgcache_torture")
os.makedirs(HERE, exist_ok=True)
BUILD = globals().get("BUILD")                  # None: test the installed bgcache
ONLY = globals().get("ONLY")                    # a list of scenario names, to run just those
ROOT = os.path.join(HERE, "bgcache_under_test")
REPORT = os.path.join(HERE, "torture_report.json")
TEXT = os.path.join(HERE, "torture_report.txt")
HISTORY = os.path.join(HERE, "torture_script_editor.log")
CAM, CAM_B = "|shotCam", "|camB"
FIRST, LAST = 1001, 1024

report = {"started": time.time(), "build": BUILD, "results": []}
SCENARIOS = []


def scenario(fresh=False, observed=False):
    """fresh: stop bgcache first and let the scenario start it itself."""
    def wrap(fn):
        SCENARIOS.append((fn.__name__, fn, fresh, observed))
        return fn
    return wrap


def main(fn):
    return maya.utils.executeInMainThreadWithResult(fn)


def save():
    with open(REPORT, "w") as handle:
        json.dump(report, handle, indent=1, default=str)


# ------------------------------------------------------------------ bgcache
def controller():
    import bgcache.controller as c
    return c


def k():
    return controller().get()


def paths():
    import bgcache.common as common
    return common.paths(k().session)


def read(name):
    import bgcache.common as common
    try:
        return common.read_json(paths()[name]) or {}
    except Exception:
        return {}


def status():
    return read("status")


def dirty():
    return sum(len(c.get("dirty") or []) for c in (status().get("cameras") or {}).values())


def versions(cam=CAM):
    return dict(((status().get("cameras") or {}).get(cam) or {}).get("versions") or {})


def worker_alive():
    proc = getattr(k(), "worker_proc", None)
    return bool(proc) and proc.poll() is None


def player_alive():
    proc = getattr(k(), "player_proc", None)
    return bool(proc) and proc.poll() is None


def log_lines():
    try:
        return open(paths()["log"], errors="replace").read().splitlines()
    except Exception:
        return []


def wait(test, seconds, every=0.3):
    t0 = time.time()
    while time.time() - t0 < seconds:
        try:
            if test():
                return round(time.time() - t0, 1)
        except Exception:
            pass
        time.sleep(every)
    return None


def wait_ready(seconds=180):
    took = wait(lambda: status().get("state", "").startswith("ready") or status().get("state") == "rendering", seconds)
    assert took is not None, "not ready after %ds: state %r" % (seconds, status().get("state"))
    return took


def wait_clean(seconds=90, cams=(CAM,)):
    def clean():
        st = status()
        have = st.get("cameras") or {}
        return st.get("state") == "ready" and all(c in have and not have[c].get("dirty") for c in cams)
    took = wait(clean, seconds)
    assert took is not None, "frames still out of date after %ds: state %r, %d dirty" % (
        seconds, status().get("state"), dirty())
    return took


def wait_log(text, seconds, after):
    return wait(lambda: any(text in l for l in log_lines()[after:]), seconds)


def redone(action, frame, seconds=40):
    """Do it, and wait for that frame to be rendered again and everything to settle."""
    before = versions().get(str(frame))
    main(action)
    assert wait(lambda: versions().get(str(frame)) != before, seconds) is not None, \
        "frame %s was not re-rendered within %ds" % (frame, seconds)
    return wait_clean(120)


def start(wait_for_clean=True):
    main(controller().shelf_click)
    wait(lambda: getattr(k(), "worker_proc", None) is not None and k().running, 20)
    assert k().running, "Start did not start"
    took = wait_ready()
    if wait_for_clean and (status().get("cameras") or {}):
        wait_clean(120)
    return took


def stop(seconds=25):
    proc = getattr(k(), "worker_proc", None)
    player = getattr(k(), "player_proc", None)
    if k().running:
        main(controller().shelf_stop)
    assert wait(lambda: not k().running, 10) is not None, "Stop did not stop"
    for name, p in (("background Maya", proc), ("player", player)):
        if p is not None:
            assert wait(lambda: p.poll() is not None, seconds) is not None, "%s still running %ds after Stop" % (name, seconds)


def pick_cameras(checked, view=None):
    """What the player's camera menu writes."""
    import bgcache.common as common
    cur = read("cameras")
    cur.update({"checked": list(checked), "view": view or (checked[0] if checked else None)})
    common.write_json_atomic(paths()["cameras"], cur)


# ------------------------------------------------------------------ the scene
def build_scene(cameras=True, first=FIRST, last=LAST):
    cmds.file(new=True, force=True)
    cmds.playbackOptions(minTime=first, maxTime=last, animationStartTime=first, animationEndTime=last)
    cmds.currentTime(first)
    cube = cmds.polyCube(name="hero", w=4, h=4, d=4)[0]
    cmds.setKeyframe(cube, at="translateX", t=first, v=-8)
    cmds.setKeyframe(cube, at="translateX", t=last, v=8)
    cmds.polySphere(name="prop", r=2)
    cmds.setAttr("prop.translate", 6, 4, 0)
    if cameras:
        for name, pos in (("shotCam", (0, 3, 40)), ("camB", (25, 10, 35))):
            cam = cmds.rename(cmds.camera(name=name)[0], name)
            cmds.setAttr(cam + ".translate", *pos)
        cmds.setAttr("camB.rotateY", 35)
        panel = [p for p in cmds.getPanel(visiblePanels=True) if cmds.getPanel(typeOf=p) == "modelPanel"][0]
        cmds.lookThru(panel, "shotCam")
    cmds.select(clear=True)


def model_panel():
    return [p for p in cmds.getPanel(visiblePanels=True) if cmds.getPanel(typeOf=p) == "modelPanel"][0]


# ------------------------------------------------------------------ scenarios
@scenario(fresh=True)
def start_on_an_unsaved_scene():
    main(build_scene)
    took = start()
    frames = glob.glob(os.path.join(__import__("bgcache.common", fromlist=["x"]).frames_dir(k().session, CAM), "f.*.jpg"))
    assert len(frames) == LAST - FIRST + 1, "%d frames cached, expected %d" % (len(frames), LAST - FIRST + 1)
    assert player_alive() and worker_alive()
    return "ready in %ss, %d frames" % (took, len(frames))


@scenario()
def press_the_shelf_button_again_while_running():
    session, pid = k().session, k().worker_proc.pid
    main(controller().shelf_click)
    time.sleep(2)
    assert k().session == session and k().worker_proc.pid == pid, "a second session was started"
    return "same session, same background Maya"


@scenario()
def move_a_key():
    before = versions().get("1012")
    main(lambda: cmds.setKeyframe("hero", at="translateY", t=1012, v=6))
    assert wait(lambda: versions().get("1012") != before, 30) is not None, "frame 1012 was not re-rendered"
    return "re-rendered, clean again in %ss" % wait_clean()


@scenario()
def forty_key_edits_in_a_row():
    def edits():
        for i in range(40):
            cmds.setKeyframe("hero", at="translateY", t=1001 + (i * 7) % 24, v=random.uniform(-3, 8))
    return "re-rendered, clean again in %ss" % redone(edits, 1001)


@scenario()
def undo_and_redo():
    def go():
        for _ in range(5):
            cmds.undo()
        for _ in range(3):
            cmds.redo()
    return "re-rendered, clean again in %ss" % redone(go, 1010)


@scenario()
def delete_all_keys_of_a_channel():
    return "re-rendered, clean again in %ss" % redone(lambda: cmds.cutKey("hero", attribute="translateY", clear=True), 1001)


@scenario()
def scrub_the_timeline_fast():
    def go():
        for i in range(80):
            cmds.currentTime(FIRST + (i * 5) % (LAST - FIRST + 1))
    main(go)
    time.sleep(1)
    assert worker_alive() and player_alive()
    return "clean in %ss" % wait_clean(60)


@scenario()
def change_a_value_without_a_key_then_refresh():
    main(lambda: cmds.select("hero"))
    time.sleep(0.8)
    main(lambda: cmds.setAttr("hero.scaleZ", 3.0))
    main(lambda: cmds.select(clear=True))
    n = len(log_lines())
    said = []
    tell = k()._tell_player
    k()._tell_player = lambda text: (said.append(text), tell(text))
    try:
        main(k().refresh_display)
    finally:
        k()._tell_player = tell
    assert wait_log("message statics", 10, n) is not None, "Refresh sent nothing; it said %r" % said
    wait_clean()
    return said[-1] if said else "sent"


@scenario()
def refresh_eight_times_in_a_row():
    def go():
        for _ in range(8):
            k().refresh_display()
    main(go)
    time.sleep(1)
    return "clean in %ss" % wait_clean(60)


@scenario()
def refresh_with_nothing_changed_sends_nothing():
    n = len(log_lines())
    main(k().refresh_display)
    time.sleep(2.5)
    assert not any("message statics" in l for l in log_lines()[n:]), "Refresh re-rendered though nothing changed"
    return "nothing sent"


@scenario()
def change_the_viewport_then_refresh():
    n = len(log_lines())
    main(lambda: cmds.modelEditor(model_panel(), edit=True, wireframeOnShaded=True))
    main(k().refresh_display)
    assert wait_log("viewport settings refreshed", 10, n) is not None, "the viewport change did not arrive"
    main(lambda: cmds.modelEditor(model_panel(), edit=True, wireframeOnShaded=False))
    main(k().refresh_display)
    return "clean in %ss" % wait_clean(60)


@scenario()
def hide_and_show_an_object_then_refresh():
    for on in (False, True):
        n = len(log_lines())
        main(lambda: cmds.setAttr("prop.visibility", on))
        main(k().refresh_display)
        assert wait_log("message statics", 10, n) is not None, "hiding/showing did not arrive (visible=%s)" % on
    return "clean in %ss" % wait_clean(60)


@scenario()
def shrink_and_grow_the_playback_range():
    main(lambda: cmds.playbackOptions(minTime=1006, maxTime=1015))
    time.sleep(1.5)
    main(lambda: cmds.playbackOptions(minTime=FIRST, maxTime=LAST))
    time.sleep(1.5)
    main(lambda: cmds.playbackOptions(maxTime=LAST + 8, animationEndTime=LAST + 8))      # past the shot
    time.sleep(3)
    grown = status().get("end")
    main(lambda: cmds.playbackOptions(maxTime=LAST, animationEndTime=LAST))
    time.sleep(3)
    wait_clean(90)
    return "shot end went to %s and back to %s" % (grown, status().get("end"))


@scenario()
def pause_edit_resume():
    main(lambda: k().toggle_pause(True))
    time.sleep(1)
    main(lambda: cmds.setKeyframe("hero", at="rotateY", t=1008, v=45))
    time.sleep(4)
    held = dirty()
    main(lambda: k().toggle_pause(False))
    took = wait_clean(90)
    assert held > 0, "frames were re-rendered while paused"
    return "%d frames waited while paused; clean %ss after resume" % (held, took)


@scenario()
def re_render_all():
    before = versions().get("1001")
    main(k().rerender_all)
    assert wait(lambda: versions().get("1001") != before, 30) is not None, "frame 1001 was not redone"
    return "clean in %ss" % wait_clean(90)


@scenario()
def tick_a_second_camera_in_the_player():
    pick_cameras([CAM, CAM_B], CAM)
    took = wait_clean(120, cams=(CAM, CAM_B))
    import bgcache.common as common
    frames = glob.glob(os.path.join(common.frames_dir(k().session, CAM_B), "f.*.jpg"))
    assert len(frames) == LAST - FIRST + 1, "camB has %d frames" % len(frames)
    return "both cameras cached in %ss" % took


@scenario()
def move_a_cached_camera_without_keys():
    n = len(log_lines())
    main(lambda: cmds.setAttr("camB.translateY", 14))
    assert wait_log("message statics", 10, n) is not None, "the camera move was not sent"
    return "sent by itself; clean in %ss" % wait_clean(90, cams=(CAM, CAM_B))


@scenario(observed=True)
def rename_a_cached_camera():
    main(lambda: cmds.rename("camB", "camB_renamed"))
    time.sleep(3)
    main(k().refresh_display)
    time.sleep(3)
    out = "state %r; background Maya %s; note %r; question %r" % (
        status().get("state"), "alive" if worker_alive() else "DEAD", read("refresh_note").get("note"),
        (read("refresh_note").get("ask") or {}).get("changes"))
    main(lambda: cmds.rename("camB_renamed", "camB"))
    assert worker_alive() and player_alive()
    return out


@scenario(observed=True)
def delete_a_cached_camera():
    main(lambda: cmds.delete("camB"))
    time.sleep(3)
    main(k().refresh_display)
    time.sleep(3)
    ask = (read("refresh_note").get("ask") or {}).get("changes")
    assert worker_alive() and player_alive(), "something died after deleting a cached camera"
    pick_cameras([CAM], CAM)
    return "state %r; Refresh asked about: %r" % (status().get("state"), ask)


@scenario()
def add_a_reference_refresh_asks_then_reload():
    ref = os.path.join(HERE, "torture_ref.ma").replace("\\", "/")
    def make():
        ball = cmds.polyTorus(name="refThing", r=3)[0]
        cmds.select(ball)
        cmds.file(ref, force=True, type="mayaAscii", exportSelected=True)
        cmds.delete(ball)
        cmds.file(ref, reference=True, namespace="extra")
        cmds.select(clear=True)
    main(make)
    assert wait(lambda: "reference" in (read("refresh_note").get("note") or ""), 8) is not None, \
        "no note next to Refresh after adding a reference: %r" % read("refresh_note")
    main(k().refresh_display)
    assert wait(lambda: (read("refresh_note").get("ask") or {}).get("changes"), 8) is not None, "Refresh did not ask to reload"
    asked = read("refresh_note")["ask"]["changes"]
    n = len(log_lines())
    main(k().reload_scene)
    assert wait_log("scene reloaded", 90, n) is not None, "the reload did not finish"
    wait_clean(120)
    assert not read("refresh_note").get("note") and not read("refresh_note").get("ask"), "the note stayed after the reload"
    return "asked about %s; reloaded; note cleared" % ", ".join(asked)


@scenario()
def reload_scene_twice_at_once():
    n = len(log_lines())
    main(lambda: (k().reload_scene(), k().reload_scene()))
    assert wait_log("scene reloaded", 120, n) is not None, "no reload finished"
    time.sleep(3)
    took = wait_clean(150)
    assert worker_alive()
    return "%d reloads done; clean in %ss" % (sum("scene reloaded" in l for l in log_lines()[n:]), took)


@scenario()
def refresh_while_reloading():
    n = len(log_lines())
    main(lambda: (k().reload_scene(), k().refresh_display()))
    assert wait_log("scene reloaded", 120, n) is not None, "the reload did not finish"
    return "clean in %ss" % wait_clean(150)


@scenario()
def select_five_hundred_things():
    def go():
        made = [cmds.spaceLocator()[0] for _ in range(500)]
        cmds.select(made)
        return made
    made = main(go)
    time.sleep(2)
    main(lambda: (cmds.select(clear=True), cmds.delete(made)))
    time.sleep(2)
    assert worker_alive() and player_alive()
    return "selected and deleted 500 locators; state %r" % status().get("state")


@scenario()
def show_selected_in_the_cache_with_nothing_selected():
    main(lambda: cmds.select(clear=True))
    main(lambda: k().cache_selected(True))
    time.sleep(1)
    assert worker_alive()
    return "asked to select something first"


@scenario()
def remove_and_show_selected_in_the_cache():
    n = len(log_lines())
    main(lambda: (cmds.select("prop"), k().cache_selected(False)))
    assert wait_log("removed: prop", 10, n) is not None, "Remove selected did not reach the background Maya"
    wait_clean(60)
    n = len(log_lines())
    main(lambda: (cmds.select("prop"), k().cache_selected(True)))
    assert wait_log("message assets", 10, n) is not None
    main(lambda: cmds.select(clear=True))
    return "removed, then shown again; clean in %ss" % wait_clean(60)


@scenario()
def two_hundred_random_actions():
    random.seed(7)
    def act(i):
        what = random.choice(("key", "key", "key", "time", "hide", "refresh", "select", "unkeyed", "range"))
        if what == "key":
            cmds.setKeyframe("hero", at=random.choice(("translateY", "rotateZ", "scaleX")),
                             t=random.randint(FIRST, LAST), v=random.uniform(-5, 5))
        elif what == "time":
            cmds.currentTime(random.randint(FIRST, LAST))
        elif what == "hide":
            cmds.setAttr("prop.visibility", random.random() > 0.5)
        elif what == "refresh":
            k().refresh_display()
        elif what == "select":
            cmds.select(random.choice(("hero", "prop", "shotCam")))
        elif what == "unkeyed":
            cmds.setAttr("prop.translateZ", random.uniform(-4, 4))
        elif what == "range":
            a = random.randint(FIRST, LAST - 4)
            cmds.playbackOptions(minTime=a, maxTime=random.randint(a + 2, LAST))
    for i in range(200):
        main(lambda: act(i))
        time.sleep(0.03)
    main(lambda: (cmds.playbackOptions(minTime=FIRST, maxTime=LAST), cmds.setAttr("prop.visibility", True),
                  cmds.select(clear=True), k().refresh_display()))
    time.sleep(2)
    took = wait_clean(180)
    assert worker_alive() and player_alive()
    return "all 200 done; clean in %ss" % took


@scenario()
def the_player_is_closed_then_the_shelf_button_pressed():
    old = k().player_proc
    old.terminate()
    assert wait(lambda: old.poll() is not None, 10) is not None
    time.sleep(1)
    main(controller().shelf_click)
    assert wait(lambda: player_alive() and k().player_proc is not old, 20) is not None, "the player did not reopen"
    assert worker_alive(), "the background Maya went with the player"
    return "player reopened; background Maya kept running"


@scenario()
def the_background_maya_dies_then_restart():
    proc = k().worker_proc
    proc.terminate()
    assert wait(lambda: proc.poll() is not None, 10) is not None
    assert wait(lambda: "error" in (status().get("state") or ""), 15) is not None, \
        "nothing said the background Maya had gone: state %r" % status().get("state")
    said = status().get("state")
    main(controller().shelf_restart)
    assert wait(lambda: k().running and getattr(k(), "worker_proc", None) not in (None, proc), 40) is not None, \
        "Restart did not start a new background Maya"
    wait_ready()
    wait_clean(150)
    return "player was told (%s); Restart worked" % said


@scenario(fresh=True)
def stop_while_it_is_still_starting():
    main(build_scene)
    main(controller().shelf_click)
    wait(lambda: getattr(k(), "worker_proc", None) is not None, 20)
    proc = k().worker_proc
    time.sleep(4)
    main(controller().shelf_stop)
    assert wait(lambda: not k().running, 10) is not None
    assert wait(lambda: proc.poll() is not None, 60) is not None, "the half-started background Maya was left running"
    return "stopped cleanly 4s into the start"


@scenario(fresh=True)
def stop_and_start_again_straight_away():
    main(build_scene)
    start()
    stop()
    took = start()
    return "second start ready in %ss" % took


@scenario()
def file_new_while_running():
    proc, player = k().worker_proc, k().player_proc
    main(lambda: cmds.file(new=True, force=True))
    assert wait(lambda: not k().running, 15) is not None, "bgcache kept running after File > New"
    assert wait(lambda: proc.poll() is not None, 30) is not None, "the background Maya was left running after File > New"
    wait(lambda: player.poll() is not None, 30)
    return "stopped by itself; player %s" % ("closed" if player.poll() is not None else "LEFT OPEN")


@scenario(fresh=True)
def start_with_only_mayas_own_cameras():
    main(lambda: build_scene(cameras=False))
    main(controller().shelf_click)
    wait(lambda: k().running, 20)
    took = wait(lambda: (status().get("state") or "").startswith("ready"), 180)
    assert took is not None, "never got ready: %r" % status().get("state")
    assert worker_alive() and player_alive()
    return "ready in %ss; state %r; cameras offered: %s" % (
        took, status().get("state"), [c.get("label") for c in (k().cfg.get("cameras") or [])])


@scenario(fresh=True)
def a_one_frame_shot():
    main(lambda: build_scene(first=1001, last=1001))
    start()
    assert "1001" in versions(), "frame 1001 was not cached: %s" % sorted(versions())
    return "state %r, frames %s" % (status().get("state"), sorted(versions()))


@scenario(fresh=True)
def a_shot_that_starts_before_frame_zero():
    main(lambda: build_scene(first=-10, last=5))
    start()
    got = sorted(int(f) for f in versions())
    assert got == list(range(-10, 6)), "frames cached: %s" % got
    return "16 frames, -10 to 5"


# ------------------------------------------------------------------ running
def errors_since(marks):
    """New Python errors in the Script Editor's history and the background Maya's log."""
    found = []
    try:
        text = open(HISTORY, errors="replace").read()
        new, marks["history"] = text[marks.get("history", 0):], len(text)
        for line in new.splitlines():
            if ("# Error" in line or "Traceback (most recent" in line) and "torture" not in line:
                found.append("your Maya: " + line.strip()[:220])
    except Exception:
        pass
    try:
        path = paths()["log"]
        text = open(path, errors="replace").read()
        key = "log:" + path
        new, marks[key] = text[marks.get(key, 0):], len(text)
        for line in new.splitlines():
            if "Traceback (most recent" in line or line.startswith("# Error") or "Error: line" in line:
                found.append("background Maya: " + line.strip()[:220])
    except Exception:
        pass
    return found[:6]


def setup():
    if cmds.file(q=True, sceneName=True):
        raise RuntimeError("a saved scene is open: this test only runs on an empty, unsaved scene")
    if BUILD:
        for m in sorted(m for m in sys.modules if m == "bgcache" or m.startswith("bgcache.")):
            del sys.modules[m]
        shutil.rmtree(ROOT, ignore_errors=True)
        with zipfile.ZipFile(BUILD) as z:
            z.extractall(ROOT)
        found = glob.glob(os.path.join(ROOT, "**", "bgcache", "__init__.py"), recursive=True)
        if not found:
            raise RuntimeError("no bgcache/ folder in %s" % BUILD)
        sys.path[:] = [p for p in sys.path if os.path.normcase(HERE) not in os.path.normcase(p)]
        sys.path.insert(0, os.path.dirname(os.path.dirname(sorted(found, key=len)[0])))
    import bgcache
    controller().get()        # made here, on Maya's main thread: its timers only run when made there
    report["version"] = bgcache.__version__
    report["package"] = os.path.dirname(bgcache.__file__)
    report["edition"] = "Full" if os.path.isdir(os.path.join(os.path.dirname(bgcache.__file__), "continuity")) else "Simple"
    report["was"] = {"history": cmds.scriptEditorInfo(query=True, writeHistory=True),
                     "file": cmds.scriptEditorInfo(query=True, historyFilename=True)}
    open(HISTORY, "w").close()
    cmds.scriptEditorInfo(historyFilename=HISTORY, writeHistory=True)


def cleanup():
    said = []
    try:
        if k().running:
            controller().shelf_stop()
    except Exception as error:
        said.append("stop: %r" % error)
    try:
        was = report.get("was") or {}
        cmds.scriptEditorInfo(writeHistory=bool(was.get("history")))
        if was.get("file"):
            cmds.scriptEditorInfo(historyFilename=was["file"])
    except Exception as error:
        said.append("history: %r" % error)
    cmds.file(new=True, force=True)
    if BUILD:
        sys.path[:] = [p for p in sys.path if os.path.normcase(HERE) not in os.path.normcase(p)]
        for m in sorted(m for m in sys.modules if m == "bgcache" or m.startswith("bgcache.")):
            del sys.modules[m]
    return "; ".join(said) or "empty scene%s" % (", test code unloaded" if BUILD else "")


def write_text():
    rows = report["results"]
    count = lambda what: sum(1 for r in rows if r["result"] == what)
    out = ["bgcache %s (%s) torture test, %s" % (report.get("version"), report.get("edition"), time.strftime("%Y-%m-%d %H:%M")),
           "%d passed, %d failed, %d observed, in %d min" % (count("PASS"), count("FAIL"), count("OBSERVED"),
                                                              round((time.time() - report["started"]) / 60.0)), ""]
    for r in rows:
        out.append("%-8s %-52s %5.1fs  %s" % (r["result"], r["name"].replace("_", " "), r["seconds"], r.get("said", "")))
        for e in r.get("errors") or []:
            out.append("           ! " + e)
    out += ["", "left running at the end: %s" % ", ".join(report.get("left_running") or ["?"]), report.get("cleanup", "")]
    with open(TEXT, "w") as handle:
        handle.write("\n".join(out) + "\n")


def run():
    marks = {}
    try:
        main(setup)
        for name, fn, fresh, observed in SCENARIOS:
            if ONLY and name not in ONLY:
                continue
            row = {"name": name, "result": "PASS", "seconds": 0.0}
            t0 = time.time()
            try:
                if fresh and k().running:
                    stop()
                elif not fresh and not k().running:
                    main(build_scene)
                    start()
                errors_since(marks)                      # only this scenario's errors count
                row["said"] = fn() or ""
                if observed:
                    row["result"] = "OBSERVED"
            except AssertionError as error:
                row["result"], row["said"] = "FAIL", str(error)
            except Exception:
                row["result"], row["said"] = "FAIL", traceback.format_exc()[-700:]
            time.sleep(1.0)
            row["errors"] = errors_since(marks)
            if row["errors"] and row["result"] == "PASS":
                row["result"] = "FAIL"
                row["said"] = (row.get("said") or "") + " (but Python errors were written, below)"
            row["seconds"] = round(time.time() - t0, 1)
            report["results"].append(row)
            save()
        try:
            stop()
        except AssertionError as error:
            report["final_stop"] = str(error)
        time.sleep(3)
        tl = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], stdout=subprocess.PIPE, universal_newlines=True,
                            creationflags=0x08000000).stdout if os.name == "nt" else \
            subprocess.run(["ps", "-eo", "comm"], stdout=subprocess.PIPE, universal_newlines=True).stdout
        report["left_running"] = sorted(l.split(",")[0].strip('"') for l in tl.splitlines() if "maya" in l.lower())
    except Exception:
        report["crashed"] = traceback.format_exc()[-1500:]
    finally:
        try:
            report["cleanup"] = main(cleanup)
        except Exception as error:
            report["cleanup"] = "cleanup failed: %r" % error
        report["finished"] = True
        save()
        try:
            write_text()
        except Exception as error:
            report["text_error"] = repr(error)
            save()


if os.path.isfile(REPORT):
    os.remove(REPORT)
threading.Thread(target=run, daemon=True).start()
print("bgcache torture test started (%d scenarios): results in %s" % (len(SCENARIOS), TEXT))
