"""Run every bgcache test (no Maya needed: Maya and Qt are stubbed).

    python3 tests/run_tests.py

Each test file prints one "ok: ..." line per passing check; any failure stops
that file with a traceback. Run before every release.
"""
import glob, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
# Tests run with the studio-style profile in fixtures/ unless a test sets its own.
# A throwaway home folder too, so no test can touch your own settings
# (~ is HOME on Linux/macOS, USERPROFILE on Windows).
home = tempfile.mkdtemp(prefix="bgcache_testhome_")
env = dict(os.environ, BGCACHE_LOGS=tempfile.mkdtemp(prefix="bgcache_testlogs_"),
           BGCACHE_PROFILE=os.path.join(HERE, "fixtures", "studio_profile.json"),
           HOME=home, USERPROFILE=home,
           PYTHONUTF8="1", PYTHONIOENCODING="utf-8")        # read source files as UTF-8 on Windows too (its default is cp1252)
if hasattr(sys.stdout, "reconfigure"):   # a Windows console can't print every character
    sys.stdout.reconfigure(errors="replace")
total, failed = 0, []
for path in sorted(glob.glob(os.path.join(HERE, "test_*.py"))):
    # the tests print UTF-8 (PYTHONUTF8 above): read it as UTF-8, not Windows' cp1252
    result = subprocess.run([sys.executable, path], capture_output=True, encoding="utf-8", errors="replace",
                            env=env, cwd=HERE)
    oks = [l for l in result.stdout.splitlines() if l.startswith("ok")]
    total += len(oks)
    status = "PASS" if result.returncode == 0 else "FAIL"
    print("%-4s %-24s %3d checks" % (status, os.path.basename(path), len(oks)))
    if result.returncode != 0:
        failed.append(path)
        print("\n".join(("    " + l) for l in (result.stdout + result.stderr).splitlines()[-12:]))
        if os.environ.get("GITHUB_ACTIONS"):     # show the failure on the GitHub run page too
            tail = (result.stdout + result.stderr).splitlines()[-12:]
            print("::error title=%s::%s" % (os.path.basename(path), "%0A".join(tail).replace("::", ": :")))
print("\n%d checks passed, %d file(s) failed" % (total, len(failed)))
sys.exit(1 if failed else 0)
