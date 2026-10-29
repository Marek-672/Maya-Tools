**BGCache 0.9.0 beta 2.** Live playback for heavy Maya shots, while you keep animating. Simple edition (cache, player, drawing), Maya 2024 or later.

### New
- **Updates only when you ask.** In the player, **Help > Check for updates** looks for a newer BGCache and shows the answer right in the Help menu: the latest version and yours, **What's new**, and **Update to ... and restart**, which installs it in the same Maya and keeps your old copy. Nothing checks or installs by itself, and BGCache only goes online on that click.
- **Fixed:** the player could fail as its window opened.

### Download
| Your system | File |
|---|---|
| Windows | `bgcache-0.9.0b2-windows-simple.zip` |
| macOS (Apple Silicon; the least tested so far) | `bgcache-0.9.0b2-macos-simple.zip` |
| Linux | `bgcache-0.9.0b2-linux-simple.zip` |

### Install
1. Unzip the file for your system.
2. Drag `install_bgcache.py` into a Maya viewport and choose **Install**. No restart needed.
3. Click the new **bgcache** shelf button: the player opens. Pick a camera and it starts caching.

From this version on, you can update from the player with **Help > Check for updates**. Dragging in a new version's installer still works too.

Full list of changes: [CHANGELOG](https://github.com/Marek-672/Maya-Tools/blob/main/bgcache/CHANGELOG.md). User guide: [bgcache/README.md](https://github.com/Marek-672/Maya-Tools/blob/main/bgcache/bgcache/README.md).

**Beta:** please report anything odd in [Issues](https://github.com/Marek-672/Maya-Tools/issues/new/choose), with your Maya version, system and the logs from `~/.bgcache/logs/<newest folder>/`.
