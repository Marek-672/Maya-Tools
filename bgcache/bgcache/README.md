# bgcache

For pipeline and technical teams: **[How bgcache talks to Maya](HOW_IT_WORKS.md)** (three local processes, files only, no network, your scene never saved).

Background, dirty-frames-only playback for heavy Maya shots. You keep animating in your normal Maya. A second Maya mirrors your key edits and re-playblasts only the frames those edits affect. A separate flipbook window plays the result at full speed.

Nothing in the studio setup is changed. The only "intrusion" is that the background session switches off the tools listed in the pipeline profile's `switch_off_in_background` *in its own session* (at the studio: the `rig_callbacks` callbacks, since controls aren't in the images). Set `switch_off_tools=False` to leave them on.

## Install

Drag `install_bgcache.py` (in the download for your system) into a Maya viewport and choose **Install**. It installs bgcache as a Maya module in your own Maya folder, for every Maya from 2024 up, and adds a bgcache button to your shelf. It works straight away, no restart. Drag it in again to **Update** (press Stop in the player first; no restart needed; your old copy is kept) or **Uninstall**. Studios can also use the `install_bgcache` folder (`./install`, `drag_into_maya.py`) that keeps every build for rolling back.

## Use

In your animation Maya, click the **bgcache** shelf button. That's Start: there's no separate control panel, everything is in the player (since 0.8.0b12). Clicking the button again while bgcache runs brings the player to the front, or opens it again if you closed it. Right-click the button for **Stop bgcache**, **Reopen player**, **Restart bgcache** and **Self-test**.

From Python, with options:

```python
import bgcache.controller as bgc
bgc.shelf_click()                  # defaults: 960x540, batches of up to 12 frames
# or: bgc.shelf_click(width=1280, height=720, chunk=6)   # chunk = largest batch
```

If the scene has unsaved changes, it exports a private copy for the background Maya (your file is never saved). It then snapshots your curves, starts a second Maya on that scene, and opens the player. **Nothing renders until you check a camera in the player.** You can pick one right away, while the background Maya is still loading, and rendering starts as soon as the scene is ready. The first full render of a camera takes about as long as playing the whole shot once at the background's frame rate. After that, only dirty frames re-render.

## The player window

Top to bottom: a toolbar (the menus **bgcache** (Push selected, Restart bgcache, Stop bgcache), **View** (Film gate: darkens what's outside the camera's film gate; Show drawings; Keep on top; and under Sound: Sound while scrubbing, Sync test, Reset sound offset) and **Help** (Self-test, Check for updates, About); then the Camera dropdown, Draw, the three cache buttons **Refresh**, **Reload scene** and **Re-render all**, and Pause), the continuity strip (its header has the **Continuity** switch, **Update footage** and **Untick all**), the picture (camera and sound bottom-left, frame number bottom-right), the cache bar, and the playback bar: Maya-style playback buttons (start, step frame, step key, play backwards/forwards, end), then **Loop**, **Sound** and **Sync**. Buttons that switch something on are lit (blue with a bright outline) while it's on. The step-key buttons step through the keys of your selection in Maya, like Maya's own.

## Continuity

