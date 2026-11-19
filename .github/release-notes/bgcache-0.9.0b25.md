**BGCache 0.9.0 beta 25.** Live playback for heavy Maya shots, while you keep animating. Maya 2024 or later.

### New since beta 22
- **Hiding and showing in Maya is followed by itself.** Ctrl+H, Shift+H and switching a display layer update the player without pressing Refresh.
- **Animation layers.** Muting, soloing or changing a layer's weight updates the player by itself. Make a new layer after Start and the orange note appears; Refresh asks to reload the scene so the layer's keys are followed (before, they were silently missing).
- The player's **Show** and **Hide** buttons are now **Show selected** and **Hide selected**.

### Fixed
- The player could stop following your Maya for the rest of a session (cameras moved without keys, things hidden or shown), with key edits arriving five seconds late, when Maya wrongly believed a mouse button was still held.

### Download
**Which one?** Simple if you just want your own shot playing in real time with drawing. Full adds continuity: the shots around yours playing with it. Full does everything Simple does, and continuity stays off until you set it up, so if you're unsure, take Full. **Help > About** in the player says which one you have.

Click a file to download it (they're also under **Assets** at the bottom of this page).

| Your system | Simple (cache, player, drawing) | Full (+ continuity) |
|---|---|---|
| Windows | [bgcache-0.9.0b25-windows-simple.zip](https://github.com/Marek-672/Maya-Tools/releases/download/bgcache-v0.9.0b25/bgcache-0.9.0b25-windows-simple.zip) | [bgcache-0.9.0b25-windows-full.zip](https://github.com/Marek-672/Maya-Tools/releases/download/bgcache-v0.9.0b25/bgcache-0.9.0b25-windows-full.zip) |
| macOS (Apple Silicon; the least tested so far) | [bgcache-0.9.0b25-macos-simple.zip](https://github.com/Marek-672/Maya-Tools/releases/download/bgcache-v0.9.0b25/bgcache-0.9.0b25-macos-simple.zip) | [bgcache-0.9.0b25-macos-full.zip](https://github.com/Marek-672/Maya-Tools/releases/download/bgcache-v0.9.0b25/bgcache-0.9.0b25-macos-full.zip) |
| Linux | [bgcache-0.9.0b25-linux-simple.zip](https://github.com/Marek-672/Maya-Tools/releases/download/bgcache-v0.9.0b25/bgcache-0.9.0b25-linux-simple.zip) | [bgcache-0.9.0b25-linux-full.zip](https://github.com/Marek-672/Maya-Tools/releases/download/bgcache-v0.9.0b25/bgcache-0.9.0b25-linux-full.zip) |

### Install or update
- **Already have BGCache:** in the player, **Help > Check for updates** offers the newest of your edition. To move from Simple to Full, drag in the Full zip's installer.
- **New:** unzip the file for your system, drag **`DRAG_ME_INTO_MAYA.py`** into a Maya viewport and choose **Install**, then click the **bgcache** shelf button.

Full list of changes: [CHANGELOG](https://github.com/Marek-672/Maya-Tools/blob/main/bgcache/CHANGELOG.md). User guide: [bgcache/README.md](https://github.com/Marek-672/Maya-Tools/blob/main/bgcache/bgcache/README.md).

**Beta:** problems to **Help > Report a problem > Send**, or [Issues](https://github.com/Marek-672/Maya-Tools/issues/new/choose). If BGCache saves you time, you can say thanks at [ko-fi.com/marekkochout](https://ko-fi.com/marekkochout).
