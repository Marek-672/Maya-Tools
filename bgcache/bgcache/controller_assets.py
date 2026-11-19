"""Which assets are in the cache (0.9.0b20), your Maya's side: what you show
or hide is followed without Refresh, and the player's Show selected / Remove
selected in the cache. The rule itself is in assets.py."""
import time

import maya.cmds as cmds

from bgcache import assets, common, profile, scene


def _children(node):
    return cmds.listRelatives(node, children=True, type="transform", fullPath=True) or []


def selected_transforms():
    """Full paths of the selected transforms (a selected shape: its parent)."""
    out = []
    for node in cmds.ls(selection=True, long=True) or []:
        try:
            if not cmds.objectType(node, isAType="transform"):
                node = (cmds.listRelatives(node, parent=True, fullPath=True) or [None])[0]
        except Exception as error:
            scene._ignored(error)
            node = None
        if node and node not in out:
            out.append(node)
    return out


class AssetsMixin(object):
    ASSETS_CHECK_S = 1.0           # how often your show / hide of assets is looked at

    def assets_config(self):
        """For the session: the profile's cache_assets. What you Show and
        Hide in the player is for the working session only (b22, Marek):
        Stop forgets it, and the next Start shows the shot as it is. Restart
        carries it over (it's the same working session)."""
        root, groups = assets.settings(profile.get("cache_assets"))
        carried, self._carry_assets = getattr(self, "_carry_assets", None) or {}, None
        return {"root": root, "environment": groups,
                "shown": list(carried.get("shown") or []), "removed": list(carried.get("removed") or [])}

    def _write_cache_lists(self):
        """For the player's Show and Hide lists."""
        spec = self.cfg.get("cache_assets") or {}
        try:
            common.write_json_atomic(common.paths(self.session)["cache_lists"], {
                "shown": list(spec.get("shown") or []), "hidden": list(spec.get("removed") or []), "ts": time.time()})
        except (IOError, OSError) as error:
            scene._ignored(error)

    def _asset_roots(self):
        root = (self.cfg.get("cache_assets") or {}).get("root")
        if not root:
            return []
        try:
            return [n for n in cmds.ls(root, long=True, type="transform") or []]
        except Exception as error:
            scene._ignored(error)
            return []

    def _watch_assets(self):
        """Start (and Reload scene): note how the watched assets are shown now."""
        spec = self.cfg.get("cache_assets") or {}
        self._write_cache_lists()
        roots = self._asset_roots()
        self._asset_nodes, self._asset_seen, self._asset_checked = [], {}, time.time()
        if not roots:
            return                           # no asset groups in this scene: nothing to follow
        try:
            env = assets.environment_groups(roots, spec.get("environment") or [], cmds.objExists)
            self._asset_nodes = assets.watched(roots, env, _children)
            self._asset_seen = self._asset_states()
        except Exception as error:
            scene._ignored(error)
        if self._asset_nodes:
            self.trace("assets-watched", len(self._asset_nodes))

    def _asset_states(self):
        out = {}
        for node in getattr(self, "_asset_nodes", []):
            plug = node + ".visibility"
            try:
                if cmds.listConnections(plug, source=True, destination=False):
                    continue                  # keyed or driven: the curves carry it
                out[plug] = bool(cmds.getAttr(plug))
            except Exception as error:
                scene._ignored(error)
        return out

    def _send_shown_hidden(self):
        """From the 150 ms poll, once a second: assets you've shown or hidden
        since the last look are sent, and the shot re-renders."""
        if not getattr(self, "_asset_nodes", None) or not self.running:
            return
        now = time.time()
        if now - getattr(self, "_asset_checked", 0) < self.ASSETS_CHECK_S or scene._mouse_held():
            return
        self._asset_checked = now
        states = self._asset_states()
        changed = [[plug, value] for plug, value in states.items() if self._asset_seen.get(plug) != value]
        self._asset_seen = states
        if not changed:
            return
        for plug, value in changed:
            self.vis_base[plug[:-len(".visibility")]] = value      # Refresh won't send it again
        self.trace("assets-shown-hidden", "%d" % len(changed))
        common.post_message(self.session, {"op": "statics", "values": changed,
                                           "ranges": [[self.cfg["start"], self.cfg["end"]]]})
        print("bgcache: %d asset(s) shown or hidden in your Maya: sent, re-rendering" % len(changed))

    def cache_selected(self, show):
        """The player's Show and Hide buttons: what's selected in your Maya."""
        self.trace("cache-selected", "show" if show else "hide")
        if not self.running:
            return
        nodes = selected_transforms()
        if not nodes:
            self._tell_player("Select something in your Maya first, then press %s" % ("Show" if show else "Hide"))
            return
        spec = self.cfg.get("cache_assets") or {}
        shown, removed = (assets.show if show else assets.remove)(spec.get("shown") or [], spec.get("removed") or [], nodes)
        self._set_cache_lists(shown, removed)
        self._tell_player("%s in the player: %s" % ("Shown" if show else "Hidden",
                                                    ", ".join(assets.label(n) for n in nodes[:4])
                                                    + (" and %d more" % (len(nodes) - 4) if len(nodes) > 4 else "")))

    def cache_forget(self, nodes=None):
        """A name clicked in the player's Shown or Hidden list (None: all of
        them): it goes back to how your Maya has it."""
        self.trace("cache-forget", "all" if nodes is None else "%d" % len(nodes))
        if not self.running:
            return
        spec = self.cfg.get("cache_assets") or {}
        shown, removed = assets.forget(spec.get("shown") or [], spec.get("removed") or [], nodes)
        self._set_cache_lists(shown, removed)
        self._tell_player("Back to how your Maya has it: %s" % (
            "everything" if nodes is None else ", ".join(assets.label(n) for n in nodes[:4])))

    def _set_cache_lists(self, shown, removed):
        spec = dict(self.cfg.get("cache_assets") or {})
        spec["shown"], spec["removed"] = shown, removed
        self.cfg["cache_assets"] = spec
        common.write_json_atomic(common.paths(self.session)["config"], self.cfg)
        self._write_cache_lists()
        common.post_message(self.session, {"op": "assets", "shown": shown, "removed": removed,
                                           "ranges": [[self.cfg["start"], self.cfg["end"]]]})
