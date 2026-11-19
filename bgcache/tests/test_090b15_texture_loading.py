"""0.9.0b15: the background Maya loads textures before drawing, checked before
every render (it was found back on "parallel": blurred image-sequence planes)."""
import os, sys, ast, types
from unittest import mock
TESTS = os.path.dirname(os.path.abspath(__file__))
path = os.path.join(os.path.dirname(TESTS), "bgcache", "worker.py")
src = open(path).read()
tree = ast.parse(src)
fn = next(n for c in tree.body if isinstance(c, ast.ClassDef) and c.name == "Worker"
          for n in c.body if isinstance(n, ast.FunctionDef) and n.name == "_immediate_textures")
logged, state = [], {"mode": "parallel", "sets": 0}
cmds = mock.MagicMock()
def displayPref(query=False, materialLoadingMode=None):
    if query:
        return state["mode"]
    state["mode"] = materialLoadingMode; state["sets"] += 1
cmds.displayPref.side_effect = displayPref
ns = {"cmds": cmds, "log": logged.append}
exec(compile(ast.Module(body=[fn], type_ignores=[]), path, "exec"), ns)
w = types.SimpleNamespace()
ns["_immediate_textures"](w)
assert state["mode"] == "immediate" and state["sets"] == 1 and "was 'parallel'" in logged[0]
print("ok: found on 'parallel': set to immediate, and the log says so")
ns["_immediate_textures"](w)
assert state["sets"] == 1 and len(logged) == 1
print("ok: already immediate: nothing done, nothing logged")
for _ in range(5):
    state["mode"] = "parallel"; ns["_immediate_textures"](w)
assert state["mode"] == "immediate" and len(logged) == 3
print("ok: reset again and again: put back every time, logged three times at most")
blast = src[src.index("def _playblast"):src.index("def render(self, cam, chunk)")]
assert blast.index("self._immediate_textures()") < blast.index("cmds.playblast(")
print("ok: checked before every render")
