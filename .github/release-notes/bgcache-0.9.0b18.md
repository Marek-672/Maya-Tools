**BGCache 0.9.0 beta 18.** Live playback for heavy Maya shots, while you keep animating. Maya 2024 or later.

The first release since beta 7 (betas 8 to 17 were test builds).

### New
- **The whole shot in the player, your range first.** The player lays out the whole shot, and your Maya playback range is the **focus**: rendered first, and played. Frames not rendered yet are hatched.
- **Sync with Maya's range.** With **Sync** on, the focus and Maya's playback range are the same thing, both ways. With it off they're separate, a blue line shows Maya's range, and **Match Maya** copies it once.
- **Cameras you move without keys update by themselves:** tumble a follow camera or change a focal length, and the player re-renders a moment after you stop.
- **Reference image planes placed in the scene** are followed the same way when you move or resize them.
- **Image plane opacity** slider in the shot's menu.
- **Onion skin, your count:** set how many drawings show before and after (0 to 5 each). You can type in the Draw strip's number boxes.
- **Drawings:** other people's drawings are listed under their own name, off until you switch them on. Stopping, opening another scene or quitting asks to save your drawings first.

### Fixed and steadier
- The background Maya ends at once when you stop (Maya's own quit could crash on the way out), and no longer rebuilds the panel layout saved in your scene.
- Textures are loaded before each frame is drawn.
- The player didn't open when a camera was already picked.
- The background Maya's log now has an image plane report, for when a plane looks different in the cache than in your Maya.

### Download
**Which one?** Simple if you just want your own shot playing in real time with drawing. Full adds continuity: the shots around yours playing with it. Full does everything Simple does, and continuity stays off until you set it up, so if you're unsure, take Full. **Help > About** in the player says which one you have.

Click a file to download it (they're also under **Assets** at the bottom of this page).

| Your system | Simple (cache, player, drawing) | Full (+ continuity) |
|---|---|---|
| Windows | [bgcache-0.9.0b18-windows-simple.zip](https://github.com/Marek-672/Maya-Tools/releases/download/bgcache-v0.9.0b18/bgcache-0.9.0b18-windows-simple.zip) | [bgcache-0.9.0b18-windows-full.zip](https://github.com/Marek-672/Maya-Tools/releases/download/bgcache-v0.9.0b18/bgcache-0.9.0b18-windows-full.zip) |
| macOS (Apple Silicon; the least tested so far) | [bgcache-0.9.0b18-macos-simple.zip](https://github.com/Marek-672/Maya-Tools/releases/download/bgcache-v0.9.0b18/bgcache-0.9.0b18-macos-simple.zip) | [bgcache-0.9.0b18-macos-full.zip](https://github.com/Marek-672/Maya-Tools/releases/download/bgcache-v0.9.0b18/bgcache-0.9.0b18-macos-full.zip) |
| Linux | [bgcache-0.9.0b18-linux-simple.zip](https://github.com/Marek-672/Maya-Tools/releases/download/bgcache-v0.9.0b18/bgcache-0.9.0b18-linux-simple.zip) | [bgcache-0.9.0b18-linux-full.zip](https://github.com/Marek-672/Maya-Tools/releases/download/bgcache-v0.9.0b18/bgcache-0.9.0b18-linux-full.zip) |

### Install or update
- **Already have BGCache:** in the player, **Help > Check for updates** offers the newest of your edition. To move from Simple to Full, drag in the Full zip's installer.
- **New:** unzip the file for your system, drag **`DRAG_ME_INTO_MAYA.py`** into a Maya viewport and choose **Install**, then click the **bgcache** shelf button.

Full list of changes: [CHANGELOG](https://github.com/Marek-672/Maya-Tools/blob/main/bgcache/CHANGELOG.md). User guide: [bgcache/README.md](https://github.com/Marek-672/Maya-Tools/blob/main/bgcache/bgcache/README.md).

**Beta:** problems to **Help > Report a problem > Send**, or [Issues](https://github.com/Marek-672/Maya-Tools/issues/new/choose). If BGCache saves you time, you can say thanks at [ko-fi.com/marekkochout](https://ko-fi.com/marekkochout).