The continuity strip comes with **bgcache Full** (the `continuity/` folder) and needs a pipeline profile that says where shots are (see `profile.py` and `profiles/example_studio.json`). The shot browser lists the sequence's shots (found from your scene's path and the profile's `shot_folder`, e.g. `/projects/<show>/<shot>/...`). Tick the small checkbox on a shot's thumbnail to add it to the reel: shots left of yours play before it, shots right of it play after, as many as you like, always in sequence order. Ticks last while the player is open; every Start begins with none ticked. **Untick all** (at the right of the strip's header) takes them all out at once. Your shot's card is outlined orange; ticked shots are outlined blue and show blue on the cache bar. Your shot is centred in the strip whenever the browser opens. Click a shot's department label (e.g. "P v009 ▾") or right-click the shot to choose its department. Auto, the default, uses the first department that has footage, in the profile's `auto_order`; a department you pick by hand shows in blue. Each department in that menu opens a list of its versions: **Latest** follows new versions as they come in; picking a version (the 10 newest are listed, **More versions...** for the rest) pins it for that shot, shown as "(pinned)" and remembered. Right-click a shot for **Check for newer now**, **Update this shot's footage** (the same version converted again, for a movie re-published under the same name) and **Show in folder**; **Update footage** in the strip's header does the check for every shot. Every couple of minutes the strip checks for newer footage by itself (and reloads a shot that follows Latest when its movie file has changed): a shot that isn't pinned then shows its label in orange, e.g. "P v012 → v013", and **Update to P v013** at the top of its menu swaps it in. Department locations come from the profile's `departments`, or from the file named in its `departments_file` (e.g. the studio's shot reference tool's `~/.studio_ref_config.json`; the player only reads that file).

Staged shots are converted once to JPEGs at the player's size and cached in `$TMPDIR/bgcache_reel/` (movies need ffmpeg, found the same way as the Maya tool). Each plays with its own sound: the shot's sound file (same folder layout as your shot's, newest version), else the movie's sound, else silence, cut to exactly the shot's length so cuts stay in sync.

- **▴ Continuity** in the browser header folds the browser away (C key). Staged shots still play and are listed in the header.
- **Continuity** in the toolbar turns the feature off: only your shot plays.
- Staged shots, department choices and these settings are remembered per shot in `~/.bgcache_player.json`.

On neighbour shots Maya doesn't move (those frames aren't in your scene); time sync resumes when the playhead is back on your shot.

## Your shot as a reference movie, and image planes

Your own shot's card (orange) has a dropdown too: **Live** (your animation, the default) or any department's movie for this shot (P, WP, shoco, editorial, lighting). Picking one plays that movie in your shot's slot of the reel, marked REFERENCE (your shot's card shows that movie with an orange **REF** tag), so you can check it in continuity with the shots around it. Pick **Live** again in the same dropdown to go back. The live cache keeps updating in the background.

The same dropdown can put that movie into your Maya as an image plane on the shot camera, **in front** (covers the scene) or **behind** (the scene draws over it). It fills the camera view either way and steps with your timeline; adjust transparency etc. in its attributes (`bgcache_reference`). **Remove image plane** takes it out; so does Stop, and saving with it still in asks whether to remove it first. Press **Refresh** to put it in the cache too (since 0.8.0b17 it waits for Refresh, like every image plane): the player then shows your animation over it (behind: the movie as a backdrop; in front: covering, adjust its transparency). Image planes you add yourself after Start also come in with **Refresh**.


The player lists the scene's shot cameras on the right. Persp, top, front and side are left out, and key edits on them are ignored, so tumbling persp with Auto Key on never triggers a re-render.

- **Check** a camera to cache it. The first checked camera becomes the one you view.
- Cameras are in the toolbar's **Camera** dropdown. **Click a name** to view it (that also caches it). The viewed camera always renders first after an edit; other checked cameras catch up in idle time.
- **Uncheck** a camera to stop caching it and drop its frames.
- Each checked camera adds roughly one more render of the dirty frames after every edit, so two or three is comfortable.

Key edits to a shot camera's animation are synced like any other animation.

## Time sync

