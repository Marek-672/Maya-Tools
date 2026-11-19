# bgcache: developer guide

For whoever looks after bgcache's code. How the three processes talk to each
other (files, callbacks, safety) is in **HOW_IT_WORKS.md**, next to this
file; this page says where each part of that lives in the code, and how to
test and build it.

```
 your Maya                         hidden Maya                    player (mayapy)
 ─────────                         ───────────                    ───────────────
 controller.py  ── Controller ──┐  worker.py                      player.py
   controller_edits.py          │    applies messages,              plays frames + sound
   controller_refresh.py        │    playblasts dirty frames        drawui.py / drawing.py
   controller_gpu.py            │                                   continuity/ (Full edition)
   controller_sync.py           │                                   audio.py, widgets.py, theme.py
   controller_refplane.py       │
 scene.py (reads your Maya) ────┘

 all three: common.py (session folder, atomic JSON files, the inbox)
```

## Code map

### In your Maya (the controller)

| File | What's in it |
|---|---|
| `controller.py` | The `Controller` class: Start (in steps: `_session_config`, `_copy_scene_for_background`, `_take_snapshot`, `_start_watching`), launching the hidden Maya and the player, Stop, the 1 s status check. Also the module functions the shelf and Maya call: `get`, `shelf_click`, `shelf_stop`, `shelf_reopen`, `shelf_restart`, `shelf_selftest`, `show_ui`, `unload`, `check_undo`. |
| `controller_edits.py` | `EditsMixin`: Maya callbacks (`_install_callbacks`), trace.log, path curves (`_send_path_curves`), and `flush`, which sends deleted and edited curves with the frames they dirty. |
| `controller_refresh.py` | `RefreshMixin`: Refresh (`refresh_display`: the one button since 0.9.0b21; it sends only what's different, says what it sent, and asks before a reload) and Reload scene. |
| `controller_gpu.py` | `GpuRescueMixin`: notices the hidden Maya stuck on GPU errors and restarts it on the CPU (`restart_on_cpu`, once per session). |
| `controller_sync.py` | `SyncMixin`: time sync with the player (`player_time.json`, `maya_time.json`), the player's buttons that need your Maya (`player_cmd.json`: Refresh, Reload scene, Stop...), Push selected, Re-render all. |
| `controller_cameras.py` | `CameraMixin` (0.9.0b12): watches the cameras being cached (cameras.json's checked list) and, when one you moved without keys comes to rest, sends its unkeyed values (`statics`). |
| `controller_scene.py` | `SceneWatchMixin` (0.9.0b21): `structure()` (references, counts of constraints, deformers, objects, animation layers and their channels) and what Maya reports while you work (references, imports, constraints, animation layers made); writes `refresh_note.json` for the player's orange note and the reload question; `unkeyed_changes` for Refresh. |
| `controller_assets.py` | `AssetsMixin` (0.9.0b20-b25): once a second, sends what you showed or hid (the studio's asset groups, anything you've selected, display layers) and animation layer mute / solo / weight; the player's Show selected / Hide selected (`cache_selected`, `cache_forget`, `cache_lists.json`), for the working session only. |
| `assets.py` | No Maya: which groups the cache leaves out (`cache_assets` in the profile), and the Shown / Hidden lists (`show`, `remove`, `forget`). |
| `refreshing.py` | No Maya: the words of Refresh (what it sent, the note, the reload question) and `structure_changes`. |
| `background_setup.py` | Not imported: copied as the hidden Maya's `userSetup.py` (0.9.0b19). Keeps its main window see-through and minimized while it starts, and hands the keyboard back. |
| `controller_refplane.py` | `RefPlaneMixin`: the player's reference movie as an image plane in your Maya. |
| `scene.py` | Plain functions that read your scene and Maya: cameras, viewport settings and renderer, image planes, sound, GPU Override, path curves, anim curve data, where Maya and mayapy are, the hidden Maya's preferences folder. No state, except `DISPLAY_SOURCE`. |
| `hotkeys.py` | Reads your Maya hotkeys, so the player's keys match. |
| `install.py`, `update.py` | Shelf setup; Help > Check for updates (the studio's releases folder or list of folders, or GitHub releases) and Update and restart. |
| `selftest.py` | Help > Self-test (runs in both Mayas). |

Before 0.8.0b21 everything above (except hotkeys, install, update, selftest)
was one 2,400-line `controller.py`. The old names still work:
`bgcache.controller.list_cameras`, `bgcache.controller.REF_PLANE` and so on
are the same objects as in `scene.py`.

**Patching in tests:** the Controller calls scene functions as
`scene.list_cameras()`, so patch them on `bgcache.scene` (or
`controller.scene`), not on `bgcache.controller`.

### In the hidden Maya

| File | What's in it |
|---|---|
| `worker.py` | `boot()` (started with `maya -command`), the `Worker` class: opens the scene, builds the off-screen render panel, applies inbox messages (`handle`, `_apply_edit`), picks dirty frames (`_todo`, the focus range), playblasts batches, writes `status.json`. |
| `worker_assets.py` | `AssetsWorkerMixin` (0.9.0b20): hides the environment groups and what you hid in the player, in its own copy only; remembers how your Maya has things for when they're shown again. |

### In the player

| File | What's in it |
|---|---|
| `player.py` | `Player`: the window (`_build_ui` and its `_build_*` parts), the Canvas, `main()` (the mayapy entry). Since 0.9.0b8 the rest is in topic files, as mixins (like the controller's): |
| `player_menus.py` | `MenusMixin`: Help > Check for updates (and Go back to an earlier version), Help > Report a problem (`ReportDialog`), the camera menu. |
| `player_range.py` | `RangeMixin`: the focus range (I / O, the bar's handles) and, b8, your Maya's playback range (`maya_range.json`): with Sync on they're the same both ways, Match Maya, the shot's cut (`cfg["cut"]`). |
| `player_reel.py` | `ReelMixin`: the reel (shots before, yours, after) and its sound; sound timing, the sync test. |
| `player_session.py` | `SessionMixin`: time sync, Reload scene, health banners, reading new frames (`_poll`), closing when your Maya asks (`player_close.json`, b8). |
| `player_input.py` | `InputMixin`: playback, keys, mouse and pen. |
| `player_paint.py` | `PaintMixin`: the picture, drawings, overlays, banners and the cache bar (hatched: not rendered yet; red: out of date; purple line: outside the cut; blue line: your Maya's range). |
| `player_common.py` | Qt, colours and small helpers shared by the player files. |
| `drawui.py`, `drawing.py` | Drawing: `drawing.py` is the files (no Qt); `drawui.py` the `Drawer` (where you draw: your shot or, b8, a shot around it, `place()`; rows; changes), split in b8 into `drawui_people.py` (other people: snapshots, Update / Revert, listed by themselves with their layers off), `drawui_saving.py` (Save, versions, recovery, asking to save), `drawui_strokes.py` (pen and eraser, painting, Blue Pencil export), `drawui_widgets.py` and `drawui_panel.py` (the strip), `drawui_icons.py`, `drawui_common.py`. Since 0.9.0b3 edits mark the drawings dirty (`Drawer.edited`) and write a recovery copy; only `save_now` (Save, Ctrl+S) writes the shared file, keeping the last 10 versions. |
| `report.py` | Help > Report a problem: gathers the logs into a zip, Hide names, Save, and Send to the profile's `reports_url`. With `update.py`, the only code that goes online, and only on a click. |
| `continuity/` | The Full edition's neighbour shots: `ui.py` (the strip), `reel.py` (converting and playing), `resolver.py` (which file is a shot's footage), `names.py` (movie / sequence names and versions however written). 0.9.0b4: `learn.py` (the setup wizard's learning core: paths in, settings out; `scan` for Search by shot name), `wizard.py` (the five-step window), `edit_order.py` (cut order from EDL / XML / FCPXML), `ffmpeg_get.py` (find ffmpeg, or download the pinned build). The Simple edition is built without this folder; `player.py` falls back to `NoContinuity`. |
| `audio.py`, `widgets.py`, `theme.py` | Sound, small shared widgets, the dark look. |

### Shared

| File | What's in it |
|---|---|
| `common.py` | Session folders and paths, atomic JSON writes, the inbox. Used by all three processes; no Maya imports. |
| `profile.py` | The pipeline profile (`profile.json`): studio settings and folder templates. Keys are listed in `tools/public/PIPELINE_SETUP.md`. |
| `system/` | What differs between Linux, Windows and macOS. |
| `stubs/` | Empty stand-ins for tools left out of the hidden Maya. |

## Rules the code keeps

- **Your scene is never saved.** Only the hidden Maya opens a copy.
- **Nothing extra in the hidden Maya's render path** unless it must be there: new features go in the player.
- **A "catch any error" says why:** each `except Exception` either reports the error (`scene._ignored` writes trace.log, `worker._ignored` writes worker.log, or a message the artist sees) or has a one-line comment giving the reason it is safe to carry on. `tests/test_b21.py` checks this.
- **No function over 80 lines** (also checked by `tests/test_b21.py`).
- **Getting a studio build to work without a download:** `tools/make_paste.py` turns an install folder update into `PASTE_bgcache_<version>.py` (and parts) to paste into Maya's Script Editor; it publishes into the studio install folder. See `PASTE_INSTALL.md` (studio only).
- **Studio-specific code never goes in the shared files.** It lives in `studio_private/` (a studio's `profile.json` and `studio_*.py` hooks named in it, such as `before_playblast`) and is added only by `tools/build_studio.py`.
- **Never wait on the mouse for long.** bgcache holds back while a mouse button is down (a drag), but Qt can lose a release and report a button held for good. `scene._mouse_held` asks the system too on Windows and gives up after 20 s anywhere (0.9.0b25). Anything new that waits for the mouse must go through it.
- **The controller is made on Maya's main thread.** Its Qt timers never fire otherwise (found by the torture test).

## Tests

```
python3 tests/run_tests.py
```

No Maya or Qt needed: each test stubs them. About 440 checks (`test_learn.py` builds 25 made-up production layouts and checks the learned settings find the neighbours' footage; add a case for every real layout that fails); run before every
build. `tests/_source.py` gives tests the source text (`source("controller")`
returns the controller files and `scene.py` together) for checks on the code
itself. Real-Maya checks: `tools/maya_torture.py` runs a build (the installed one, or
a download given as `BUILD`) through 40 things a user might do or do by
accident in an interactive Maya on an empty scene, reads the Script Editor
and worker.log for errors after each, and writes `torture_report.txt`. Run it
before a build is sent or published. It uses a tiny scene: speed, textures and
a studio's renderer are still checked by hand on real shots (see the TODO).

## Builds

| Script | Makes |
|---|---|
| `tools/build_studio.py [out] --name <studio>` (not in the public copy) | The studio build: a drag-and-drop install zip and the `bgcache_<version>.zip` for the studio's releases folder (the player's Update and restart). Full edition plus `studio_private/`. |
| `tools/build_release.py` | The generic downloads (Simple and Full), with no studio files. |
| `tools/make_public.py <out>` (not in the public copy) | The clean public copy for GitHub: public files only, studio names replaced, then checks nothing studio-specific is left and runs the tests in the copy. |

The version is `__version__` in `bgcache/__init__.py`; each build gets a new
number (`0.8.0bNN`) and a `CHANGELOG.md` entry.
