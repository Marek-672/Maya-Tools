"""0.9.0b4: the setup wizard's learning core on made-up production layouts.

Each case builds a folder tree, learns from one example movie (and the open
scene), checks what was read, then saves the learned profile and asks the
player's own lookup for a neighbouring shot's newest footage: the real test
that the settings work. Every real failure from a report becomes a case."""
import json
import os
import shutil
import sys
import tempfile
import time

TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
sys.path.insert(0, REPO)
ROOT = os.path.realpath(tempfile.mkdtemp())
PROFILE = os.path.join(ROOT, "profile.json")
os.environ["BGCACHE_PROFILE"] = PROFILE

from bgcache import profile                                  # noqa: E402
from bgcache.continuity import learn, names, resolver        # noqa: E402


def build(case, files):
    base = os.path.join(ROOT, case)
    for i, rel in enumerate(files):
        path = os.path.join(base, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            open(path, "w").close()
            t = time.time() - 1000 + i                 # later in the list = newer
            os.utime(path, (t, t))
    return learn.norm(base)


def apply(lay):
    with open(PROFILE, "w") as handle:
        json.dump(learn.to_profile(lay), handle)
    profile.load(force=True)
    profile._context.clear()


def resolve(shot, dept=None):
    seq = profile.sequence_of(shot) or ""
    info = resolver.resolve_shot("", shot, dept)
    return learn.norm(info["source_path"]) if info else None


CASES = []


def case(name, files, movie, scene=None, shot=None, sequence=None, depts=None, shots=None,
         resolves=None, known=None, problem=None):
    CASES.append(dict(name=name, files=files, movie=movie, scene=scene, shot=shot, sequence=sequence,
                      depts=depts, shots=shots, resolves=resolves or {}, known=known, problem=problem))


# 1. a studio tree: show / sequence / shot / department / version folder
case("studio", [
    "BIRDS/sq010/sq010_0040/anim/maya/scenes/sq010_0040_anim_v031.ma",
    "BIRDS/sq010/sq010_0040/lighting/v003/sq010_0040_light_v003.mov",
    "BIRDS/sq010/sq010_0040/lighting/v004/sq010_0040_light_v004.mov",
    "BIRDS/sq010/sq010_0040/playblast/v012/sq010_0040_pb_v012.mov",
    "BIRDS/sq010/sq010_0030/lighting/v002/sq010_0030_light_v002.mov",
    "BIRDS/sq010/sq010_0030/lighting/v007/sq010_0030_light_v007.mov",
    "BIRDS/sq010/sq010_0050/playblast/v001/sq010_0050_pb_v001.mov"],
    movie="BIRDS/sq010/sq010_0040/lighting/v004/sq010_0040_light_v004.mov",
    scene="BIRDS/sq010/sq010_0040/anim/maya/scenes/sq010_0040_anim_v031.ma",
    shot="sq010_0040", sequence="sq010", depts=["lighting", "playblast"],
    shots=["sq010_0030", "sq010_0040", "sq010_0050"],
    resolves={("sq010_0030", "lighting"): "sq010_0030_light_v007.mov",
              ("sq010_0050", "playblast"): "sq010_0050_pb_v001.mov"})

# 1b. the same tree with the scene saved outside the shot folders
case("studio_scene_elsewhere", [
    "BIRDS/scenes/sq010_0040_anim_v031.ma",
    "BIRDS/sq010/sq010_0040/lighting/v004/sq010_0040_light_v004.mov",
    "BIRDS/sq010/sq010_0030/lighting/v007/sq010_0030_light_v007.mov"],
    movie="BIRDS/sq010/sq010_0040/lighting/v004/sq010_0040_light_v004.mov",
    scene="BIRDS/scenes/sq010_0040_anim_v031.ma", shot="sq010_0040", sequence="sq010",
    shots=["sq010_0030", "sq010_0040"],
    resolves={("sq010_0030", "lighting"): "sq010_0030_light_v007.mov"})

# 2. version folders named with the shot, no sequence folder
case("named_version_folders", [
    "SHOW/m0120_0300/maya/scenes/m0120_0300_anim_v010.mb",
    "SHOW/m0120_0300/P/P_m0120_0300_anim_v011/m0120_0300.mov",
    "SHOW/m0120_0300/P/P_m0120_0300_anim_v012/m0120_0300.mov",
    "SHOW/m0120_0290/P/P_m0120_0290_anim_v003/m0120_0290.mov"],
    movie="SHOW/m0120_0300/P/P_m0120_0300_anim_v012/m0120_0300.mov",
    scene="SHOW/m0120_0300/maya/scenes/m0120_0300_anim_v010.mb",
    shot="m0120_0300", depts=["P"], shots=["m0120_0290", "m0120_0300"],
    resolves={("m0120_0290", "P"): "P_m0120_0290_anim_v003/m0120_0290.mov"})

# 3. versions in file names, side by side, inside shot folders
case("names_in_shot_folder", [
    "film/shots/sh010/scenes/sh010_anim.ma",
    "film/shots/sh010/anim/sh010_anim_v002.mov",
    "film/shots/sh010/anim/sh010_anim_v003.mov",
    "film/shots/sh020/anim/sh020_anim_v001.mov",
    "film/shots/sh020/anim/sh020_anim_v004.mov"],
    movie="film/shots/sh010/anim/sh010_anim_v003.mov", scene="film/shots/sh010/scenes/sh010_anim.ma",
    shot="sh010", depts=["anim"], shots=["sh010", "sh020"],
    resolves={("sh020", "anim"): "sh020_anim_v004.mov"})

# 4. one folder of playblasts for the whole film; scenes elsewhere
case("one_folder", [
    "film/scenes/sh010.ma",
    "film/playblasts/sh010_v01.mp4", "film/playblasts/sh010_v02.mp4",
    "film/playblasts/sh020_v01.mp4", "film/playblasts/sh030_v05.mp4"],
    movie="film/playblasts/sh010_v02.mp4", scene="film/scenes/sh010.ma",
    shot="sh010", depts=["playblasts"], shots=["sh010", "sh020", "sh030"],
    resolves={("sh030", "playblasts"): "sh030_v05.mp4", ("sh010", "playblasts"): "sh010_v02.mp4"})

# 5. editorial exports per sequence folder, sequence inside the shot code
case("editorial", [
    "film/edit/exports/sq01/sq01_sh010_v002.mov", "film/edit/exports/sq01/sq01_sh020_v001.mov",
    "film/edit/exports/sq01/sq01_sh020_v003.mov", "film/edit/exports/sq02/sq02_sh010_v001.mov",
    "film/anim/sq01_sh020_anim.ma"],
    movie="film/edit/exports/sq01/sq01_sh020_v003.mov", scene="film/anim/sq01_sh020_anim.ma",
    shot="sq01_sh020", sequence="sq01", shots=["sq01_sh010", "sq01_sh020"],
    resolves={("sq01_sh010", None): "sq01_sh010_v002.mov"})

# 6. image sequences in version folders with a resolution folder
case("frames_in_versions", [
    "p/seq/sh010/comp/v002/1920x1080/sh010_comp_v002.1001.exr",
    "p/seq/sh010/comp/v003/1920x1080/sh010_comp_v003.1001.exr",
    "p/seq/sh010/comp/v003/1920x1080/sh010_comp_v003.1002.exr",
    "p/seq/sh020/comp/v001/1920x1080/sh020_comp_v001.1001.exr",
    "p/seq/sh010/anim/sh010.ma"],
    movie="p/seq/sh010/comp/v003/1920x1080/sh010_comp_v003.1001.exr", scene="p/seq/sh010/anim/sh010.ma",
    shot="sh010", depts=["comp"], shots=["sh010", "sh020"],
    resolves={("sh020", "comp"): "sh020_comp_v001.1001.exr"})

# 7. image sequences with the version in the name, all in one folder per shot
case("frames_in_names", [
    "p/sh010/render/sh010_lgt_v001.0001.jpg", "p/sh010/render/sh010_lgt_v002.0001.jpg",
    "p/sh010/render/sh010_lgt_v002.0002.jpg", "p/sh020/render/sh020_lgt_v001.0001.jpg"],
    movie="p/sh010/render/sh010_lgt_v002.0001.jpg", shot="sh010", depts=["render"],
    shots=["sh010", "sh020"], resolves={("sh020", "render"): "sh020_lgt_v001.0001.jpg"})

# 8. takes
case("takes", ["f/shots/sh010/sh010_take2.mov", "f/shots/sh010/sh010_take3.mov",
               "f/shots/sh020/sh020_take1.mov"],
     movie="f/shots/sh010/sh010_take3.mov", shot="sh010", shots=["sh010", "sh020"],
     resolves={("sh020", None): "sh020_take1.mov"})

# 9. plain numbers after the department
case("plain_numbers", ["f/sh010/anim/sh010_anim_003.mov", "f/sh010/anim/sh010_anim_004.mov",
                       "f/sh020/anim/sh020_anim_001.mov"],
     movie="f/sh010/anim/sh010_anim_004.mov", shot="sh010", depts=["anim"],
     resolves={("sh020", "anim"): "sh020_anim_001.mov"})

# 10. no version at all: one movie per shot
case("no_version", ["f/shots/sh010/sh010.mov", "f/shots/sh020/sh020.mov", "f/shots/sh030/sh030.mp4"],
     movie="f/shots/sh010/sh010.mov", shot="sh010", shots=["sh010", "sh020", "sh030"],
     resolves={("sh020", None): "sh020.mov"})

# 11. Windows-style example path (backslashes)
case("windows_path", ["FILM/shots/sh010/anim/v001/sh010.mov", "FILM/shots/sh020/anim/v002/sh020.mov"],
     movie="FILM\\shots\\sh010\\anim\\v001\\sh010.mov", shot="sh010", depts=["anim"],
     resolves={("sh020", "anim"): "v002/sh020.mov"})

# 12. upper-case folders, lower-case files
case("case_mix", ["F/SH010/anim/sh010_anim_v001.mov", "F/SH010/anim/sh010_anim_v002.mov",
                  "F/SH020/anim/sh020_anim_v003.mov"],
     movie="F/SH010/anim/sh010_anim_v002.mov", shot="SH010", depts=["anim"],
     resolves={("SH020", "anim"): "sh020_anim_v003.mov"})

# 13. sequence folder above shot folders named by number only
case("number_shots", [
    "film/sq010/0040/anim/sq010_0040_anim_v002.mov", "film/sq010/0040/scenes/sq010_0040.ma",
    "film/sq010/0050/anim/sq010_0050_anim_v001.mov", "film/sq020/0010/anim/sq020_0010_anim_v001.mov"],
    movie="film/sq010/0040/anim/sq010_0040_anim_v002.mov", scene="film/sq010/0040/scenes/sq010_0040.ma",
    shot="0040", sequence="sq010", depts=["anim"], shots=["0040", "0050"],
    resolves={("0050", "anim"): "sq010_0050_anim_v001.mov"})

# 14. episodes: ep / seq / shot codes
case("episodes", [
    "show/ep01/ep01_sq02_sh030/blast/v001/ep01_sq02_sh030_blast_v001.mov",
    "show/ep01/ep01_sq02_sh040/blast/v004/ep01_sq02_sh040_blast_v004.mov"],
    movie="show/ep01/ep01_sq02_sh030/blast/v001/ep01_sq02_sh030_blast_v001.mov",
    shot="ep01_sq02_sh030", depts=["blast"], shots=["ep01_sq02_sh030", "ep01_sq02_sh040"],
    resolves={("ep01_sq02_sh040", "blast"): "ep01_sq02_sh040_blast_v004.mov"})

# 15. department abbreviation in names, departments side by side in one folder
case("words_in_names", ["f/sh010/sh010_anim_v003.mov", "f/sh010/sh010_lgt_v002.mov",
                        "f/sh010/sh010_lgt_v001.mov", "f/sh020/sh020_lgt_v005.mov"],
     movie="f/sh010/sh010_anim_v003.mov", shot="sh010", depts=["anim", "lgt"],
     resolves={("sh020", "lgt"): "sh020_lgt_v005.mov"})

# 16. movies and mp4s mixed between versions
case("mov_and_mp4", ["f/sh010/pb/sh010_pb_v001.mov", "f/sh010/pb/sh010_pb_v002.mp4",
                     "f/sh020/pb/sh020_pb_v001.mp4"],
     movie="f/sh010/pb/sh010_pb_v002.mp4", shot="sh010", depts=["pb"],
     resolves={("sh010", "pb"): "sh010_pb_v002.mp4", ("sh020", "pb"): "sh020_pb_v001.mp4"})

# 17. version folders with a prefix (anim_v012) and a nested publish folder
case("nested_publish", [
    "p/sh010/publish/anim/anim_v011/sh010.mov", "p/sh010/publish/anim/anim_v012/sh010.mov",
    "p/sh010/publish/light/light_v002/sh010.mov", "p/sh020/publish/light/light_v004/sh020.mov"],
    movie="p/sh010/publish/anim/anim_v012/sh010.mov", shot="sh010", depts=["anim", "light"],
    resolves={("sh020", "light"): "light_v004/sh020.mov"})

# 18. spaces in folder names
case("spaces", ["My Film/Shots/sh010/Play Blasts/sh010_v1.mov", "My Film/Shots/sh020/Play Blasts/sh020_v3.mov"],
     movie="My Film/Shots/sh010/Play Blasts/sh010_v1.mov", shot="sh010", depts=["Play Blasts"],
     resolves={("sh020", "Play Blasts"): "sh020_v3.mov"})

# 19. dailies filed by date: found by searching for the shot's name
case("dailies_by_date", ["d/dailies/2026-10-28/sh010_anim_v3.mov", "d/dailies/2026-10-29/sh020_anim_v1.mov"],
     movie="d/dailies/2026-10-28/sh010_anim_v3.mov", shot="sh010", depts=["dailies"], shots=["sh010", "sh020"],
     resolves={("sh020", "dailies"): "2026-10-29/sh020_anim_v1.mov"})

# 20. a home test scene that doesn't name the shot: learned from the movie, flagged as a guess
case("unrelated_scene", ["f/sh010/anim/v001/sh010.mov", "f/sh020/anim/v001/sh020.mov"],
     movie="f/sh010/anim/v001/sh010.mov", scene="home/test_scene.ma", problem="doesn't mention shot sh010")

# 20b. ... and with no shot folder, the shot can't be told: it asks
case("unrelated_flat", ["f/blasts/sh010_v1.mov", "f/blasts/sh020_v1.mov"],
     movie="f/blasts/sh010_v1.mov", scene="home/test_scene.ma", problem="don't share")

# 21. ... and the shot typed in by the user instead
case("typed_shot", ["f/sh010/anim/v001/sh010.mov", "f/sh020/anim/v004/sh020.mov"],
     movie="f/sh010/anim/v001/sh010.mov", scene="home/test_scene.ma", known="sh010", shot="sh010",
     resolves={("sh020", "anim"): "v004/sh020.mov"})

# 22. date-versioned exports (versions are dates in the name)
case("dated_names", ["f/edit/sh010_20261028.mov", "f/edit/sh010_20261030.mov", "f/edit/sh020_20261029.mov"],
     movie="f/edit/sh010_20261030.mov", shot="sh010", shots=["sh010", "sh020"],
     resolves={("sh010", None): "sh010_20261030.mov"})

# 23. not footage at all
case("not_footage", ["f/sh010/notes.txt"], movie="f/sh010/notes.txt", problem="isn't a movie")


def run(c):
    base = build(c["name"], c["files"])
    movie = base + "/" + c["movie"].replace("\\", "/") if "\\" not in c["movie"] else \
        (base.replace("/", "\\") + "\\" + c["movie"])
    scene = base + "/" + c["scene"] if c["scene"] else None
    lay = learn.learn(movie, scene, c["known"])
    where = "%s: %s" % (c["name"], lay["notes"])
    if c["problem"]:
        assert any(c["problem"] in text for _l, text in lay["notes"] + [n for d in lay["departments"]
                                                                       for n in d["notes"]]), where
        return
    assert lay["shot"] == c["shot"], (where, lay["shot"])
    if c["sequence"]:
        assert (lay["sequence"] or "").lower() == c["sequence"].lower(), (where, lay["sequence"])
    got = [d["name"] for d in lay["departments"]]
    for d in c["depts"] or []:
        assert d in got, (where, got)
    if c["shots"]:
        assert lay["shots"] == c["shots"], (where, lay["shots"])
    apply(lay)
    if scene:                                            # the player places the open scene in its shot
        ids = profile.parse_shot(scene)
        assert ids and ids[1].lower() == lay["shot"].lower(), (where, ids)
        if c["shots"]:                                   # and lists the sequence's shots
            assert profile.list_shots("", ids[2]) == c["shots"], (where, profile.list_shots("", ids[2]))
    elif lay["shot_folder"] and lay["sequence"]:
        profile.list_shots("", lay["sequence"])          # learns the shots' sequence, as the player does
    for (shot, dept), tail in c["resolves"].items():
        got = resolve(shot, dept)
        assert got and got.endswith(tail), (where, shot, dept, got, learn.to_profile(lay))


for c in CASES:
    run(c)
print("ok: %d made-up layouts learned from one example each; with the learned settings the player "
      "places the open scene, lists its sequence's shots and finds their newest footage" % len(CASES))

# ---- version names
assert names.version_in("P_sq010_0040_anim_v012", "P_sq010_0040_anim_v*") == 12
assert names.version_in("sh010_take3", "sh010_take*") == 3
assert names.version_in("2026-10-28", "*") == 20261028
assert names.version_in("SH010_ANIM_V004", "sh010_anim_v*") == 4
assert names.version_in("sh010", "sh010") is None and names.matches("SH010", "sh010")
assert learn.version_pattern("{shot}_anim_v004") == ("{shot}_anim_v*", "v")
assert learn.version_pattern("{shot}_003") == ("{shot}_*", "number")
assert learn.version_pattern("{shot}") == ("{shot}", None)
print("ok: versions read however they're written: v012, take3, _003, dates; upper or lower case")

# ---- Search by shot name
found = learn.scan([os.path.join(ROOT, "dailies_by_date")], learn.shot_pattern("{shot}_anim_v3", "sh010", None))
assert sorted(found) == ["sh010", "sh020"] and found["sh020"][0].endswith("sh020_anim_v1.mov")
print("ok: Search by shot name finds each shot's footage under the folders you point at")

# ---- By hand: a movie dropped onto a shot's card; its later versions count as newer
base = build("by_hand", ["odd/place/SHOT_TEN_final_v1.mov", "odd/place/SHOT_TEN_final_v2.mov",
                         "f/sh010/anim/v001/sh010.mov"])
lay = learn.learn(base + "/f/sh010/anim/v001/sh010.mov")
prof = learn.to_profile(lay)
prof["footage_by_hand"] = {"sh020": {"anim": base + "/odd/place/SHOT_TEN_final_v1.mov"}}
with open(PROFILE, "w") as handle:
    json.dump(prof, handle)
profile.load(force=True)
assert resolve("sh020", "anim").endswith("SHOT_TEN_final_v2.mov")
assert resolver.list_versions("", "sh020", "anim") == [2, 1]
print("ok: a movie dropped on a shot by hand is used for it, and its later versions count as newer")

shutil.rmtree(ROOT, ignore_errors=True)

# ---- cut order from an edit export
from bgcache.continuity import edit_order                   # noqa: E402
ROOT2 = os.path.realpath(tempfile.mkdtemp())
edl = os.path.join(ROOT2, "cut.edl")
open(edl, "w").write("""TITLE: CUT
FCM: NON-DROP FRAME

001  SH030 V     C        00:00:00:00 00:00:02:00 01:00:00:00 01:00:02:00
* FROM CLIP NAME: sh030_anim_v004.mov
002  SH010 V     C        00:00:00:00 00:00:01:00 01:00:02:00 01:00:03:00
* FROM CLIP NAME: sh010_anim_v002.mov
003  SH030 V     C        00:00:02:00 00:00:03:00 01:00:03:00 01:00:04:00
""")
pat = learn.shot_pattern("{shot}_anim_v002", "sh010", None)
assert [s.lower() for s in edit_order.order(edl, pat)] == ["sh030", "sh010"]
assert edit_order.sort_shots(["sh010", "sh020", "sh030"], edl, pat) == ["sh030", "sh010", "sh020"]
xml = os.path.join(ROOT2, "cut.xml")
open(xml, "w").write("""<?xml version="1.0"?><xmeml version="4"><sequence><media><video><track>
<clipitem><name>sh020_v1.mov</name><start>48</start></clipitem>
<clipitem><name>sh010_v3.mov</name><start>0</start></clipitem>
</track></video><audio><track><clipitem><name>sh099_mix.wav</name><start>0</start></clipitem></track></audio>
</media></sequence></xmeml>""")
assert edit_order.order(xml, pat) == ["sh010", "sh020"]
fcpx = os.path.join(ROOT2, "cut.fcpxml")
open(fcpx, "w").write("""<?xml version="1.0"?><fcpxml version="1.10"><library><event><project><sequence>
<spine><asset-clip name="sh020 v2"/><gap/><asset-clip name="sh040_v1"/><asset-clip name="sh010"/></spine>
</sequence></project></event></library></fcpxml>""")
assert edit_order.order(fcpx, pat) == ["sh020", "sh040", "sh010"]
assert edit_order.order(os.path.join(ROOT2, "missing.edl"), pat) == []
print("ok: shots follow the cut from an EDL, Final Cut / Premiere XML or FCPXML; shots not in the edit come after")
shutil.rmtree(ROOT2, ignore_errors=True)
