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
        self._vis_watch = {}
        try:
            self._note_selected(selected_transforms())      # what's selected as you start
        except Exception as error:
            scene._ignored(error)
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

    WATCHED_MAX = 400              # the most selected things whose show / hide is followed

    def _note_selected(self, nodes):
        """From the selection: Ctrl+H and Shift+H act on what's selected, so
        the things you select are the ones whose show / hide is looked at
        (b24). Full paths of transforms; the oldest drop off."""
        watch = getattr(self, "_vis_watch", None)
        if watch is None:
            watch = self._vis_watch = {}
        for node in nodes:
            watch.pop(node, None)
            watch[node] = True              # newest last
        for node in list(watch)[:max(0, len(watch) - self.WATCHED_MAX)]:
            del watch[node]

    def _selected_changes(self):
        """Things you selected and then showed or hid (compared with what the
        background Maya was last given: vis_base)."""
        out = []
        for node in list(getattr(self, "_vis_watch", None) or ()):
            before = self.vis_base.get(node)
            if before is None:
                continue                      # new since Start: that's for Reload scene
            plug = node + ".visibility"
            try:
                if not cmds.objExists(node):
                    del self._vis_watch[node]
                    continue
                if cmds.listConnections(plug, source=True, destination=False):
                    continue                  # keyed or driven: the curves carry it
                value = bool(cmds.getAttr(plug))
            except Exception as error:
                scene._ignored(error)
                continue
            if value != before:
                out.append([plug, value])
        return out

    def _layer_changes(self):
        """Display layers you switched (visibility, template / reference, playback)."""
        sent = getattr(self, "_refresh_sent", None)
        if sent is None:
            return []
        try:
            return [v for v in scene.display_layer_values() if v[0] in sent and sent[v[0]] != v[1]]
        except Exception as error:
            scene._ignored(error)
            return []

    def _send_anim_layers(self):
        """b25: an animation layer you muted, soloed, or changed the weight or
        mode of (layers the background Maya has: a new one needs Reload scene)."""
        sent = getattr(self, "_refresh_sent", None)
        if sent is None or "_anim_layers" not in sent:
            return
        before = sent["_anim_layers"]
        try:
            now = scene.anim_layer_values()
        except Exception as error:
            scene._ignored(error)
            return
        changed = dict((layer, vals) for layer, vals in now.items() if layer in before and before[layer] != vals)
        if not changed:
            return
        before.update(changed)
        self.trace("anim-layers", "%d" % len(changed))
        common.post_message(self.session, {"op": "anim_layers", "layers": changed,
                                           "ranges": [[self.cfg["start"], self.cfg["end"]]]})
        said = "From your Maya: animation layer %s (mute, solo or weight). Re-rendering." % ", ".join(sorted(changed)[:3])
        self._tell_player(said)
        print("bgcache: " + said)

    def _send_shown_hidden(self):
        """From the 150 ms poll, once a second: what you've shown or hidden
        since the last look is sent, and the shot re-renders. Looked at: the
        asset groups (b20), anything you selected (Ctrl+H, Shift+H) and the
        display layers (b24)."""
        if not self.running:
            return
        now = time.time()
        if now - getattr(self, "_asset_checked", 0) < self.ASSETS_CHECK_S or scene._mouse_held():
            return
        self._asset_checked = now
        self._send_anim_layers()
        changed = []
        if getattr(self, "_asset_nodes", None):
            states = self._asset_states()
            changed = [[plug, value] for plug, value in states.items() if self._asset_seen.get(plug) != value]
            self._asset_seen = states
        have = set(plug for plug, _ in changed)
        changed += [v for v in self._selected_changes() if v[0] not in have]
        layers = self._layer_changes()
        if not changed and not layers:
            return
        for plug, value in changed:
            self.vis_base[plug[:-len(".visibility")]] = value      # Refresh won't send it again
        for plug, value in layers:
            self._refresh_sent[plug] = value
        self.trace("shown-hidden", "%d objects, %d layer settings" % (len(changed), len(layers)))
        common.post_message(self.session, {"op": "statics", "values": changed + layers,
                                           "ranges": [[self.cfg["start"], self.cfg["end"]]]})
        said = " and ".join(t for t in (
            "%d object%s shown or hidden" % (len(changed), "" if len(changed) == 1 else "s") if changed else "",
            "%d layer setting%s" % (len(layers), "" if len(layers) == 1 else "s") if layers else "") if t)
        self._tell_player("From your Maya: %s. Re-rendering." % said)
        print("bgcache: %s in your Maya: sent, re-rendering" % said)

    def cache_selected(self, show):
        """The player's Show and Hide buttons: what's selected in your Maya."""
        self.trace("cache-selected", "show" if show else "hide")
        if not self.running:
            return
        nodes = selected_transforms()
        if not nodes:
            self._tell_player("Select something in your Maya first, then press %s" % ("Show selected" if show else "Hide selected"))
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
