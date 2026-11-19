"""One Refresh (0.9.0b21): the words and the comparisons, no Maya here.

Refresh is the one thing you press when the player doesn't match your Maya.
It sends what it can cheaply (viewport, layers, shown and hidden, unkeyed
values on what you've selected, image planes), says what it did, and, if the
scene itself has changed (references, constraints, objects), asks whether to
reload it. Maya also tells bgcache when a reference comes or goes: the player
then says so next to Refresh, and does nothing by itself.
"""


def plural(n, one, many=None):
    return "%d %s" % (n, one if n == 1 else (many or one + "s"))


def structure_changes(old, new):
    """What differs between two scene structures (see controller_scene.structure),
    as short phrases: [] when the background Maya's copy is still good."""
    if not old or not new:
        return []
    out = []
    a, b = old.get("references") or {}, new.get("references") or {}
    added, removed = [r for r in b if r not in a], [r for r in a if r not in b]
    swapped = [r for r in b if r in a and b[r][0] != a[r][0]]
    loaded = [r for r in b if r in a and b[r][1] and not a[r][1]]
    unloaded = [r for r in b if r in a and a[r][1] and not b[r][1]]
    for names, what in ((added, "added"), (removed, "removed"), (swapped, "replaced"),
                        (loaded, "loaded"), (unloaded, "unloaded")):
        if names:
            out.append("%s %s" % (plural(len(names), "reference"), what))
    for key, one, many in (("constraints", "constraint", None), ("deformers", "deformer", None),
                           ("objects", "object", None)):
        diff = int(new.get(key) or 0) - int(old.get(key) or 0)
        if diff:
            out.append("%s %s" % (plural(abs(diff), one, many), "added" if diff > 0 else "removed"))
    return out


def summary(viewport=(), layers=0, shown_hidden=0, values=0, controls=0, planes=0, gpu=False):
    """What a Refresh sent, for the player: one line."""
    parts = []
    if viewport:
        parts.append("viewport settings")
    if layers:
        parts.append(plural(layers, "layer setting"))
    if shown_hidden:
        parts.append("%s shown or hidden" % plural(shown_hidden, "object"))
    if values:
        parts.append("%s on %s" % (plural(values, "unkeyed value"), plural(controls, "control")))
    if planes:
        parts.append(plural(planes, "image plane"))
    if gpu:
        parts.append("GPU setting")
    if not parts:
        return ""
    return "Refreshed: %s. Re-rendering." % ", ".join(parts)


NOTHING = "Nothing to update that Refresh can see. Still wrong? bgcache menu > Reload scene."

EVENTS = {
    "reference-added": "a reference was added", "reference-removed": "a reference was removed",
    "reference-loaded": "a reference was loaded", "reference-unloaded": "a reference was unloaded",
    "imported": "something was imported", "constraint": "a constraint was made",
}


def note(events):
    """The orange words next to Refresh, from what Maya reported since the last reload."""
    events = [e for e in events if e in EVENTS]
    if not events:
        return ""
    first = EVENTS[events[-1]]
    more = len(set(events)) - 1
    return "Scene changed: %s%s" % (first, " (and more)" if more > 0 else "")


def question(changes, seconds=None):
    """(title, text) of the bar that asks whether to reload."""
    took = ""
    if seconds:
        took = ", which took %s last time" % ("%d seconds" % seconds if seconds < 90
                                              else "about %d minutes" % round(seconds / 60.0))
    return ("Your scene has changed since the cache was made",
            "%s. To show that, the player has to reload the scene%s. Everything else from this Refresh "
            "has been sent." % (", ".join(changes).capitalize(), took))
