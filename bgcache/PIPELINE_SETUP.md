# bgcache: pipeline setup

**How bgcache talks to Maya** (processes, files, callbacks, what it never touches): see `bgcache/HOW_IT_WORKS.md`.

For pipeline TDs. bgcache works without any setup: drawings go next to the
scene (or in the Maya project), and the continuity strip stays off. To turn
on continuity and shared drawings, you describe your studio's folder layout
in one JSON file, the **pipeline profile**. No code changes.

## Where bgcache looks for the profile

First found wins:

1. the file named by the `BGCACHE_PROFILE` environment variable (handy per show: set it in the show's Maya launcher);
2. `profile.json` inside the installed `bgcache` folder (ship it with your studio build);
3. `~/.bgcache/profile.json` (a user's own);
4. otherwise the built-in generic profile.

Start from `profiles/example_studio.json`. Paths always use forward slashes,
on Windows too. Keys starting with `_` are notes and are ignored. Keys you
leave out keep their default.

## Templates

`{show}`, `{sequence}` and `{shot}` are filled in from the scene's path;
`departments` and `drawings_folder` can also use `{shot_folder}`. Any other
`{name}` in `shot_folder` (for example `{episode}`) is captured from the path
and can be used in the other templates too.

## Keys

| Key | What it does | Default |
|---|---|---|
| `shot_folder` | Where one shot's folder is, e.g. `/projects/{show}/shots/{shot}`. A scene saved anywhere inside it belongs to that shot: that turns on continuity and the shared drawings folder. | `""` (no shots) |
| `sequence_from_shot` | When `shot_folder` has no `{sequence}`: read it from the shot name. `{sequence}_*` = everything before the first `_` (`sq010_0040` is in `sq010`). | `"{sequence}_*"` |
| `drawings_folder` | Where everyone's drawings for a shot go, e.g. `{shot_folder}/review/bgcache`. Each person writes only their own file under it. | `""`: next to the scene, or `<Maya project>/bgcache/<scene name>` |
| `departments` | Footage the continuity strip can show, one entry per department: `name`, `base_path` (folder holding the versions), `version_pattern` (version folder names, `*` = anything, ending `_v<number>`), `source_type` (`image_sequence` or `single_movie`, a `.mov` in the version folder). | `[]` |
| `departments_file` | Optional JSON file with its own `departments` list (and `ffmpeg_path`) that replaces the one above, e.g. a file shared with another tool. Only read. | `""` |
| `auto_order` | Auto picks the first department with footage, in this order; departments not listed follow in their listed order. | `[]` |
| `movie_slate_frames` | Department movies start with this many slate frames. A movie exactly that much longer than the shot has them skipped. | `0` |
| `assume_slate_when_unknown` | When the shot's length is unknown: skip the slate frames anyway (`true`) or play the movie as is. | `false` |
| `skip_in_background` | Tools left out of the hidden Maya, matched against its script, module and plug-in folders. Tools with startup dialogs hang a hidden Maya. | `["animbot"]` |
| `switch_off_in_background` | Tools switched off inside the hidden Maya only: `{"if_scriptjob_contains": "...", "call": "package.module.function"}` calls the function whenever a matching script job is running. | `[]` |
| `maya_wrappers` | Studio wrapper commands that start Maya, tried on the PATH after the usual places. | `[]` |
| `sound_preference` | Several sound tracks in a scene and none picked on the time slider: which to play, matched in the sound node's name, e.g. `["_mix_"]` for the full mix before stems. Otherwise the first track that isn't muted. | `[]` |
| `background_gpu` | GPU deformers in the hidden Maya (much faster than the CPU). `"follow"`: when your own Maya has GPU Override on. `"always"`: even when yours has it off (for shots that switch it off when they open). `false`: always the CPU. If they fail there (out of graphics memory, or a rig that breaks on the GPU), bgcache switches that Maya to the CPU by itself, restarting it if it got stuck, and says so. | `"follow"` |
| `background_viewport_renderer` | The hidden Maya draws the cache with the same viewport renderer as your shot camera's view: Viewport 2.0, plus your studio's render override if the view uses one. `false`: always Maya's standard Viewport 2.0. | `true` |
| `before_playblast` | Your studio's own playblast set-up, run in the hidden Maya once its render view is made: `"module.function"` (called with the panel name, or with no arguments). | `""` |
| `viewport_plugins` | Plug-ins that provide your studio's viewport render override, loaded in the hidden Maya (plug-ins with "viewport" in their name are found by themselves). | `[]` |
| `releases_folder` | Studio only: a folder of release zips (`bgcache_<version>.zip`, `bgcache/` at the top). **Help > Check for updates** looks here (only when the artist clicks it: nothing checks or installs by itself) and offers **Update and restart** (no Maya restart, no installer). When set, it's the only place looked at. The installed copy must be in a folder the artist can write to (the drag-and-drop install is). | `""` |
| `github_releases` | Without a releases folder, **Help > Check for updates** asks this GitHub repository for the newest bgcache release (bgcache's only network use, and only on that click). Set it to `""` to switch the check off, e.g. on machines without internet. | `"Marek-672/Maya-Tools"` |
| `ffmpeg` | ffmpeg's location, if it isn't on the PATH (only needed for movies and for sound at a different sample rate). | `""` |

## Checking a profile without Maya

```
python3 tools/check_profile.py <folder containing bgcache> <profile.json> <scene path>
```

It prints the shot it finds, the sequence's shots, Auto's department order,
the footage found for each department and where drawings go.

## If your studio has its own playblast tool or viewport renderer

Many studios playblast through their own tool, and some draw their viewports
with their own Viewport 2.0 render override. That matters for bgcache: the
hidden Maya playblasts every cached frame. At one studio a plain
`cmds.playblast` crashed Maya, and the standard Viewport 2.0 was about 16
times slower than the studio's renderer.

- **The renderer is copied by itself:** at Start, bgcache reads the renderer
  and render override of the viewport looking through the shot camera and
  uses the same in the hidden Maya, loading the plug-in that provides it
  (plug-ins with "viewport" in their name, or those in `viewport_plugins`).
  `worker.log` says which renderer it used ("viewport renderer: vp2Renderer
  with ..."). `background_viewport_renderer: false` goes back to the standard
  Viewport 2.0.
- **Anything else your playblast tool prepares** (freeing texture memory,
  switching viewport effects off, colour management, lens settings): put it
  in a function and name it in `before_playblast`. It runs once in the hidden
  Maya after its render view is made, and is given the panel's name.
- **To find what your tool does:** in the Script Editor turn on History >
  Echo All Commands, run the studio playblast, and note the command it runs.
  Then `inspect.getsourcefile(<module>)` shows where its code is.
- **To check the result:** compare `worker.log`'s "rendered N frames in X s"
  lines with your own Maya's playback speed on the same shot. A big gap
  usually means the hidden Maya isn't drawing the way your playblast does.
- **If the cache comes out wrong (grey, no textures, odd shading) while the
  artist's viewport looks right,** your render override may not draw
  correctly in a hidden Maya. Test it for one session in the artist's Script
  Editor: `import bgcache.profile as p; p.load()["background_viewport_renderer"] = False`,
  then Stop and Start bgcache. If the cache is right with the standard
  Viewport 2.0, set `"background_viewport_renderer": false` in the profile
  (correct but slower), or fix it in your `before_playblast` hook. This is a
  pipeline setting on purpose: artists don't get a menu switch for it.
- **Studio-only code** (your own viewport commands, say) goes in a file of its
  own, e.g. `studio_private/studio_<name>.py`, named in `before_playblast` as
  `"bgcache.studio_<name>.prepare"`. `tools/build_studio.py` builds it into
  your studio's zips only.

## Things to know

- **userSetup.py in the hidden Maya:** bgcache starts it with
  `MAYA_SKIP_USERSETUP_PY=1` and `BGCACHE_BACKGROUND=1`. If your studio
  setup opens ports or starts services from other startup scripts, check for
  `BGCACHE_BACKGROUND` and skip them there.
- **Licences:** the hidden Maya is a second Maya session. On network licences,
  check whether it takes a seat.
- **Shared installs:** put the module folder on a shared drive and add it to
  `MAYA_MODULE_PATH` in your launcher; ship your `profile.json` inside the
  `bgcache` folder.
- **Known limits:** versions must be folders ending `_v<number>` (versioned
  files side by side aren't found); movies must be `.mov`; neighbouring shots
  are in name order, not cut order.
