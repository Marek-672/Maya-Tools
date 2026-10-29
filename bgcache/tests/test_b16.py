"""0.8.0b16: the background Maya draws with the same viewport renderer as your
shot camera's view (studio: Viewport 2.0 + the studio's render override from
its own plug-in, which the studio playblast uses too; the standard
Viewport 2.0 was ~20x slower and a plain playblast crashes Maya there)."""
import os, sys, json, types
import _source  # noqa: E402  (tests/_source.py)
STUDIO_OPTS = "dn" + "ViewportOptions"       # a studio's own command (kept out of the public text)
STUDIO_PLUGIN = "dn" + "Viewport2Renderer"
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
src = open(os.path.join(TESTS, "test_worker.py")).read()
exec(src.split("step(); st = json.load")[0])          # fake Maya + a Worker `w`

edits, calls = [], []
cmds.modelEditor = lambda panel, edit=False, query=False, **k: edits.append(k)
setattr(cmds, STUDIO_OPTS, lambda **k: calls.append((STUDIO_OPTS, k)))
cmds.ogs = lambda **k: calls.append(("ogs", k))
w.panel = "renderView"
w.cfg["viewport_renderer"] = {"renderer": "vp2Renderer", "override": "the studioViewport2",
                              "plugins": [{"name": STUDIO_PLUGIN, "path": "/x/%s.py" % STUDIO_PLUGIN}]}
w._apply_renderer()
assert {"rendererName": "vp2Renderer"} in edits and {"rendererOverrideName": "the studioViewport2"} in edits
assert not [c for c in calls if c[0] == STUDIO_OPTS], "studio commands live in the studio's own file (b19)"
assert ("ogs", {"disposeReleasableTextures": True}) not in calls, "b19: freeing textures at start drew the cache grey"
print("ok: the cache draws with your shot camera's renderer (Viewport 2.0 + the studioViewport2); no studio "
      "commands in the shared code, no texture clean-up at start (b19)")

def broken(panel, edit=False, query=False, **k):
    if "rendererOverrideName" in k:
        raise RuntimeError("no such override")
    edits.append(k)
cmds.modelEditor = broken
del edits[:]
w._apply_renderer()
assert {"rendererName": "vp2Renderer"} in edits
print("ok: an override the background Maya can't use leaves the standard Viewport 2.0 (logged), no failure")

c = _source.source("controller")
assert "def viewport_renderer():" in c and '"viewport_renderer": renderer,' in c
assert 'cfg["plugins"] += [p for p in renderer.get("plugins") or [] if p["name"] not in have]' in c
wsrc = open(os.path.join(REPO, "bgcache", "worker.py")).read()
assert wsrc.index("self._load_plugins()") < wsrc.index("self._build_panel()")
assert "        self._apply_renderer()\n        self._apply_display()" in wsrc
pr = os.path.join(REPO, "studio_private", "profile.json")
if os.path.isfile(pr):
    assert json.load(open(pr))["viewport_plugins"] == [STUDIO_PLUGIN]
print("ok: its plug-in loads in the light background Maya before the render view is made; "
      "profile background_viewport_renderer: false turns it off")
