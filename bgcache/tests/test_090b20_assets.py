"""0.9.0b20: what's drawn in the cache: what you see in your Maya, without the
environment groups; Show selected / Remove selected in the cache."""
import os, sys
TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(TESTS))
from bgcache import assets

tree = {"|Assets": ["|Assets|character", "|Assets|prop", "|Assets|environ", "|Assets|dressing", "|Assets|vehicle"],
        "|Assets|character": ["|Assets|character|hero"], "|Assets|character|hero": ["|Assets|character|hero|rig"],
        "|Assets|character|hero|rig": ["|Assets|character|hero|rig|deep"],
        "|Assets|prop": ["|Assets|prop|cup", "|Assets|prop|chair"],
        "|Assets|environ": ["|Assets|environ|street", "|Assets|environ|shop"],
        "|Assets|environ|shop": ["|Assets|environ|shop|counter", "|Assets|environ|shop|walls"],
        "|Assets|dressing": ["|Assets|dressing|signs"]}
nodes = set(tree) | {c for kids in tree.values() for c in kids}
children = lambda n: tree.get(n, [])
exists = lambda n: n in nodes

assert assets.settings({"root": "Assets", "environment": ["environ", "digimatte", "dressing"]}) == ("Assets", ["environ", "digimatte", "dressing"])
assert assets.settings({}) == assets.settings(None) == assets.settings({"root": "Assets"}) == ("", [])
env = assets.environment_groups(["|Assets"], ["environ", "digimatte", "dressing"], exists)
assert env == ["|Assets|environ", "|Assets|dressing"]
print("ok: the profile names the environment groups; only the ones in the scene count (no digimatte here)")

assert assets.to_hide(env, [], [], children, exists) == ["|Assets|environ", "|Assets|dressing"]
print("ok: nothing chosen: each environment group is hidden in one go; props, vehicles, characters are left as you see them")

hide = assets.to_hide(env, ["|Assets|environ|shop|counter"], [], children, exists)
assert hide == ["|Assets|environ|street", "|Assets|environ|shop|walls", "|Assets|dressing"]
print("ok: Show selected (the shop's counter): only what's beside the way down to it is hidden")

shown, removed = assets.show([], [], ["|Assets|environ|shop"])
shown, removed = assets.remove(shown, removed, ["|Assets|prop|chair"])
assert (shown, removed) == (["|Assets|environ|shop"], ["|Assets|prop|chair"])
assert assets.to_hide(env, shown, removed, children, exists) == ["|Assets|environ|street", "|Assets|dressing", "|Assets|prop|chair"]
print("ok: Remove selected (a chair you can see in Maya) leaves it out of the cache")
shown, removed = assets.show(shown, removed, ["|Assets|prop|chair"])
assert removed == [] and shown == ["|Assets|environ|shop", "|Assets|prop|chair"]
shown, removed = assets.remove(shown, removed, ["|Assets|environ|shop"])
assert shown == ["|Assets|prop|chair"] and removed == ["|Assets|environ|shop"]
assert assets.to_hide(env, shown, removed, children, exists) == ["|Assets|environ", "|Assets|dressing"]
print("ok: Show brings a removed thing back; Remove takes a shown piece of the environment out again")
assert assets.to_hide(env, ["|Assets|environ|gone"], ["|Assets|prop|gone"], children, exists) == ["|Assets|environ", "|Assets|dressing"]
print("ok: something that's no longer in the scene changes nothing")

watched = assets.watched(["|Assets"], env, children)
assert "|Assets|prop|cup" in watched and "|Assets|character|hero|rig" in watched and "|Assets|vehicle" in watched
assert "|Assets|character|hero|rig|deep" not in watched and not any(w.startswith("|Assets|environ") for w in watched)
print("ok: show / hide is followed on the asset groups and just under them: not deep inside rigs, not in the environment")

src = lambda name: open(os.path.join(os.path.dirname(TESTS), "bgcache", name)).read()
w, c, p = src("worker.py"), src("controller_sync.py"), src("player.py")
assert "self.apply_assets()" in w and 'op == "assets"' in w and "self.note_visibility(plug, value)" in w
assert "bool(seen.get(name)) if by_group else shown" in w
assert "self._send_shown_hidden()" in c and '"cache_show_selected", "cache_remove_selected"' in c
assert '"Show selected in the cache"' in p and '"Remove selected from the cache"' in p
print("ok: wired: the background Maya hides the groups and lets your viewport's plug-in shapes through; your Maya "
      "follows show / hide; the player has Show selected in the cache and Remove selected from the cache")
