"""0.9.0b2: updates only when you ask. Help > Check for updates looks in the
studio releases folder, or on GitHub for everyone else; the answer shows in
the Help menu; no Update button, nothing checks or installs by itself."""
import io
import json
import os
import sys
import tempfile
import zipfile
from unittest import mock

TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
sys.path.insert(0, REPO)
from bgcache import update, profile                       # noqa: E402

p = open(os.path.join(REPO, "bgcache", "player.py")).read()
assert "check_for_update(quiet=True)" not in p and "singleShot(4000, lambda: self.check_for_update" not in p
assert "b_update" not in p and "updateButton" not in p and "def offer_update" not in p
assert 'help_menu.addAction("Check for updates", self.check_for_update)' in p
assert "self._update_item.setVisible(bool(self._update_source()))" in p
print("ok: nothing checks for updates by itself, and there's no orange Update button")
assert '"Latest: %s (you have %s)"' in p and '"You have the latest (%s)"' in p
assert '"Update to %s and restart"' in p and '"What\'s new in %s"' in p and '"Couldn\'t check: %s"' in p
assert "QtCore.QTimer.singleShot(0, self.b_help.showMenu)" in p
print("ok: the answer shows in the Help menu: Latest (you have ...), What's new, Update to ... and restart")

# ---- where it looks
assert profile.DEFAULT["github_releases"] == "Marek-672/Maya-Tools" and profile.DEFAULT["releases_folder"] == ""
studio = os.path.join(REPO, "studio_private", "profile.json")
if os.path.isfile(studio):
    pr = json.load(open(studio))
    assert pr["releases_folder"] and pr["github_releases"] == ""
src = p[p.index("    def _update_source(self):"):p.index("    def check_for_update(self):")]
assert src.index('"releases_folder"') < src.index('"github_releases"')
print("ok: studio builds look only in their releases folder; others on GitHub (Marek-672/Maya-Tools)")


# ---- GitHub, with the network faked
def fake_answer(payload):
    class A(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            self.close()
    return A(payload if isinstance(payload, bytes) else json.dumps(payload).encode())


RELEASES = [
    {"tag_name": "shot-transfer-v1.0", "draft": False, "body": "", "assets": []},
    {"tag_name": "bgcache-v0.9.0b3", "draft": True, "body": "draft", "assets": []},
    {"tag_name": "bgcache-v0.9.0b2", "draft": False, "body": "**New:** Help > Check for updates",
     "html_url": "https://github.com/Marek-672/Maya-Tools/releases/tag/bgcache-v0.9.0b2",
     "assets": [{"name": "bgcache-0.9.0b2-windows-simple.zip", "browser_download_url": "https://x/w.zip"},
                {"name": "bgcache-0.9.0b2-linux-simple.zip", "browser_download_url": "https://x/l.zip"}]},
    {"tag_name": "bgcache-v0.9.0b1", "draft": False, "body": "", "assets": []},
]
seen = []


def fake_get(url, timeout, accept="application/vnd.github+json"):
    seen.append(url)
    return fake_answer(RELEASES)


with mock.patch.object(update, "_get", fake_get):
    r = update.check_github("Marek-672/Maya-Tools", "0.9.0b1", "windows", "simple")
assert seen == ["https://api.github.com/repos/Marek-672/Maya-Tools/releases?per_page=50"]
assert r["state"] == "newer" and r["version"] == "0.9.0b2" and r["zip_url"] == "https://x/w.zip"
assert r["zip_name"] == "bgcache-0.9.0b2-windows-simple.zip" and "Check for updates" in r["notes"]
print("ok: GitHub: the newest published bgcache release (not drafts, not other tools), with the zip for "
      "your system and edition and its notes")
with mock.patch.object(update, "_get", fake_get):
    assert update.check_github("Marek-672/Maya-Tools", "0.9.0b2", "windows", "simple")["state"] == "latest"
    assert update.check_github("Marek-672/Maya-Tools", "0.9.0b1", "macos", "simple")["state"] == "error"
print("ok: up to date says so; a release without your system's zip is an error, with the download page")


class HTTPError(Exception):
    def __init__(self, code):
        self.code = code


for error, words in ((HTTPError(404), "can't be found"), (HTTPError(403), "busy"),
                     (OSError("[SSL: CERTIFICATE_VERIFY_FAILED]"), "certificate"),
                     (OSError("Name or service not known"), "no connection")):
    def failing(*a, **k):
        raise error
    with mock.patch.object(update, "_get", failing):
        r = update.check_github("Marek-672/Maya-Tools", "0.9.0b1", "windows", "simple")
    assert r["state"] == "error" and words in r["message"] and r["page"].endswith("/releases"), r
print("ok: no connection, not public yet, GitHub busy or a certificate problem: a plain message and the "
      "download page, never an error box")

# ---- a GitHub download (drag-and-drop layout) installs like a releases folder zip
tmp = tempfile.mkdtemp()
dl = os.path.join(tmp, "dl.zip")
with zipfile.ZipFile(dl, "w") as z:
    top = "bgcache-0.9.0b2-windows-simple/module/scripts/bgcache/"
    z.writestr(top + "__init__.py", '__version__ = "0.9.0b2"\n')
    z.writestr(top + "controller.py", "# new\n")
    z.writestr("bgcache-0.9.0b2-windows-simple/install_bgcache.py", "# installer\n")
with mock.patch.object(update, "_get", lambda url, timeout, accept=None: fake_answer(open(dl, "rb").read())):
    got = update.download("https://x/w.zip", os.path.join(tmp, "session_tmp"), "bgcache-0.9.0b2-windows-simple.zip")
assert os.path.isfile(got) and not os.path.exists(got + ".part")
installed = os.path.join(tmp, "modules", "bgcache", "scripts", "bgcache")
os.makedirs(installed)
open(os.path.join(installed, "__init__.py"), "w").write('__version__ = "0.9.0b1"\n')
open(os.path.join(installed, "controller.py"), "w").write("# old\n")
old, new, backup = update.install_over(got, installed, log=lambda *a: None)
assert (old, new) == ("0.9.0b1", "0.9.0b2") and open(os.path.join(installed, "controller.py")).read() == "# new\n"
assert open(os.path.join(backup, "controller.py")).read() == "# old\n"
print("ok: Update and restart from GitHub: downloads your zip, swaps it in (the drag-and-drop layout), "
      "keeps the old copy")

# ---- the network stays off unless you click
u = open(os.path.join(REPO, "bgcache", "update.py")).read()
assert u.count("import urllib.request") == 1 and "def _get(" in u
import glob                                                 # noqa: E402
for path in glob.glob(os.path.join(REPO, "bgcache", "**", "*.py"), recursive=True):
    if os.path.basename(path) not in ("update.py", "report.py", "ffmpeg_get.py"):
        text = open(path).read()
        assert "urllib" not in text and "import socket" not in text and "http.client" not in text, path
r = open(os.path.join(REPO, "bgcache", "report.py")).read()
assert r.count("urlopen(") == 1 and r.index("urlopen(") > r.index("def send(")
f = open(os.path.join(REPO, "bgcache", "continuity", "ffmpeg_get.py")).read()
assert f.count("urlopen(") == 1 and f.index("urlopen(") > f.index("def _fetch(")
print("ok: only update.py (Check for updates), report.py (Send) and ffmpeg_get.py (Download it for me) go online, "
      "and only when you click")
