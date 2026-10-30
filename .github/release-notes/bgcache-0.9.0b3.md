**BGCache 0.9.0 beta 3.** Live playback for heavy Maya shots, while you keep animating. Simple edition (cache, player, drawing), Maya 2024 or later.

### Changed: drawings are kept when you save
- Your drawings stay yours until you click **Save drawings** at the bottom of the Draw panel, or press **Ctrl+S**. Undo and redo work as before. While something is unsaved the panel says so and the DRAW tag on the picture shows a dot. Stopping or closing the player asks whether to save.
- **History:** each save keeps the drawings before it (the newest 10). **History...** lists them; **Restore** puts one back.
- **Recovery:** an unsaved copy is kept while you draw, so after a crash BGCache offers your unsaved drawings back.

### New
- **Help > Report a problem:** describe what happened; the logs, versions and Self-test are added, and you see the list first. **Hide names** keeps scene and user names out. Save the report and attach it to an [issue](https://github.com/Marek-672/Maya-Tools/issues/new/choose).
- **Fixed:** a camera that sees nothing no longer leaves the hidden Maya's window showing.

### Download
| Your system | File |
|---|---|
| Windows | `bgcache-0.9.0b3-windows-simple.zip` |
| macOS (Apple Silicon; the least tested so far) | `bgcache-0.9.0b3-macos-simple.zip` |
| Linux | `bgcache-0.9.0b3-linux-simple.zip` |

### Install or update
- **Already have 0.9.0b2:** in the player, **Help > Check for updates > Update to 0.9.0b3 and restart**.
- **New:** unzip the file for your system, drag `install_bgcache.py` into a Maya viewport and choose **Install**, then click the **bgcache** shelf button.

Full list of changes: [CHANGELOG](https://github.com/Marek-672/Maya-Tools/blob/main/bgcache/CHANGELOG.md). User guide: [bgcache/README.md](https://github.com/Marek-672/Maya-Tools/blob/main/bgcache/bgcache/README.md).

If BGCache saves you time, you can say thanks at [ko-fi.com/marekkochout](https://ko-fi.com/marekkochout).
