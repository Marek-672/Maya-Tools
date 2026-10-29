# How bgcache talks to Maya

(Where each part lives in the code: DEVELOPER.md, next to this file.)

For pipeline and technical teams. In short: **three local processes that talk only through small files in a per-session temp folder.** There's no network traffic, no sockets, no commandPort and no server, and your scene file is never saved. (The one exception: when an artist chooses **Help > Check for updates** outside a studio, the player asks GitHub for the latest release. Studio builds look in the studio's releases folder instead, and a profile with an empty `github_releases` never goes online.)

```
 your Maya (controller.py)                hidden Maya (worker.py)             player (mayapy, player.py)
 ───────────────────────────              ──────────────────────              ──────────────────────────
 Maya callbacks see key edits  ── inbox/*.json (messages) ──▶  applies them,
 (curves, unkeyed values,                                      re-playblasts only the
  visibility, image planes)                                    changed frames
                               ◀── status.json (1 s heartbeat) ─┤
                                                                ├── frames/<camera>/f.####.jpg ──▶ plays them, with sound
 follows the player's frame    ◀── player_time.json, player_cmd.json ──────────────────────────────┤
 tells the player its frame    ── maya_time.json ──────────────────────────────────────────────────▶
                                                         ◀── cameras.json (which cameras to cache) ─┘
 config.json (written at Start / Reload scene) is read by both the hidden Maya and the player.
```

## The three processes

| Process | What it is | Started by |
|---|---|---|
| **Your Maya**, `bgcache/controller.py` (with `controller_*.py` and `scene.py`) | The Maya you animate in. It watches your edits and sends them on. It never playblasts. | The bgcache shelf button. |
| **Hidden Maya**, `bgcache/worker.py` | A second, full Maya, minimised. It opens a copy of your scene, mirrors your edits and playblasts only the frames they change. | Your Maya, with `subprocess.Popen([maya, "-command", 'python("…import bgcache.worker; bgcache.worker.boot()")'])`. The bgcache folder is passed in `BGCACHE_PKG`. |
| **Player**, `bgcache/player.py` | A separate `mayapy` process (Qt). It plays the cached frames at full speed with sound, and holds the drawing and continuity tools. If no mayapy is found, it runs as a window inside your Maya. | Your Maya, with `subprocess.Popen([mayapy, "-c", …, session, <your Maya's pid>])`. |

All three run on the same machine as the same user. The hidden Maya and the player both quit by themselves when your Maya's process is gone, so nothing is left running after a crash.

## Where the files are

- **Session folder:** `$TMPDIR/maya_bgcache_<user>/<date_time_pid>/`. One per Start. Set `BGCACHE_ROOT` to move it. Leftover folders from earlier sessions are removed at the next Start.
- **Logs:** `~/.bgcache/logs/<session>/`, holding `worker.log`, `player.log` and `trace.log`. The newest 15 sessions are kept. Set `BGCACHE_LOGS` to move them.

**Every file is written atomically:** each is written to a temp name and then renamed, so a reader never sees half a file. On Windows the rename is retried for a moment if another process has the file open.

| File | Written by | Read by | What's in it | How often |
|---|---|---|---|---|
| `config.json` | your Maya | hidden Maya, player | Scene copy path, frame range, fps, cameras, sound, your viewport settings and renderer, GPU choice, plug-ins to load, size and quality of the cache | At Start and at Reload scene |
| `inbox/<time>_<n>.json` | your Maya (the player's buttons go through your Maya; only Stop, if your Maya doesn't answer within 4 s, writes `quit` here itself) | hidden Maya, which deletes each one after reading | One message each, for example `curves` (key data of edited curves), `statics` (unkeyed values, display, visibility, image planes, GPU), `curve_shapes` (path curve CVs), `delete_curves`, `reload`, `pause`, `selftest`, `quit` | On each edit, after a short pause while you work |
| `status.json` | hidden Maya | your Maya, player | State, dirty frames and a frame version per camera, warnings, GPU state, the hidden Maya's process id | When something changes, plus a heartbeat every 1 s |
| `frames/<camera>/f.<frame>.jpg` | hidden Maya | player | The cached frames: JPEG, 960×540, quality 85 by default | Each batch of 1 to 12 frames |
| `cameras.json` | player | hidden Maya | Which cameras to cache, which one you're viewing, and the focus range (the frames to cache now) | When you change them |
| `player_time.json` | player | your Maya, checked every 150 ms | The player's current frame (Sync) | While you play, scrub or step |
| `maya_time.json` | your Maya | player | Your Maya's current frame, plus "bring the player to the front" | When your time changes (at most 4 times a second while your Maya plays, then the frame it stops on) |
| `player_cmd.json` (+ `.done`) | player | your Maya, checked every 150 ms; it writes `.done` back | Buttons that need your Maya: Refresh, Reload scene, Re-render all, Push selected, next/previous key, Stop, Restart, Self-test, Update | When you press them |

