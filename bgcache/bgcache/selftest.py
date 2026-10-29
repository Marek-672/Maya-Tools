"""bgcache self-test: one command, a short report to read back.

In your Maya's Script Editor (Python tab):

    import bgcache.selftest as t; t.run()

    t.run(hide_selected=True)   # also time it with what you've selected hidden
                                # (hidden in the background Maya only)

It prints a report of about 20 lines and saves it to
~/.bgcache/selftest_<date>.txt:

- Your Maya: versions, evaluation mode, which evaluators exist and are on,
  your viewport's display settings.
- Background Maya (while bgcache is running): its evaluators, what its render
  view is set to, and a playblast benchmark on the camera you're viewing:
  batches of 1, 3, 6 and 12 frames, fitted to "start-up + time per frame",
  then the same with the invisibility evaluator off, the frustum evaluator
  on (if your Maya has one) and your selection hidden (if asked). Rendering
  pauses while it runs (about a minute on a heavy rig); nothing in the cache
  changes.
- This session's worker.log: edits synced, average time to the first new
  frame and its parts, playblast times by batch size.
"""
import getpass
import glob
import os
import re
import time

SIZES = (1, 3, 6, 12)          # batch sizes timed for the main benchmark
VARIANT_SIZES = (1, 6)         # quicker: two sizes are enough for a fit
REPEATS = 2                    # best of two, so a one-off hiccup doesn't count
WAIT_S = 240                   # how long your Maya waits for the background part
SHOWN_FLAGS = ("displayAppearance", "wireframeOnShaded", "xray", "backfaceCulling",
               "displayTextures", "displayLights", "polymeshes", "pluginShapes")


# --------------------------------------------------------------------------
# Pure helpers (tested without Maya)
# --------------------------------------------------------------------------
def fit(samples):
    """[(frames, seconds)] -> (start-up s, s per frame), least squares, or
    None with fewer than two batch sizes."""
    if len({n for n, _ in samples}) < 2:
        return None
    k = float(len(samples))
    mn = sum(n for n, _ in samples) / k
    mt = sum(t for _, t in samples) / k
    var = sum((n - mn) ** 2 for n, _ in samples)
    per = sum((n - mn) * (t - mt) for n, t in samples) / var
    return max(0.0, mt - per * mn), max(0.0, per)


def model_text(model):
    if not model:
        return "not enough data"
    return "%.2fs start-up + %.2fs/frame" % model


EDIT_RE = re.compile(r"edit synced: (\d+) frames.*?first frame after ([\d.]+)s.*?"
                     r"\(your Maya ([\d.]+)s, pickup ([\d.]+)s, apply ([\d.]+)s, first frame render ([\d.]+)s\)")
RENDERED_RE = re.compile(r"rendered (\d+) frames in ([\d.]+)s \(playblast ([\d.]+)s\)")