When you scrub, step or pause in the player, Maya moves to that frame once the player has rested on it for a quarter of a second (stepping quickly or flipping through drawings doesn't make Maya evaluate every frame on the way). When you change frames in Maya, the paused player follows. The **Sync** button turns it off and on for both directions, and the player remembers your choice next time. While it's off, an orange **SYNC OFF** tag sits on the picture. (There's no single-letter key for it: S is Set Key in Maya, too easy to press while the player has focus.) While Maya itself is playing, the player doesn't move Maya.

## The background Maya

At startup it closes any editors it inherited from your saved window layout (Graph Editor, Outliner, Channel Box, Attribute Editor...), switches to a single view and stops other viewports drawing, so nothing redraws while it rebuilds curves. It does this again after opening the scene and after each Reload scene.

## Your preferences are never touched

The background Maya has its own preferences folder, `~/.bgcache/maya_app/`, made the first time from a copy of yours without your window layout, panel layouts or shelves. Whatever it saves goes there, never into `~/maya`. Your own scripts, modules and plug-ins are still found. It also quits without saving preferences. After changing a preference that matters for the cache (a viewport setting, say), start it with:

```python
import bgcache.controller as bgc; bgc.shelf_click(refresh_background_prefs=True)
```

## Opening another scene

Opening a file, File > New or quitting Maya stops bgcache automatically, before the old scene is cleared, and closes the background Maya and the player. Click Start again in the new scene.

## Versions and rolling back

Every release is archived as `releases/bgcache_<version>.zip` in the shared install folder. With Maya closed:

- `install --list` shows the archived versions and the one you have.
- `install --version 0.6.2` installs that exact version.
- `install --rollback` puts back what you had before your last install.

`CHANGELOG.md` (with the source) lists what changed in each version.

## Logs and crash hunting

Each session's logs are kept in `~/.bgcache/logs/<session>/` (the newest 15 sessions), outside the temp folder, so they survive a crash or a temp clean-up:

- `trace.log`: one timestamped line for everything bgcache does in your Maya. After a crash, its last line shows whether bgcache was busy at that moment, and with what. `shelf_click(trace=False)` turns it off.
- `worker.log`: the background Maya, including its own trace of each render and message, and why it closed.
- `player.log`: the player.

It starts without Maya's auto-loaded plug-ins (faster, lighter); the plug-ins your scene's nodes use are loaded for it. If something's missing in the cache, start with `bgc.shelf_click(light_background=False)`.

`worker.log` records where startup time goes, for example:
`startup: export 6s, snapshot 3s, launch 41s, plug-ins 2s, scene open 58s, setup 2s, first frames 9s (total 2:01)` and the slowest references.

When an edit makes the whole shot re-render, the Script Editor and `worker.log` say which curve and why. Keying every channel (or Delete Static Channels) no longer re-renders the shot when nothing actually changed: bgcache remembers the values of a control's unkeyed attributes when you select it.

animBot is left out of the background Maya (it can stop it loading with a startup dialog); your own Maya keeps it. Other tools can be left out the same way, in the profile's `skip_in_background` or for one session: `bgc.shelf_click(skip_in_background=("animbot", "othertool"))`.

Its windows are minimized at startup, so it stays out of your way. On some graphics setups a minimized viewport renders blank frames; the worker checks the first frames it renders, and if they're blank it restores the "bgcache render view" window and re-renders. Use `shelf_click(hide_background=False)` to keep everything visible.

After an edit, rendering starts at the frame you're on in Maya. `worker.log` records how long each edit took, e.g. `edit synced: 9 frames, first frame after 1.2s, all after 3.4s`.

## Sound

**Scrub** (toolbar) plays each frame's sound as you drag or step, like Maya's audio scrubbing.

If sound lands early or late against the picture (remote workstations add delay), open the menu on the **Sound** button and choose **Sync test**: the picture flashes white once a second with a click. Press `[` to move the sound earlier or `]` to move it later, a quarter frame at a time, until the click lands on the flash, then Esc. The offset is remembered.


The player plays the sound set on Maya's time slider (or the scene's only audio node), with its offset and trim, in sync with the picture. It restarts in step on every play, scrub and loop. M mutes. WAV (16/24/32-bit, float) and AIFF are supported. The player's top line says whether sound is on, and `player.log` says why if it isn't.

While starting, Maya's progress bar shows each step ("Exporting scene copy...", "Launching background Maya..."), then the player opens and shows "Loading scene... 0:42 (usually about 1:45)" with a spinner. If the background Maya stops, the player says so in red.

**Stop** is in the player's **bgcache** menu, with **Restart bgcache**; **Help** has **Self-test** and **Check for updates**. Updates never happen by themselves and nothing checks by itself: **Check for updates** looks only when you click it (in the studio's releases folder at a studio, otherwise on the BGCache releases page on GitHub) and shows the answer in the Help menu, e.g. "Latest: 0.9.0b3 (you have 0.9.0b2)" with **What's new** and **Update to ... and restart** (installs it in the same Maya, keeping your old copy), or "You have the latest". Closing the player window asks: **Stop bgcache**, or **Keep caching** (the background Maya carries on; the shelf button brings the player back with everything cached so far). Tick **Don't ask again** to keep your answer. Versions before 0.8.0b12 had a control panel in Maya; if your layout still has one, it closes by itself.

