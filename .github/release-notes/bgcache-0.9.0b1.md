**BGCache 0.9.0 beta 1: the first public release.** Live playback for heavy Maya shots, while you keep animating: a hidden second Maya re-playblasts only the frames your edits change, and a player plays the shot at full speed with sound. Draw over it, too.

This is the **Simple edition** (cache, player, drawing), free for everyone. Maya 2024 or later.

### Download
| Your system | File |
|---|---|
| Windows | `bgcache-0.9.0b1-windows-simple.zip` |
| macOS (Apple Silicon; the least tested so far) | `bgcache-0.9.0b1-macos-simple.zip` |
| Linux | `bgcache-0.9.0b1-linux-simple.zip` |

### Install
1. Unzip the file for your system.
2. Drag `install_bgcache.py` into a Maya viewport and choose **Install**. No restart needed.
3. Click the new **bgcache** shelf button: the player opens. Pick a camera and it starts caching.

To update later, drag in the new version's installer the same way (your old copy is kept). The same installer uninstalls.

### What's in it
- Only changed frames are re-rendered, the frame you're on first.
- The player follows your Maya hotkeys and time slider, with sound.
- Drawing over playback: pen and eraser with tablet pressure, layers, onion skin, hold, Paper, Blue Pencil export.
- Focus range: drag the handles on the cache bar, or press I / O, to cache just the part you're working on.
- Refresh, Reload scene, Re-render all, Pause and a self-test, all in the player.
- Your scene file is never saved or changed, and your Maya preferences are never touched.

Full list of changes: [CHANGELOG](https://github.com/Marek-672/Maya-Tools/blob/main/bgcache/CHANGELOG.md). User guide: [bgcache/README.md](https://github.com/Marek-672/Maya-Tools/blob/main/bgcache/bgcache/README.md).

**Beta:** please report anything odd in [Issues](https://github.com/Marek-672/Maya-Tools/issues/new/choose), with your Maya version, system and the logs from `~/.bgcache/logs/<newest folder>/`.
