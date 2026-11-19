"""Which assets are drawn in the cache (0.9.0b20). No Maya here: names in,
names out, so it can be tested anywhere.

The rule (Marek, 2026-11-18): what you can see in your Maya is in the cache,
except the environment. A studio's pipeline profile says where the
environment is:

    "cache_assets": {"root": "Assets", "environment": ["environ", "digimatte", "dressing"]}

i.e. the groups directly under a group called Assets that are never drawn.
Two lists change that for single things: `shown` (drawn although they're in
the environment: "Show selected in the cache") and `removed` (not drawn
although you see them: "Remove selected from the cache").

Names are Maya's full paths (|Assets|environ|setA).
"""


def settings(spec):
    """(root name, [environment group names]) from the profile's cache_assets; ("", []) if unset."""
    spec = spec if isinstance(spec, dict) else {}
    root = str(spec.get("root") or "").strip("|")
    groups = [str(g).strip("|") for g in (spec.get("environment") or []) if str(g).strip("|")]
    return (root, groups) if root and groups else ("", [])


def inside(node, branch):
    """True if node is branch or under it."""
    return node == branch or node.startswith(branch + "|")


def environment_groups(roots, groups, exists):
    """Full paths of the environment groups that are in the scene. roots: the
    full paths of every group with the root's name."""
    out = []
    for root in roots:
        for name in groups:
            path = "%s|%s" % (root, name)
            if exists(path) and path not in out:
                out.append(path)
    return out


def to_hide(env_groups, shown, removed, children, exists):
    """The nodes to hide in the background Maya, as few as possible: an
    environment group in one go, or, when something inside it is to be shown,
    everything beside the way down to that thing. children(node): its child
    transforms (full paths)."""
    shown = [s for s in shown if exists(s)]
    out = []

    def walk(node):
        wanted = [s for s in shown if inside(s, node)]
        if not wanted:
            out.append(node)            # nothing to show in here: hidden at the top
        elif node in wanted:
            return                      # shown, with everything under it
        else:
            for child in children(node):
                walk(child)

    for group in env_groups:
        walk(group)
    for node in removed:
        if exists(node) and not any(inside(node, h) for h in out):
            out.append(node)
    return out


def show(shown, removed, nodes):
    """Show selected in the cache: (shown, removed) after it. Something that
    was removed is simply back; something in the environment is added to shown."""
    nodes = [n for n in nodes if n]
    removed = [r for r in removed if not any(inside(r, n) or inside(n, r) for n in nodes)]
    shown = [s for s in shown if not any(inside(s, n) for n in nodes)]
    return shown + [n for n in nodes if n not in shown], removed


def remove(shown, removed, nodes):
    """Remove selected from the cache: (shown, removed) after it."""
    nodes = [n for n in nodes if n]
    shown = [s for s in shown if not any(inside(s, n) for n in nodes)]
    removed = [r for r in removed if not any(inside(r, n) for n in nodes)]
    return shown, removed + [n for n in nodes if n not in removed]


def watched(roots, env_groups, children, depth=3):
    """The transforms whose show / hide is followed without Refresh: the
    asset groups and what's just under them (not inside the environment, not
    deep inside rigs)."""
    out = []

    def walk(node, level):
        if any(inside(node, e) for e in env_groups):
            return
        out.append(node)
        if level < depth:
            for child in children(node):
                walk(child, level + 1)

    for root in roots:
        walk(root, 0)
    return out