In the player's toolbar (they ask your Maya to do it):

- **Focus range**: to cache only the part you're working on, drag the two handles on the cache bar, or press **I** / **O** at the frame you're on (**Shift+I** / **Shift+O**: back to the shot's start / end). Frames outside the range that your edits change go red and wait; the player shows the old frames there. Double-click the bar (or **View > Clear focus range**) to cache the whole shot again; what was waiting is redone. Playback and sync still cover the whole shot.
- **Path curves**: moving the CVs of a curve that drives something (a motion path, spline IK, a wire) updates the cache by itself. Adding or removing CVs works too. Moving the whole curve (its transform, no keys): **Push selected**.
- **Refresh**: sends the display settings of the viewport looking through the shot camera (the one you last clicked only if none does) (shading mode, wireframe on shaded, x-ray, backface culling, lighting, textures, the Show menu), display layer visibility and objects you've hidden or shown (H / Shift+H) to the background Maya, then re-renders every frame. Use it after changing how the viewport looks or what's visible. Grid, HUD, controls, joints and other overlays always stay off in the cache. It also sends your camera image planes, including ones added after Start. Image planes show in the cache as they do in your Maya: Show > Image Planes is read from the viewport looking through the shot camera, and a plane you've hidden (H) or set to display None is left out (not even loaded). Changes reach the cache at Start and Refresh only, the player's own reference plane included (putting it in from the player changes your Maya; press Refresh to see it in the cache).
- **Push selected**: after changing attributes that have no keys (a space switch, a rig setting) on what's selected in your Maya. Re-renders the whole range.
- **Reload scene**: re-exports your scene and reopens it in the background Maya without relaunching it. Use it after adding characters, props, references or constraints, or changing the frame range. Cameras and continuity are kept.
- **Re-render all**: if anything looks out of sync.
- **Help > Self-test**: prints a short report in your Maya's Script Editor (see Self-test below).
- **Pause**: stops re-rendering while you block. Your edits keep reaching the background Maya and changed frames show red on the cache bar; nothing renders until **Resume**, which starts again from the frame you're on. While paused the picture has a red tint and an orange **II PAUSED** tag, and the status line shows how many frames are waiting.

The background Maya doesn't evaluate what only feeds hidden things (Maya's invisibility evaluator), so hiding a heavy character or display layer you don't need, then pressing Refresh, makes re-rendering faster as well as cleaner.

- **Stop**: shuts down the background Maya and the player.

## Keys

The player uses your own Maya hotkeys, read at Start: step a frame (Alt+, / Alt+. by default), jump to the previous/next key of your selection (, / .; in Draw mode, the previous/next drawing), play (Alt+V), go to start/end, and timeline scrub (hold K and drag). Remapped keys are followed; anything not found uses Maya's default. Space also plays. The player's own toggles keep their letters (D draw, L loop, M mute, C continuity browser, T on top, [ ] sound offset; Sync and live/reference are buttons only) unless one of your playback keys uses that letter. The Script Editor prints the keys found at each Start.

## Drawing

**Draw** (D) opens a strip on the right and turns the picture into a canvas: pen or eraser, size in pixels of the cached frame (so lines stay on the character at any window size), red/yellow/cyan/white/black plus a custom colour (the rainbow swatch: the first click opens Qt's colour picker; after that, click it to use your colour and click again to change it; it's remembered), the selected colour underlined in orange, Hold (a drawing shows until the next drawn frame), Onion skin (drawn frames before in red, after in blue, faint), **◀ Drawing / Drawing ▶** (go to the previous / next drawn frame; in Draw mode your Maya previous/next key hotkeys, , and . by default, do the same; past the last drawing it cycles back to the first), **Paper** (a slider that fades the picture towards white so drawings read better; only in Draw mode, kept while you switch Draw off and on, back to 0 at every Start), Undo / Redo (Ctrl+Z / Ctrl+Shift+Z), Clear (this frame's drawing on the active layer). Pen and eraser each keep their own size (the Size slider shows the current tool's), and a circle on the picture shows it. The eraser cuts strokes where it passes and keeps the pieces either side; hold Shift to remove whole strokes instead. With pen pressure, a light touch erases thinner. Drawing on a frame that has no drawing of its own starts a new drawn frame there; erasing on a held frame edits the drawing being held. Nothing is drawn while playing. Scrub while drawing with your timeline scrub key + drag, a middle-drag, or by dragging on the cache bar. A pen's eraser end erases; pressure is used when it reaches the workstation (over PCoIP it may arrive as a plain mouse).

