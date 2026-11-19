"""0.9.0b22: Show and Hide on the player's bar, each with a list of what it
holds; for the working session only."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from bgcache import assets, common

src = lambda name: open(os.path.join(os.path.dirname(HERE), "bgcache", name)).read()

shown, hidden = ["|Assets|environ|shop"], ["|Assets|char|bob", "|Assets|prop|cup"]
assert assets.forget(shown, hidden, ["|Assets|char|bob"]) == (shown, ["|Assets|prop|cup"])
assert assets.forget(shown, hidden, ["|Assets|environ|shop"]) == ([], hidden)
assert assets.forget(shown, hidden) == ([], [])
assert assets.forget(shown, hidden, ["|not|there"]) == (shown, hidden)
assert assets.label("|Assets|char|bob") == "bob"
print("ok: a name clicked in a list goes back to how Maya has it; Put all back empties the lists")

c = src("controller_assets.py")
assert "load_prefs" not in c and "save_prefs" not in c
print("ok: what you Show and Hide is never written to the preferences: Stop forgets it")
assert "_carry_assets" in c and "_carry_assets" in src("controller.py")
print("ok: Restart carries the lists over (the same working session)")
assert "cache_lists" in common.paths("x") and "_write_cache_lists" in c
assert 'cmd == "cache_forget"' in src("controller_sync.py")

p, s = src("player.py"), src("player_session.py")
assert '_tool("Show selected"' in p and '_tool("Hide selected"' in p and "Hidden in the player" in p and "Shown in the player" in p
assert '"Show selected in the cache"' not in p and '"Remove selected from the cache"' not in p
assert "_list_arrow.setVisible(bool(count))" in s and "self._check_cache_lists()" in s
print("ok: Show and Hide are on the bar; the arrow and its list appear only when a button is holding something")