The hidden Maya checks its inbox every 50 ms (every 100 ms after 2 s with nothing to do). Its whole loop runs in Maya's idle time: read messages, apply them, playblast the next batch, write the status.

## What your Maya listens to

All of this is set up at Start and removed at Stop:

- `MAnimMessage.addAnimCurveEditedCallback`: key edits.
- `MDGMessage.addNodeAddedCallback` and `addNodeRemovedCallback` on `animCurve`: curves made or deleted.
- `scriptJob`s on `Undo`, `Redo`, `timeChanged`, `SelectionChanged` and `deleteAll`, plus `conditionFalse` on `playingBack` (the frame your playback stops on).
- `MNodeMessage.addAttributeChangedCallback` on **path curves** only: curve shapes you edit by hand that drive a motion path, spline IK, wire or similar (usually a handful). Moving their CVs sends the new positions.
- `MSceneMessage` `kBeforeOpen`, `kBeforeNew` and `kMayaExiting`: bgcache stops before the scene changes. `kBeforeSave` is used only while the player's reference image plane is in your scene, to offer to remove it before you save.
- Three Qt timers: a short "flush" after edits, a 1 s status check, and a 150 ms check of the player's frame and commands.

What it sends is **data, not scenes**: for each edited curve, its keys, tangents and a few sampled values, plus the frame ranges that changed. Unkeyed values, display layers, hidden or shown objects, viewport settings, image planes and the GPU Override setting go only at Start and when you press **Refresh**. **Reload scene** exports a fresh copy and reopens it in the hidden Maya.

## Your scene and your preferences are safe

- **Your file is never saved by bgcache.** If your scene has unsaved changes, your Maya exports a private copy to the session folder. Otherwise the hidden Maya opens your file as it is, and never saves it.
- **The hidden Maya never saves anything.** It marks its scene unchanged and quits without saving, so it can never ask "Save changes?".
- **It has its own preferences folder.** It runs with its own `MAYA_APP_DIR` (`~/.bgcache/maya_app`), a copy of yours made once. It still finds your scripts, modules and plug-ins, but it can't change your preferences. If it ever found itself using yours, it closes at once without saving anything.
- **It starts light:** without auto-loaded plug-ins. It loads only the plug-ins your scene's nodes use, plus the plug-in for your viewport renderer (for example the studioViewport2).
- Tools in the profile's `skip_in_background` are left off its paths. Tools in `switch_off_in_background` are switched off inside it only, never in your Maya.

## How the hidden Maya draws

It playblasts off-screen from its own panel. The panel looks through the camera you're viewing, with:
- your viewport's display settings and your renderer, including a studio render override such as the studioViewport2;
- textures loaded before drawing;
- no HUD, grid or overlays;
- the camera's full frame, with no overscan and no 2D pan/zoom.

GPU deformers follow your Maya's GPU Override. If they fail there, the hidden Maya switches to the CPU by itself, or your Maya restarts it on the CPU if it got stuck.

## Debugging

- **`worker.log`** (the hidden Maya): startup timing, plug-ins loaded, the renderer used, GPU, every batch ("rendered 12 frames in 2.6s (playblast 2.6s)"), and errors.
- **`trace.log`** (your Maya): every callback and message, for crash hunting.
- **`player.log`**: sound device and playback.
- **Self-test** (player → Help → Self-test) prints a report in your Maya's Script Editor: evaluators, viewport settings, and a playblast benchmark in the hidden Maya.