Layers: your layers are under your name; the pen draws on the highlighted one (orange pen mark). Add, move up/down, delete (undoable), hide, rename by double-click, and each row's circle icon sets its opacity. The padlock locks a layer (orange, closed; the row dims): no drawing, erasing, clearing, undo/redo or deleting on it until you unlock it (grey, open). Drawings are saved per person and camera: `<drawings folder>/<user>/drawings/<camera>/layers.json`. In a studio shot the drawings folder comes from the profile's `drawings_folder` (e.g. `/projects/<show>/<shot>/maya/bgcache`); otherwise it's `<Maya project>/bgcache/<scene name>`, or `<scene folder>/bgcache/<scene name>` for a scene outside the project. The scene name leaves out its version number, so `walk_v003` and `walk_v004` share drawings. If that folder can't be written: `~/.bgcache/drawings/`. Orange ticks (the full height of the cache bar, with a dark edge) mark drawn frames; **Drawings** in the toolbar hides all drawings.

**Import** lists the other people with drawings for this shot and camera. Tick a name and they appear under their own heading, one row per layer, each with its own eye and opacity (your view only). Their layers are always locked: **Duplicate** (the copy icon on a row) copies one into your layers as "name: layer (copy)" for you to edit; their file is never touched. Tell them, and they see your layer in their Import like anyone else's.

What you see of someone stays as it is, also after closing and reopening the player, until you choose: when they save newer drawings their heading turns orange with **Update**; after updating it shows **Revert** (back to what you had) until their next update. Untick, × on the heading, or select a row and press the trash button to remove someone from your list (their files are untouched).

Import also lists drawings on your shot's other cameras (on BIRDS: `camera` and `noise_camera`), including yours. **Cache noise_camera** starts caching that camera in the background ("caching 62%", then "loaded"); you can tick people there straight away and switch with the Camera menu when you like. **Import > Blue Pencil zip** shows a Blue Pencil export over the playback.

Your drawings file gets the same permissions as the folder it's in, so everyone can read it, and a copy of it is kept once per sitting (last 20) in `history/` next to it.

