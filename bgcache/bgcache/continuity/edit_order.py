"""Shot order from the edit (0.9.0b4): neighbouring shots follow the cut,
not name order, when the profile's "edit_order" names an edit export:

    .edl                 CMX 3600 (clip names, "FROM CLIP NAME" comments,
                         reel names)
    .xml                 Final Cut Pro 7 / Premiere Pro XML (xmeml): the
                         video track's clip items, in timeline order
    .fcpxml              Final Cut Pro X: the spine's clips, in order

Shots are found in the clip names (and file names) with the profile's
shot_pattern, else any name shaped like the open shot. A shot cut in twice
keeps its first place. Shots missing from the edit come after, in name
order. Read again when the file changes. No Maya or Qt here.
"""
import os
import re
import xml.etree.ElementTree as ElementTree

_cache = {"key": None, "order": []}


def clip_names(path):
    """The edit's clip names in timeline order (empty if unreadable)."""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".edl":
            return _edl(path)
        root = ElementTree.parse(path).getroot()
    except (OSError, ElementTree.ParseError, UnicodeDecodeError) as error:
        print("bgcache: couldn't read the edit %s: %s" % (path, error))
        return []
    if root.tag == "fcpxml":
        return _fcpxml(root)
    return _xmeml(root)


def _edl(path):
    names = []
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            m = re.match(r"^\*\s*(FROM CLIP NAME|SOURCE FILE|LOC)\s*:\s*(.+)$", line, re.IGNORECASE)
            if m:
                names.append(m.group(2).strip())
                continue
            m = re.match(r"^\d{3,6}\s+(\S+)\s+(V|A|AA|B|A\d*)\b", line, re.IGNORECASE)
            if m and m.group(2).upper().startswith(("V", "B")):
                names.append(m.group(1))          # the reel name, often the shot
    return names


def _xmeml(root):
    out = []
    for track in root.iter("track"):
        if not _is_video(root, track):
            continue
        items = []
        for item in track.findall("clipitem"):
            start = item.findtext("start") or "0"
            text = [item.findtext("name") or ""]
            path = item.find("file/pathurl")
            if path is not None and path.text:
                text.append(path.text)
            items.append((int(start) if start.lstrip("-").isdigit() else 0, " ".join(text)))
        out.extend(name for _start, name in sorted(items, key=lambda x: x[0]))
    return out


def _is_video(root, track):
    for video in root.iter("video"):
        if track in list(video):
            return True
    return False


def _fcpxml(root):
    out = []
    for spine in root.iter("spine"):
        for clip in spine:
            if clip.tag in ("asset-clip", "clip", "ref-clip", "mc-clip", "sync-clip", "video"):
                out.append(clip.get("name") or "")
        break                                     # the main storyline only
    return out


def order(path, pattern):
    """Shot codes in cut order (as written in the edit), first cut first."""
    try:
        key = (path, os.path.getmtime(path), pattern)
    except OSError:
        return []
    if _cache["key"] == key:
        return _cache["order"]
    try:
        rx = re.compile(pattern)
    except re.error:
        return []
    found, seen = [], set()
    for name in clip_names(path):
        m = rx.search(os.path.basename(name.replace("\\", "/"))) or rx.search(name)
        if m and m.group("shot").lower() not in seen:
            seen.add(m.group("shot").lower())
            found.append(m.group("shot"))
    _cache.update(key=key, order=found)
    return found


def sort_shots(shots, path, pattern):
    """shots in the edit's order; shots not in the edit after, by name."""
    cut = {s.lower(): i for i, s in enumerate(order(path, pattern))}
    return sorted(shots, key=lambda s: (cut.get(s.lower(), len(cut)), s.lower()))
