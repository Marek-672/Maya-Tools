"""Which assets are drawn in the cache (0.9.0b20), the background Maya's
side: the environment groups are hidden here (never in your Maya), the
plug-in shapes your viewport shows are let through, and what the player's
Show selected / Remove selected asked for is applied. The rule: assets.py."""
import maya.cmds as cmds

from bgcache import assets


def log(text):
    from bgcache import worker
    worker.log(text)


def _children(node):
    return cmds.listRelatives(node, children=True, type="transform", fullPath=True) or []


class AssetsWorkerMixin(object):
    def _assets_spec(self):
        return self.cfg.get("cache_assets") or {}

    def _environment_groups(self):
        spec = self._assets_spec()
        if not spec.get("root"):
            return []
        try:
            roots = cmds.ls(spec["root"], long=True, type="transform") or []
        except Exception as error:
            log("assets: %s" % error)
            return []
        return assets.environment_groups(roots, spec.get("environment") or [], cmds.objExists)

    def assets_by_group(self):
        """True when this scene has the profile's environment groups: the
        cache then draws what you see, minus those groups (and not, as
        without them, no plug-in shapes of the environment kinds at all)."""
        return bool(getattr(self, "_env_groups", None))

    def apply_assets(self):
        """Hide the environment (but what's to be shown) and what was removed;
        un-hide what an earlier call hid and this one doesn't."""
        spec = self._assets_spec()
        self._env_groups = self._environment_groups()
        hidden = getattr(self, "_cache_hidden", set())
        want = set(assets.to_hide(self._env_groups, spec.get("shown") or [], spec.get("removed") or [],
                                  _children, cmds.objExists))
        seen = getattr(self, "user_vis", {})
        for node in sorted(hidden - want):
            self._set_visible(node, seen.get(node, True))
        failed = [n for n in sorted(want) if not self._set_visible(n, False)]
        self._cache_hidden = want
        if self._env_groups or want or hidden:
            log("assets in the cache: what you see, without %s%s%s%s" % (
                ", ".join(g.split("|")[-1] for g in self._env_groups) or "no environment groups (none in this scene)",
                "; shown anyway: %s" % ", ".join(s.split("|")[-1] for s in spec["shown"]) if spec.get("shown") else "",
                "; removed: %s" % ", ".join(s.split("|")[-1] for s in spec["removed"]) if spec.get("removed") else "",
                "; COULD NOT HIDE: %s" % ", ".join(f.split("|")[-1] for f in failed) if failed else ""))

    def _set_visible(self, node, on):
        plug = node + ".visibility"
        try:
            if not cmds.objExists(plug):
                return True
            if cmds.getAttr(plug, lock=True):
                cmds.setAttr(plug, lock=False)
            for src in cmds.listConnections(plug, source=True, destination=False, plugs=True) or []:
                cmds.disconnectAttr(src, plug)          # here only: this is the background copy
            cmds.setAttr(plug, bool(on))
            return True
        except Exception as error:
            log("assets: %s not %s (%s)" % (node.split("|")[-1], "shown" if on else "hidden", error))
            return False

    def note_visibility(self, plug, value):
        """An unkeyed value from your Maya is about to be set. False if it's
        the visibility of something the cache hides: remembered for when it
        isn't hidden any more, and not set."""
        if not plug.endswith(".visibility"):
            return True
        node = plug[:-len(".visibility")]
        if not hasattr(self, "user_vis"):
            self.user_vis = {}
        self.user_vis[node] = bool(value)
        return node not in getattr(self, "_cache_hidden", ())