def summarize_log(text):
    """Lines summing up a worker.log: edits synced and playblast times."""
    edits = [tuple(float(x) for x in m.groups()) for m in EDIT_RE.finditer(text or "")]
    blasts = [(int(m.group(1)), float(m.group(3))) for m in RENDERED_RE.finditer(text or "")]
    out = []
    if edits:
        k = float(len(edits))
        avg = lambda i: sum(e[i] for e in edits) / k
        first = sorted(e[1] for e in edits)
        out.append("%d edits synced: first new frame after %.2fs on average (median %.2fs, worst %.2fs)"
                   % (len(edits), avg(1), first[len(first) // 2], first[-1]))
        out.append("  of which: your Maya %.2fs, pickup %.2fs, apply %.2fs, first frame render %.2fs"
                   % (avg(2), avg(3), avg(4), avg(5)))
    else:
        out.append("no edits synced in this log yet")
    if blasts:
        by = {}
        for n, t in blasts:
            by.setdefault(n, []).append(t)
        sizes = sorted(by)
        shown = ", ".join("%d fr %.2fs (x%d)" % (n, sum(by[n]) / len(by[n]), len(by[n])) for n in sizes[:6])
        out.append("playblasts: %s%s" % (shown, ", ..." if len(sizes) > 6 else ""))
        out.append("  fitted: %s" % model_text(fit(blasts[-200:])))
    return out


def evaluator_text(states):
    """{name: on} -> 'cache off, deformer on, ...' with frustum/invisibility first."""
    first = [n for n in states if "frustum" in n.lower() or "invisib" in n.lower()]
    rest = sorted(n for n in states if n not in first)
    return ", ".join("%s %s" % (n, "on" if states[n] else "off") for n in sorted(first) + rest)


def frustum_name(states):
    return next((n for n in states if "frustum" in n.lower()), None)


def display_text(display):
    d = display or {}
    parts = []
    for flag in SHOWN_FLAGS:
        if flag in d:
            value = d[flag]
            parts.append("%s=%s" % (flag, ("on" if value else "off") if isinstance(value, bool) else value))
    return ", ".join(parts) or "(no viewport found)"


# --------------------------------------------------------------------------
# Maya: evaluators, display
# --------------------------------------------------------------------------
def evaluator_states(cmds):
    states = {}
    names = []
    for kwargs in ({"query": True, "name": True}, {"query": True}):
        try:
            names = cmds.evaluator(**kwargs) or []
        except Exception:  # older Maya: the other query form is tried next
            names = []
        if names:
            break
    if isinstance(names, str):
        names = [names]
    for name in names:
        try:
            states[name] = bool(cmds.evaluator(name=name, query=True, enable=True))
        except Exception:  # evaluator not loaded: reported as off
            states[name] = False
    return states


def _evaluation_mode(cmds):
    try:
        return cmds.evaluationManager(query=True, mode=True)[0]
    except Exception:  # report only: '?' in the self-test
        return "?"


# --------------------------------------------------------------------------
# Background Maya part (runs in the worker, from its message loop)
# --------------------------------------------------------------------------
def _bench(worker, cam, frame, sizes, repeats=REPEATS):
    """[(frames, best seconds)] playblasting the render view at frame onwards."""
    folder = os.path.join(worker.p["tmp"], "selftest")
    if not os.path.isdir(folder):
        os.makedirs(folder)
    out = []
    for n in sizes:
        a = min(max(frame, worker.first), max(worker.first, worker.last - n + 1))
        b = min(worker.last, a + n - 1)
        best = None
        for _ in range(repeats):
            t = worker._playblast(os.path.join(folder, "st"), a, b)
            best = t if best is None else min(best, t)
            for old in glob.glob(os.path.join(folder, "*")):
                try:
                    os.remove(old)
                except OSError:
                    pass
        out.append((b - a + 1, best))
    return out


def background_report(worker, msg):
    import maya.cmds as cmds
    lines = []
    states = evaluator_states(cmds)
    lines.append("evaluation %s; evaluators: %s" % (_evaluation_mode(cmds), evaluator_text(states) or "none listed"))
    frustum = frustum_name(states)
    lines.append("frustum evaluator: %s" % ("yes (%s)" % frustum if frustum else "not in this Maya"))
    shown = {}
    for flag in SHOWN_FLAGS:
        try:
            shown[flag] = cmds.modelEditor(worker.panel, query=True, **{flag: True})
        except Exception:  # flag not in this Maya version: left out of the report
            pass
    lines.append("render view: %s" % display_text(shown))
    cam = worker.view
    if not cam:
        lines.append("no camera viewed: benchmark skipped")
        return lines
    if cam != worker.panel_camera:
        cmds.modelEditor(worker.panel, edit=True, camera=cam)
        worker.panel_camera = cam
        worker._no_overscan(cam)
    frame = int(msg.get("frame") or worker.first)
    try:
        overscan = cmds.getAttr(cam + ".overscan") if cmds.nodeType(cam) == "camera" else \
            cmds.getAttr((cmds.listRelatives(cam, shapes=True, fullPath=True) or [cam])[0] + ".overscan")
    except Exception:  # report only: '?' in the self-test
        overscan = "?"
    lines.append("benchmark on %s from frame %d, %dx%d, overscan %s (best of %d):"
                 % (cam.split("|")[-1], frame, worker.cfg["width"], worker.cfg["height"], overscan, REPEATS))
    base = _bench(worker, cam, frame, SIZES)
    lines.append("  as is:  %s  -> %s" % (", ".join("%d fr %.2fs" % s for s in base), model_text(fit(base))))

    def variant(label, setup, undo):
        try:
            setup()
        except Exception as error:
            lines.append("  %s: couldn't set up (%s)" % (label, error))
            return
        try:
            got = _bench(worker, cam, frame, VARIANT_SIZES)
            lines.append("  %s:  %s  -> %s" % (label, ", ".join("%d fr %.2fs" % s for s in got),
                                                model_text(fit(got))))
        finally:
            try:
                undo()
            except Exception as error:
                lines.append("  (couldn't restore after %s: %s)" % (label, error))

    if states.get("invisibility"):
        variant("invisibility evaluator off",
                lambda: cmds.evaluator(name="invisibility", enable=False),
                lambda: cmds.evaluator(name="invisibility", enable=True))
    if frustum and not states.get(frustum):
        variant("frustum evaluator on",
                lambda: cmds.evaluator(name=frustum, enable=True),
                lambda: cmds.evaluator(name=frustum, enable=False))
    hide = [n for n in (msg.get("hide") or []) if cmds.objExists(n)]
    if msg.get("hide") and not hide:
        lines.append("  hidden: none of %s found in the background scene" % ", ".join(msg["hide"])[:120])
    if hide:
        before = {}

        def hide_them():
            for n in hide:
                plug = n + ".visibility"
                before[plug] = cmds.getAttr(plug)
                if not cmds.listConnections(plug, source=True, destination=False):
                    cmds.setAttr(plug, False)

        def show_them():
            for plug, value in before.items():
                if not cmds.listConnections(plug, source=True, destination=False):
                    cmds.setAttr(plug, value)
        variant("with %s hidden" % ", ".join(n.split("|")[-1] for n in hide)[:60], hide_them, show_them)
    return lines


# --------------------------------------------------------------------------
# Your Maya: run()
# --------------------------------------------------------------------------
def _report_path():
    folder = os.path.join(os.path.expanduser("~"), ".bgcache")
    if not os.path.isdir(folder):
        os.makedirs(folder)
    return os.path.join(folder, "selftest_%s.txt" % time.strftime("%Y%m%d_%H%M%S"))


def _latest_log(c):
    from bgcache import common
    if c.session:
        path = common.paths(c.session)["log"]
        if os.path.exists(path):
            return path
    logs = glob.glob(os.path.join(common.LOG_ROOT, "*", "worker.log"))
    return max(logs, key=os.path.getmtime) if logs else None


def local_report(cmds, c):
    import bgcache
    from bgcache import controller
    lines = ["bgcache %s self-test · %s · %s" % (bgcache.__version__, getpass.getuser(), time.strftime("%Y-%m-%d %H:%M"))]
    try:
        maya = cmds.about(version=True)
        cut = cmds.about(cutIdentifier=True)
    except Exception:  # report only: '?' in the self-test
        maya, cut = "?", "?"
    lines.append("Maya %s (%s), scene %s" % (maya, cut, os.path.basename(cmds.file(query=True, sceneName=True) or "untitled")))
    lines.append("YOUR MAYA")
    lines.append("  evaluation %s; evaluators: %s" % (_evaluation_mode(cmds), evaluator_text(evaluator_states(cmds)) or "none listed"))
    lines.append("  viewport: %s" % display_text(controller.viewport_display()))
    return lines


def run(hide_selected=False, hide=None, wait=True):
    """Print the self-test report (and save it). hide_selected / hide: also
    time the background Maya with those objects hidden (there only)."""
    import maya.cmds as cmds
    from bgcache import common, controller
    c = controller.get()
    lines = local_report(cmds, c)
    names = list(hide or [])
    if hide_selected:
        names += cmds.ls(selection=True, long=True) or []
    log_path = _latest_log(c)

    def finish(bg_lines):
        out = list(lines)
        out.append("BACKGROUND MAYA")
        out += ["  " + l for l in bg_lines]
        out.append("WORKER LOG (%s)" % (os.path.basename(os.path.dirname(log_path)) if log_path else "none"))
        text = ""
        if log_path:
            try:
                with open(log_path) as handle:
                    text = handle.read()
            except (IOError, OSError):
                pass
        out += ["  " + l for l in summarize_log(text)]
        path = _report_path()
        with open(path, "w") as handle:
            handle.write("\n".join(out) + "\n")
        print("\n" + "\n".join(out))
        print("(saved to %s)" % path)
        return out

    if not c.running:
        return finish(["bgcache isn't running: Start it to test the background Maya too"])
    result = os.path.join(common.paths(c.session)["logs"], "selftest.json")
    token = "%.6f" % time.time()
    common.post_message(c.session, {"op": "selftest", "id": token, "hide": names,
                                    "frame": int(round(cmds.currentTime(query=True)))})
    print("bgcache self-test: timing playblasts in the background Maya (about a minute)...")
    if not wait:
        return lines
    try:
        from PySide6 import QtCore
    except ImportError:  # Maya 2024 and earlier (PySide2)
        from PySide2 import QtCore
    started = time.time()
    holder = {}

    def poll():
        st = common.read_json(result) or {}
        if st.get("id") == token:
            holder["out"] = finish(st.get("lines") or [])
            return
        if time.time() - started > WAIT_S:
            holder["out"] = finish(["no answer from the background Maya after %ds (busy or stopped?)" % WAIT_S])
            return
        QtCore.QTimer.singleShot(500, poll)
    QtCore.QTimer.singleShot(500, poll)      # your Maya stays usable while it runs
    return lines
