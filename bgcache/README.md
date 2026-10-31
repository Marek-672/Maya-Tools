# BGCache

**Live playback for heavy Maya shots, while you keep animating.** Part of MK Anim Tools.

![The BGCache player](docs/player.png)

Heavy rigs can't play in real time in Maya, so you playblast again and again
to see your timing. BGCache does that for you, in the background: a second,
hidden Maya mirrors your key edits and re-playblasts **only the frames those
edits change**, the frame you're on first. A separate player window plays the
result at full speed, with sound. Edit a key, and a moment later you see it
play in real time.

Made by an animator for animators. Free and open source (MIT).

> **Beta.** BGCache is used daily on heavy production shots, but this is its
> first public release. Please report anything odd (see below).

## What you get

- **Playback that keeps up:** only changed frames are re-rendered, current
  frame first. A key edit shows up in a fraction of a second.
- **Your Maya, your keys:** the player follows your own Maya hotkeys (step
  frame, step key, play, scrub) and stays in sync with Maya's time slider.
- **Drawing over playback:** pen and eraser (with tablet pressure), layers,
  onion skin, hold, Paper (fades the picture so drawings read), stepping
  through drawings, export to Maya's Blue Pencil. Drawings are kept when you
  **Save** (Ctrl+S), with a history of the last 10 saves and a recovery copy
  if anything crashes.
- **Continuity (Full edition):** the shots around yours, from any
  department's movies or image sequences, play as one reel with your live
  shot. **Set up continuity** learns where your film keeps its footage from
  one movie you drop in (or searches your folders for it), and can follow the
  cut from an EDL or XML. Works for one person or a team.
- **Focus range:** drag two handles on the cache bar (or press I / O) to cache
  only the part you're working on.
- **Refresh, Reload scene, Re-render all, Pause**, a self-test, and clear
  warnings when something needs you (for example the graphics card running
  out of memory).
- **Safe:** your scene file is never saved or changed by BGCache, and the
  hidden Maya has its own preferences folder, so yours are never touched.

## Requirements

- Maya **2024 or later**.
- **Windows** (tested with Maya 2027), **Linux** (used daily with Maya 2024) or
  **macOS** (tested on Apple Silicon with Maya 2025; less tested than the others).
- Enough memory for a second Maya with your scene open. On network licences,
  check with your IT whether the second (hidden) Maya takes a licence seat.

## Install

1. Download the zip for your system from the
   [Releases](https://github.com/Marek-672/Maya-Tools/releases) page and unzip it:
   `bgcache-<version>-<system>-simple.zip` (cache, player, drawing) or
   `bgcache-<version>-<system>-full.zip` (the same plus continuity).
2. Drag `install_bgcache.py` into a Maya viewport and choose **Install**.
3. Click the new **bgcache** shelf button: BGCache starts and the player opens.
   Pick a camera in the player and it starts caching.
4. Full edition: click **Continuity** in the player and show it one movie of
   your shot (see [the guide](bgcache/README.md#setting-up-continuity-the-setup-wizard-090b4)).

It installs as a Maya module in your own Maya folder (every Maya 2024+ finds
it). It never edits `userSetup.py` or `Maya.env`. Drag it in again to
**Update** (no restart needed; your old copy is kept) or **Uninstall**.

The user guide is [bgcache/README.md](bgcache/README.md).

## Reporting a problem

In the player, **Help > Report a problem**: write what happened (and an email
if you'd like an answer), then **Send**. It goes straight to me, with your
versions and system, the session's logs and the newest Self-test (**Help >
Self-test** first makes it more useful). You see the list before anything is
sent, and **Hide names** (on) keeps scene and user names out. Prefer GitHub?
**Save report...** and attach the zip to an
[issue](https://github.com/Marek-672/Maya-Tools/issues/new/choose).

## Support

BGCache is free. If it saves you time and you'd like to say thanks, you can
buy me a coffee at [ko-fi.com/marekkochout](https://ko-fi.com/marekkochout).

## Studios and pipeline TDs

Everything studio-specific lives in one JSON **pipeline profile**: where shots
live, where drawings are shared, which tools to switch off in the hidden Maya,
GPU use, a releases folder for studio-wide updates. No code changes. See
[PIPELINE_SETUP.md](PIPELINE_SETUP.md) and `profiles/example_studio.json`.
How the three processes talk to each other (files only: no network, no
ports): [bgcache/HOW_IT_WORKS.md](bgcache/HOW_IT_WORKS.md). Where things live
in the code: [bgcache/DEVELOPER.md](bgcache/DEVELOPER.md).

A TD can also run **Set up continuity** once on a real shot and ship the
settings file it writes, instead of writing a profile by hand.

## Tests

`python3 tests/run_tests.py` runs the automatic checks (no Maya needed: Maya
and Qt are stubbed). They run on Windows, macOS and Linux on every change.
Live testing is done in Maya.

## Licence

MIT, see [LICENSE](LICENSE). Copyright (c) 2026 Marek Kochout.
