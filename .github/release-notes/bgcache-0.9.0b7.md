**BGCache 0.9.0 beta 7.** Live playback for heavy Maya shots, while you keep animating. Maya 2024 or later.

### Fixed
- **No shelf button after installing:** for some people (with shelf buttons from other tools that hold Python code instead of text), the installer stopped before making the bgcache button. Fixed: the button now goes on its own **bgcache** shelf tab, and the install message says where it is. If you already have the button, it's updated where it is.
- **Maya froze at "Loading scene" (Linux and macOS):** when Maya was started from a terminal in the background (`maya &`), the terminal could pause Maya as BGCache started. The second Maya and the player now start apart from the terminal, so this can't happen.

Also in here, from beta 6: **Go back to an earlier version** in Help > Check for updates, and one file to drag to install (`DRAG_ME_INTO_MAYA.py`). From beta 5: more footage formats in continuity. From beta 4: the Full edition with **Set up continuity**.

### Download
**Which one?** Simple if you just want your own shot playing in real time with drawing. Full adds continuity: the shots around yours playing with it. Full does everything Simple does, and continuity stays off until you set it up, so if you're unsure, take Full. **Help > About** in the player says which one you have.

Click a file to download it (they're also under **Assets** at the bottom of this page).

| Your system | Simple (cache, player, drawing) | Full (+ continuity) |
|---|---|---|
| Windows | [bgcache-0.9.0b7-windows-simple.zip](https://github.com/Marek-672/Maya-Tools/releases/download/bgcache-v0.9.0b7/bgcache-0.9.0b7-windows-simple.zip) | [bgcache-0.9.0b7-windows-full.zip](https://github.com/Marek-672/Maya-Tools/releases/download/bgcache-v0.9.0b7/bgcache-0.9.0b7-windows-full.zip) |
| macOS (Apple Silicon; the least tested so far) | [bgcache-0.9.0b7-macos-simple.zip](https://github.com/Marek-672/Maya-Tools/releases/download/bgcache-v0.9.0b7/bgcache-0.9.0b7-macos-simple.zip) | [bgcache-0.9.0b7-macos-full.zip](https://github.com/Marek-672/Maya-Tools/releases/download/bgcache-v0.9.0b7/bgcache-0.9.0b7-macos-full.zip) |
| Linux | [bgcache-0.9.0b7-linux-simple.zip](https://github.com/Marek-672/Maya-Tools/releases/download/bgcache-v0.9.0b7/bgcache-0.9.0b7-linux-simple.zip) | [bgcache-0.9.0b7-linux-full.zip](https://github.com/Marek-672/Maya-Tools/releases/download/bgcache-v0.9.0b7/bgcache-0.9.0b7-linux-full.zip) |

### Install or update
- **Already have BGCache:** in the player, **Help > Check for updates** offers the newest of your edition. To move from Simple to Full, drag in the Full zip's installer.
- **New:** unzip the file for your system, drag **`DRAG_ME_INTO_MAYA.py`** into a Maya viewport and choose **Install**, then click the **bgcache** shelf button.

Full list of changes: [CHANGELOG](https://github.com/Marek-672/Maya-Tools/blob/main/bgcache/CHANGELOG.md). User guide: [bgcache/README.md](https://github.com/Marek-672/Maya-Tools/blob/main/bgcache/bgcache/README.md).

**Beta:** problems to **Help > Report a problem > Send**, or [Issues](https://github.com/Marek-672/Maya-Tools/issues/new/choose). If BGCache saves you time, you can say thanks at [ko-fi.com/marekkochout](https://ko-fi.com/marekkochout).
