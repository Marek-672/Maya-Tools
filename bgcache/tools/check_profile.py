"""Check a bgcache pipeline profile against a real scene path.
    python3 check_profile.py <folder containing bgcache> <profile.json> <scene path>
"""
import os, sys
sys.path.insert(0, sys.argv[1])
os.environ["BGCACHE_PROFILE"] = sys.argv[2]
from bgcache import profile
from bgcache.continuity import resolver

scene = sys.argv[3]
print("profile:  ", profile.source())
ids = profile.parse_shot(scene)
if not ids:
    sys.exit("not in a shot: %s doesn't match shot_folder %r" % (scene, profile.get("shot_folder")))
show, shot, sequence = ids
print("shot:      show %s, sequence %s, shot %s" % (show, sequence, shot))
print("drawings: ", profile.drawings_root(scene))
shots = resolver.list_shots_in_sequence(show, sequence)
print("sequence:  %d shots: %s" % (len(shots), " ".join(shots)))
for dept in resolver.get_departments():
    found = resolver.resolve_shot(show, shot, dept["name"])
    print("  %-12s %s" % (dept["name"], "v%03d  %s" % (found["version"], found["source_path"])
                          if found else "none found"))
