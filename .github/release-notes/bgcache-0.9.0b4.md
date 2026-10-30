**BGCache 0.9.0 beta 4: the Full edition.** Live playback for heavy Maya shots, while you keep animating, now with **continuity**: the shots around yours play as one reel with your live shot. Maya 2024 or later.

### New: Set up continuity
In the Full edition's player, click **Continuity** (or **bgcache > Set up continuity...**) and show it **one movie of your shot**. BGCache works out where your film keeps its footage and finds every other shot's newest version. Footage all over the place? Point it at the folders and it searches them for files named after your shots.

- Version folders or versions in file names (`v004`, `_004`, `take3`, dates); MOV, MP4 and image sequences.
- Shots read from file names, so footage doesn't need to live in shot folders.
- Drop in an edit (EDL, Final Cut / Premiere XML, FCPXML) and shots follow the cut.
- A table of every shot and department before you save. Choose any missing file by hand.
- **Teams:** shared drawings and one setup for everyone, in the project folder. Each computer says once where that folder is.
- Movies need ffmpeg. If it isn't there, **Download it for me** fetches a fixed, checked build into `~/.bgcache/ffmpeg` (only when you click).

Nothing is saved until you press Save. Pipeline TDs can still write the settings by hand ([PIPELINE_SETUP.md](https://github.com/Marek-672/Maya-Tools/blob/main/bgcache/PIPELINE_SETUP.md)).

### Also new
- **Focus range plays too:** with a focus set, Play plays and loops only those frames. The handles have tabs, so they're easy to grab at the window's edges.
- **Drawings stay on** when your shot shows a department's movie instead of Live.

### Download
**Which one?** Simple if you just want your own shot playing in real time with drawing. Full adds continuity: the shots around yours playing with it. Full does everything Simple does, and continuity stays off until you set it up, so if you're unsure, take Full. **Help > About** in the player says which one you have.

| Your system | Simple (cache, player, drawing) | Full (+ continuity) |
|---|---|---|
| Windows | `bgcache-0.9.0b4-windows-simple.zip` | `bgcache-0.9.0b4-windows-full.zip` |
| macOS (Apple Silicon; the least tested so far) | `bgcache-0.9.0b4-macos-simple.zip` | `bgcache-0.9.0b4-macos-full.zip` |
| Linux | `bgcache-0.9.0b4-linux-simple.zip` | `bgcache-0.9.0b4-linux-full.zip` |

### Install or update
- **Already have 0.9.0b2 or b3:** in the player, **Help > Check for updates** offers the newest of your edition. To move from Simple to Full, drag in the Full zip's installer.
- **New:** unzip the file for your system, drag `install_bgcache.py` into a Maya viewport and choose **Install**, then click the **bgcache** shelf button.

Full list of changes: [CHANGELOG](https://github.com/Marek-672/Maya-Tools/blob/main/bgcache/CHANGELOG.md). User guide: [bgcache/README.md](https://github.com/Marek-672/Maya-Tools/blob/main/bgcache/bgcache/README.md).

**Beta:** problems to **Help > Report a problem** and [Issues](https://github.com/Marek-672/Maya-Tools/issues/new/choose). If BGCache saves you time, you can say thanks at [ko-fi.com/marekkochout](https://ko-fi.com/marekkochout).