**Export to Blue Pencil** writes your visible layers (and visible imported people) as a zip in Blue Pencil's own layout: one Blue Pencil layer per layer, a 2048 PNG per drawn frame placed on the camera's film gate (Blue Pencil's square is as wide as the film gate and centred on it; the cached frame is the resolution gate, rendered at overscan 1). The player then opens Maya's Blue Pencil import with the zip's path on your clipboard; pick the file there.

The cache draws characters and animation only. The environment (USD stage, gpuCache and other plug-in shapes) is never drawn, which makes caching several times faster. (An Envirs button to show it existed in 0.6.4 to 0.6.8 and was removed; it can be brought back from version history.)

Hiding the set with a display layer does not make caching faster in your own Maya either: a hidden USD stage still updates every frame.

Player keys: Space play/pause, Left/Right step, Home/End, L loop, M mute, C show/hide the shot browser, T always on top, click or drag the picture or bar to scrub. In the timeline bar, green is up to date and red is being re-rendered. Stale frames show the old image with a red border.

If your studio launches Maya through a wrapper, pass the commands:

```python
bgc.shelf_click(maya_cmd=["/path/to/maya_wrapper"], mayapy_cmd=["/path/to/mayapy_wrapper"])
```

## Self-test

One command prints a short report to read back (about 20 lines), and saves it to `~/.bgcache/selftest_<date>.txt`:

```python
import bgcache.selftest as t; t.run()
t.run(hide_selected=True)   # also time it with your selection hidden (in the background Maya only)
```

(or **Help > Self-test** in the player). It lists your Maya's evaluators and viewport settings; with bgcache running, the background Maya's evaluators and render view settings and a playblast benchmark on the camera you're viewing (1, 3, 6 and 12 frames, fitted to start-up + time per frame), repeated with the invisibility evaluator off, the frustum evaluator on (if this Maya has one) and your selection hidden; and a summary of this session's worker.log (edits synced, time to the first new frame, playblast times). Rendering stops while it runs (about a minute on a heavy rig); the cache isn't changed.

## What syncs automatically

Any edit to a time-based anim curve: moving, adding or deleting keys, value and tangent changes, curves created or deleted, undo and redo. Each edit dirties only the frames between the nearest unchanged keys on either side. Curves with cycle or linear infinity dirty the whole range.

Batches are sized by time, not by frame count. Each playblast costs a fixed start-up time plus a time per frame; bgcache measures both for each camera and picks batches that take about 0.75 s, or longer when the start-up cost is big (it stays under 40% of the batch, so single frames don't waste most of their time starting up). The background Maya can only notice a new edit between batches, so this keeps the wait short on any rig: a light rig gets batches of up to 12 frames, a heavy one smaller ones. Right after an edit, the camera you're viewing renders the frame you're on by itself first. Dragging keys is sent once, just after you let go of the mouse.

Each edit writes a line to `worker.log`, for example `edit synced: 40 frames, first frame after 0.45s, all after 9.8s (your Maya 0.12s, pickup 0.03s, apply 0.01s, first frame render 0.29s) batches 1,3,3,3,...`. "Your Maya" is the wait for you to stop editing, "pickup" the background Maya noticing, "apply" rebuilding your curves there, "first frame render" the playblast of the frame you're on.

## What doesn't (use Push selected, Re-render all, or restart)

- Unkeyed attribute changes
- Changes to the frame range, camera animation, sound, references, constraints or new objects
- Anything a tool does without touching anim curves

## Undo check

When you click Start, bgcache checks that undo is on in your Maya. If it's off, it asks whether to turn it back on. To keep undo on every time Maya starts: Windows > Settings/Preferences > Preferences > Undo, set Undo to On, then click Save.

## Costs

- Two Maya sessions: roughly double the RAM, and a second license seat.
- The background renders at about the speed the rig evaluates, so a 20-frame dirty region on a 4 fps rig takes roughly 5 to 8 seconds.

## Troubleshooting

Session files live in `$TMPDIR/maya_bgcache_<user>/<session>/`. Check `worker.log` and `player.log` there.

- **"GPU deformers failed in the background Maya"**: the background Maya uses GPU deformers when your Maya's GPU Override is on at Start; switch it in your Maya and press **Refresh** to switch it there too (worker.log says which and why). If your Maya freezes, **bgcache > Stop** in the player still stops the background Maya. If they fail there (out of graphics memory, or a rig that breaks on the GPU), it switches to the CPU, and if it got stuck it is restarted on the CPU by itself (slower, your edits are kept). If your own Maya also freezes with GPU Override on, the rig itself doesn't work on the GPU on that machine: keep GPU Override off for that shot. Profile `"background_gpu": false` keeps the background Maya on the CPU always.
- **Worker never gets past "opening scene"**: a startup dialog in the background Maya may be waiting for you. Look at that window.
- **Blank or black frames**: normally fixed automatically (see "The background Maya"). If not, start with `shelf_click(hide_background=False)` and check `worker.log`.
- **No sound**: set the sound on the time slider before Start. If the player says "no audio output", `player.log` lists what failed (Qt multimedia, then `paplay`/`aplay`).
- **Sound a little early or late**: it is restarted in sync on every play and loop, but audio devices add a small fixed latency. Tell me which way it's off.
- **"rebuilt but differs" warnings in worker.log**: the tangent round-trip isn't exact for that curve type. Send me the log line.
