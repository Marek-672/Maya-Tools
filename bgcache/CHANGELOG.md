# Changelog

## 0.9.0 beta 23

- The player's **Show** and **Hide** buttons are now **Show selected** and
  **Hide selected**, so it's plain they act on what's selected in your Maya.

## 0.9.0 beta 22

Everything since beta 7 (betas 8 to 21 were test builds and weren't published).

- **One Refresh.** The top bar's cache buttons are down to Refresh and Pause.
  When the player doesn't match your Maya, press Refresh: it sends what's
  different (viewport settings, things shown or hidden, values you changed
  without a key) and says what it sent, or that nothing was different. If
  the scene itself changed (a reference added or removed, something
  imported, a constraint made), an orange note shows next to Refresh, and
  Refresh asks before reloading the scene, in the player: **Reload scene**
  or **Not now**. Push selected is gone; Reload scene is in the bgcache menu
  and Re-render all in Help.
- **The background Maya starts from its own clean settings** (Maya's
  defaults plus your graphics and colour settings), not a copy of yours, so
  your panels, layouts and start-up scripts never open in it. No splash, and
  no full-screen window flashing up at Start.
- **Show and Hide.** Select something in your Maya and press **Hide selected** to
  leave it out of the player (a character in your way), or **Show selected** to bring
  it back. Only the player changes. An arrow beside the button lists what
  you've hidden, so nothing goes missing without an explanation; click a name
  to put it back. It's for the working session only: Stop forgets it.
- **The whole shot in the player, your range first.** The player lays out
  the whole shot (Maya's outer range, the ends of the range slider) and your
  playback range is the **focus**: rendered first and played. Frames not
  rendered yet are hatched.
- **Sync with Maya's range.** With Sync on, the focus and your Maya's
  playback range are the same thing, both ways: drag either. With Sync off
  they're separate, a blue line shows Maya's range, and **Match Maya** copies
  it once. I and O set the focus.
- **Cameras you move without keys update by themselves:** a follow camera
  you tumble through, or a new focal length. A moment after you stop, the
  player re-renders. No more select the camera and Push selected.
- **Reference image planes placed in the scene** (not on a camera) are
  followed the same way when you move or resize them.
- **Image plane opacity** slider in the shot's menu, for the reference plane
  in your Maya.
- **Onion skin, your count:** Before and After boxes (0 to 5 drawings each,
  counted in drawings, not frames; the nearest is the strongest). You can
  type in the Draw strip's number boxes, and their arrows can be seen.
- **Drawings:** other people's drawings are listed under their own name, off
  until you switch them on, with a dot and Update when they've saved newer
  ones. Stop, opening another scene or quitting asks to save your drawings
  first. A drawing outside the frames you have never shows, held or not.
  With continuity (Full) and a drawings folder in the pipeline profile, you
  can draw on the shots around yours.
- **Steadier background Maya:** it ends at once when you stop (Maya's own
  quit could crash on the way out); it no longer rebuilds the panel layout
  saved in your scene (Graph Editor, Outliner...); textures are loaded before
  each frame is drawn; and its log now has an image plane report (what each
  plane loaded, and the render settings), for when a plane looks different
  in the cache than in your Maya.
- **Fixed:** the player didn't open when a camera was already picked; the
  shot stayed long after you closed your range again; a clearer message when
  the open scene isn't in a shot folder.
- A test tool, `tools/maya_torture.py`: runs bgcache through 34 things a
  user might do, or do by accident, in a real Maya and writes a report.
- For pipelines: `cache_assets` leaves your environment groups out of the
  cache; `shot_range_env` in the profile gives the shot's cut from
  your launcher's environment variables; a `before_playblast` hook's returned
  lines are written to the background Maya's log. See PIPELINE_SETUP.md.

## 0.9.0 beta 7

- **Fixed: no shelf button after installing** for some people: a shelf
  button made by another tool (holding Python code rather than text) stopped
  the installer before it made bgcache's. The button now goes on its own
  **bgcache** shelf tab (an existing bgcache button is updated where it is).
- **Fixed (Linux and macOS): Maya froze at "Loading scene"** when it was
  started from a terminal in the background (`maya &`): the second Maya and
  the player are now started apart from the terminal, so it can't pause them.

## 0.9.0 beta 6

- **Go back to an earlier version:** if a new version misbehaves, Help > Check
  for updates lists the earlier versions you can return to (kept on your
  computer, or from GitHub). The version you leave is kept too.
- **Install: one file to drag.** In the download, drag `DRAG_ME_INTO_MAYA.py`
  into Maya (it used to be called install_bgcache.py). Nothing else changes.

## 0.9.0 beta 5

- **More footage formats in continuity:** AVI, MKV, MXF, WebM and other movies
  ffmpeg plays, and image sequences in EXR, DPX, TGA and more (EXR and DPX
  are read through ffmpeg).

## 0.9.0 beta 4

- **The Full edition is out:** continuity, the strip of shots around yours,
  played as one reel with your shot.
- **Set up continuity** (the setup wizard): show it one movie of your shot
  and it learns where your film keeps its footage. Or point it at folders and
  it searches them for files named after your shots. It works with version
  folders or versions in file names (v004, _004, take3, dates), MOV, MP4 and
  image sequences, and shots read from file names. Add an edit (EDL or XML)
  and shots follow the cut.
- **Teams:** shared drawings and one setup for everyone, in the project
  folder; each computer says once where that folder is.
- **ffmpeg:** if movies need it and it isn't there, "Download it for me"
  fetches a fixed, checked build into ~/.bgcache/ffmpeg (only on that click).
- **Focus range plays too:** with a focus set, Play plays (and loops) only
  those frames, with a FOCUS tag on the picture. The handles have tabs, so
  they're easy to see and grab even at the window's edges.
- **Drawings stay on** when your shot shows a department's movie instead of
  Live, and you can keep drawing there.

## 0.9.0 beta 3

- **Drawings are shared when you save, not as you draw (changed).** Your
  drawings stay yours until you click **Save drawings** at the bottom of the
  Draw panel, or press **Ctrl+S**. Until then the panel says "Unsaved" and
  the DRAW tag on the picture shows a dot. Stopping or closing the player
  asks whether to save.
- **Drawing history:** each save keeps the drawings before it (the newest
  10). **History...** lists them; **Restore** puts one back.
- **Recovery:** an unsaved copy is kept while you draw, so after a crash
  BGCache offers your unsaved drawings back.
- **Help > Report a problem:** describe what happened; the logs, versions
  and Self-test are added, and you see the list first. **Hide names** keeps
  scene and user names out. Save the report and attach it to a GitHub issue.
- **Fixed:** a camera that sees nothing no longer leaves the hidden Maya's
  window showing.
- For studios: continuity footage with the version in the file name, and
  .mp4; the releases folder can be a list of folders.

## 0.9.0 beta 2

- **Updates only when you ask:** Help > Check for updates looks for a newer
  BGCache (on GitHub, or in a studio's releases folder) and shows the answer
  right in the Help menu: the latest version and yours, What's new, and
  Update and restart, which installs it in the same Maya and keeps your old
  copy. Nothing checks or installs by itself, and BGCache goes online only on
  that click. The orange Update button is gone.
- **Fixed:** the Simple edition's player could fail as its window opened.

## 0.9.0 beta 1 (first public release)

The Simple edition (cache, player, drawing) for everyone. Changes since the
0.8.0 betas, which were tested in production:

- **The player opens first** and shows what's happening while your scene is
  copied and the hidden Maya starts.
- **New toolbar:** menus first (bgcache, View, Help), then the camera, Draw,
  Refresh / Reload scene / Re-render all, and Pause. Loop, Sound and Sync sit
  with the playback buttons.
- **Focus range:** drag the handles on the cache bar, or press I / O at the
  frame you're on (Shift+I / Shift+O reset an end; double-click the bar to
  clear), to cache only that part of the shot. Playback still covers the
  whole shot, and Maya's time slider isn't touched.
- **Path curves:** moving the CVs of a curve that drives a motion path, spline
  IK or wire now updates the cache, also when CVs are added or removed.
- **The cache looks like your shot camera's viewport** (shading, textures,
  lights, the Show menu, image planes and the viewport renderer), read at
  Start, Refresh and Reload scene. Image planes reach the cache at Start and
  Refresh.
- **Textures:** the hidden Maya reloads its textures once its view is set up,
  and at every Refresh.
- **GPU deformers follow your Maya's GPU Override,** and Refresh sends a
  change. If they fail in the hidden Maya, it moves to the CPU by itself (or
  is restarted on the CPU, with a message and a timer in the player).
- **Stop works even when your Maya is frozen.**
- **Lighter:** less file writing while your Maya plays, and the hidden Maya
  checks for work less often when it's idle.
- **Studios:** an Update button and Update and restart from a studio releases
  folder; a `before_playblast` hook and the studio's viewport renderer
  copied to the hidden Maya; fixes to updating in place.
- **Clean-up:** the code is split by topic, with no function over 80 lines,
  and every place that carries on past an error says why. New pages:
  `bgcache/HOW_IT_WORKS.md` (how the three processes talk to each other) and
  `bgcache/DEVELOPER.md` (a code map).

## 0.8.0 beta (b12)

First public beta. bgcache started as an in-house tool (0.1 to 0.7, Linux,
one studio's folder layout written into the code); 0.8 is the same tool made
general:

- **One codebase, two editions:** Simple (cache, player, drawing) and Full
  (plus the continuity add-on).
- **Pipeline profiles:** everything studio-specific in one JSON file
  (shot folders, departments, drawings folder, tools switched off in the
  hidden Maya, sound track preference, GPU use). Checked against the
  in-house version on real shots: identical results.
- **Windows, Linux and macOS** (macOS untested), Maya 2024 and later,
  PySide2 and PySide6.
- **Drag-and-drop installer** (Maya module, every Maya version, Update keeps
  the old copy, Uninstall).
- Drawing: Paper, stepping through drawings, clearer drawn-frame marks.
- Continuity: versions per department, pinning, newer-footage marker.
- Sound converted to whatever the output device takes (sample rate, mono or
  stereo); several sound tracks in a scene handled.
- Warnings instead of silent stalls: GPU deformers failing (caching moves to
  the CPU, restarting the hidden Maya if it got stuck), caching stuck. The hidden
  Maya uses the GPU only when your Maya does.
- Updates install without restarting Maya.
- Everything in one window: the shelf button starts BGCache and opens the
  player; Stop, Restart and Self-test are in the player (and on the shelf
  button's right-click menu); closing the player asks whether to keep caching.
- Your camera image planes (and the player's reference movie as an image
  plane) show in the cache.
- Continuity: check for newer footage now, reload a shot's footage, refresh all.
- Gentler sync with your Maya; textures loaded before the first frames draw;
  the panel stays when docked, goes when floating.
