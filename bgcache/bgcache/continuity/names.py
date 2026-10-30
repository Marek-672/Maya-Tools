"""Reading footage names (0.9.0b4): what counts as a movie or an image
sequence, and the version in a name, however it's written.

A department's version_pattern is a name with * where the version goes:
    "P_{shot}_anim_v*"   -> P_sq010_0040_anim_v012     (version 12)
    "v*"                 -> v004                      (a version folder)
    "{shot}_take*"       -> sh010_take3.mov           (take 3)
    "{shot}_anim_*"      -> sh010_anim_003.mp4        (3)
    "*"                  -> 2026-10-28                (a date: 20261028)
The version is the digits in the last * that has any. A pattern without *
names one file or folder (no versions: the newest one wins). Matching
ignores upper and lower case, so SH010 and sh010 are the same shot.
No Maya, Qt or ffmpeg here.
"""
import os
import re

MOVIE_EXTS = (".mov", ".mp4", ".m4v")
IMAGE_EXTS = ("jpg", "jpeg", "png", "tif", "tiff", "exr", "dpx")
FRAME_RE = re.compile(r"\.(\d+)\.(%s)$" % "|".join(IMAGE_EXTS), re.IGNORECASE)
_patterns = {}


def is_movie(name):
    return name.lower().endswith(MOVIE_EXTS)


def is_frame(name):
    return bool(FRAME_RE.search(name))


def footage_stem(name):
    """(stem, kind) of a footage file: shot_v004.mov -> ("shot_v004",
    "single_movie"); shot_v004.1001.jpg -> ("shot_v004", "image_sequence");
    anything else -> (None, None)."""
    m = FRAME_RE.search(name)
    if m:
        return name[:m.start()], "image_sequence"
    stem, ext = os.path.splitext(name)
    if ext.lower() in MOVIE_EXTS:
        return stem, "single_movie"
    return None, None


def pattern_regex(pattern):
    """A version_pattern as a regex: each * a group (the last one greedy)."""
    rx = _patterns.get(pattern)
    if rx is None:
        pieces = pattern.split("*")
        body = ""
        for i, piece in enumerate(pieces):
            body += re.escape(piece)
            if i < len(pieces) - 1:
                body += "(.*)" if i == len(pieces) - 2 else "(.*?)"
        rx = _patterns[pattern] = re.compile("^%s$" % body, re.IGNORECASE)
    return rx


def matches(name, pattern):
    return bool(pattern_regex(pattern).match(name))


def version_in(name, pattern):
    """The version number in a name matching pattern, or None (no match, or
    no digits where the * is)."""
    m = pattern_regex(pattern).match(name)
    if not m:
        return None
    for group in reversed(m.groups()):
        digits = "".join(re.findall(r"\d+", group or ""))
        if digits:
            return int(digits)
    return None
