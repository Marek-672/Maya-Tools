# Changelog

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
