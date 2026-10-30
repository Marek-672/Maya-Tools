"""Help > Report a problem (0.9.0b3).

Gathers what's useful for working out a problem into one zip: what you wrote,
versions and system, the session's logs (worker, player, trace), the newest
Self-test report and the player settings. You see the list before anything
leaves the computer.

Hide names (on by default) swaps the show, sequence, shot, scene and user
names for SHOW / SEQ / SHOT / SCENE / USER everywhere in the report.

Save report... always works. Send needs the profile's reports_url (a Google
Apps Script web app that files reports in a Google Drive folder; see
tools/reports_receiver.gs). It's empty by default, so nothing is sent unless
whoever set bgcache up switched it on. No Qt or Maya here.
"""
import base64
import getpass
import glob
import io
import json
import os
import platform
import sys
import time
import zipfile

from bgcache import common

LOG_FILES = ("worker.log", "player.log", "trace.log")
MAX_LOG_BYTES = 400 * 1024          # the end of each log: the part that matters
MIN_NAME = 3                        # shorter names would replace too much


def _tail(path, limit=MAX_LOG_BYTES):
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as handle:
            if size > limit:
                handle.seek(size - limit)
            data = handle.read()
    except (IOError, OSError):
        return None
    text = data.decode("utf-8", "replace")
    if size > limit:
        text = "[... the first %d KB left out ...]\n" % ((size - limit) // 1024) + text.split("\n", 1)[-1]
    return text


def _newest(pattern):
    found = glob.glob(pattern)
    return max(found, key=os.path.getmtime) if found else None


def names_to_hide(cfg):
    """{name: label} for Hide names: the shot's show / sequence / shot (from
    the profile's shot_folder), the scene name and the user."""
    from bgcache import profile
    out = {}
    scene = (cfg or {}).get("original_scene") or (cfg or {}).get("scene") or ""
    try:
        fields = profile.match_shot(scene) or {}
    except Exception:  # an odd profile must never stop a report
        fields = {}
    for key, label in (("show", "SHOW"), ("sequence", "SEQ"), ("shot", "SHOT")):
        if fields.get(key):
            out[fields[key]] = label
    if scene:
        stem = os.path.splitext(os.path.basename(scene))[0]
        out.setdefault(stem, "SCENE")
        out.setdefault(profile.scene_stem(scene), "SCENE")
    user = (cfg or {}).get("user") or getpass.getuser()
    out.setdefault(user, "USER")
    return {k: v for k, v in out.items() if k and len(k) >= MIN_NAME}


def hide(text, names):
    for name in sorted(names, key=len, reverse=True):     # longest first: shot before show
        text = text.replace(name, names[name])
    return text


def about(cfg, version, edition):
    """The header lines: versions and system."""
    return [
        "bgcache %s (%s edition)" % (version, edition),
        "system: %s %s (%s)" % (platform.system(), platform.release(), platform.machine()),
        "python: %s" % sys.version.split()[0],
        "maya: %s" % ((cfg or {}).get("maya_version") or "see the logs"),
        "profile: %s" % ((cfg or {}).get("profile") or "built-in defaults"),
        "session: %s" % os.path.basename((cfg or {}).get("session") or "?"),
        "time: %s" % time.strftime("%Y-%m-%d %H:%M:%S"),
    ]


def gather(session, cfg, version, edition):
    """[(name in the zip, path or None, text)]: everything a report would
    hold, before Hide names. The list the dialog shows."""
    items = [("about.txt", None, "\n".join(about(cfg, version, edition)) + "\n")]
    logs = common.log_dir(session) if session else None
    for name in LOG_FILES:
        path = os.path.join(logs, name) if logs else None
        text = _tail(path) if path and os.path.exists(path) else None
        if text is not None:
            items.append((name, path, text))
    selftest = _newest(os.path.join(os.path.expanduser("~"), ".bgcache", "selftest_*.txt"))
    if selftest:
        items.append(("selftest.txt", selftest, _tail(selftest) or ""))
    if os.path.exists(common.PREFS_PATH):
        items.append(("player_settings.json", common.PREFS_PATH, _tail(common.PREFS_PATH) or ""))
    return items


def build(items, what, email="", names=None):
    """The report zip as bytes. names: Hide names (from names_to_hide), or None."""
    note = "What happened:\n%s\n" % (what.strip() or "(nothing written)")
    if email.strip():
        note += "\nReply to: %s\n" % email.strip()
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, _path, text in [("what_happened.txt", None, note)] + list(items):
            if names and name != "what_happened.txt":
                text = hide(text, names)
            z.writestr(name, text)
    return out.getvalue()


def file_name(version):
    return "bgcache_report_%s_%s.zip" % (version, time.strftime("%Y%m%d_%H%M%S"))


def save(data, path):
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    with open(path, "wb") as handle:
        handle.write(data)
    return path


def send(url, data, name, version, timeout=30):
    """Post the zip to the reports receiver. (True, message) or (False, why)."""
    try:
        from urllib.request import Request, urlopen
    except ImportError:              # Python 2 Maya
        from urllib2 import Request, urlopen
    body = json.dumps({"name": name, "version": version,
                       "zip": base64.b64encode(data).decode("ascii")}).encode("utf-8")
    request = Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        answer = urlopen(request, timeout=timeout).read().decode("utf-8", "replace")
    except Exception as error:       # no network, wrong address...: shown to you
        return False, "couldn't send: %s" % error
    try:
        reply = json.loads(answer)
    except ValueError:
        return False, "the reports address didn't answer as expected"
    if reply.get("ok"):
        return True, "Report sent. Thank you!"
    return False, "not accepted: %s" % reply.get("error", "unknown reason")
