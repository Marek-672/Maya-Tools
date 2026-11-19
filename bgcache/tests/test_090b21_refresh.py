"""0.9.0b21: one Refresh: what it says, what counts as "the scene changed",
the note next to Refresh, the question before a reload."""
import os, sys
TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(TESTS))
from bgcache import refreshing as r

old = {"references": {"heroRN": ["/a/hero.ma", True], "setRN": ["/a/set.ma", True], "propRN": ["/a/cup.ma", False]},
       "constraints": 4, "deformers": 10, "objects": 900}
assert r.structure_changes(old, dict(old)) == [] and r.structure_changes(None, old) == []
new = {"references": {"heroRN": ["/a/hero_v2.ma", True], "propRN": ["/a/cup.ma", True], "carRN": ["/a/car.ma", True],
                      "busRN": ["/a/bus.ma", True]}, "constraints": 5, "deformers": 10, "objects": 880}
assert r.structure_changes(old, new) == ["2 references added", "1 reference removed", "1 reference replaced",
                                         "1 reference loaded", "1 constraint added", "20 objects removed"]
print("ok: the scene has changed when references are added, removed, replaced, loaded or unloaded, or the "
      "numbers of constraints, deformers or objects differ; said in plain words")

assert r.summary() == ""
assert r.summary(viewport=["xray"], layers=2) == "Refreshed: viewport settings, 2 layer settings. Re-rendering."
assert r.summary(values=5, controls=2, shown_hidden=1) == \
    "Refreshed: 1 object shown or hidden, 5 unkeyed values on 2 controls. Re-rendering."
assert r.summary(planes=1, gpu=True) == "Refreshed: 1 image plane, GPU setting. Re-rendering."
assert "Nothing to update" in r.NOTHING and "Reload scene" in r.NOTHING
print("ok: Refresh says what it sent, or that there was nothing it could see (and where Reload scene is)")

assert r.note([]) == "" and r.note(["unknown"]) == ""
assert r.note(["reference-added"]) == "Scene changed: a reference was added"
assert r.note(["reference-added", "constraint"]) == "Scene changed: a constraint was made (and more)"
print("ok: the orange note next to Refresh says what Maya reported")

title, text = r.question(["2 references added", "1 constraint added"], 48)
assert title == "Your scene has changed since the cache was made"
assert text.startswith("2 references added, 1 constraint added. To show that, the player has to reload the scene, "
                       "which took 48 seconds last time.")
assert "last time" not in r.question(["1 object added"], 0)[1] and "about 3 minutes" in r.question(["x"], 170)[1]
print("ok: the question says what changed and how long the last reload took (nothing about time the first time)")

src = lambda name: open(os.path.join(os.path.dirname(TESTS), "bgcache", name)).read()
p, ps, cr, cs = src("player.py"), src("player_session.py"), src("controller_refresh.py"), src("controller_scene.py")
assert "self.b_reload" not in p and "self.b_rerender" not in p and '"Push selected"' not in p
assert 'app_menu.addAction("Reload scene", self.reload_scene)' in p and 'help_menu.addAction("Re-render all"' in p
assert '_tool("Reload scene"' in p and '_tool("Not now"' in p and "QMessageBox" not in p[p.index("_build_reload_question"):][:1600]
assert "def answer_reload" in ps and "self.reload_question.setVisible(True)" in ps
assert "self.unkeyed_changes()" in cr and "self.changed_structure()" in cr and "self.reload_scene()" not in cr[:cr.index("def reload_scene")]
assert "if node not in self.vis_base or self.vis_base[node] == visible:" in cr      # a new object isn't "shown"
assert "kAfterCreateReference" in cs and 'addNodeAddedCallback(self._on_constraint, "constraint")' in cs
print("ok: the bar has Refresh only (Reload scene in the bgcache menu, Re-render all in Help, no Push selected); "
      "the question is a bar in the player, not a dialog; Refresh never reloads by itself")
