"""bgcache: background, dirty-frame-only playback cache for heavy Maya shots.

Three pieces:
    controller.py  runs in the Maya you animate in. Watches key edits, works out
                   which frames they affect, and sends the changes to the worker.
    worker.py      runs in a second Maya. Mirrors your key edits and playblasts
                   only the dirty frames, in small chunks, in the background.
    player.py      a standalone flipbook (run with mayapy) that plays the frames
                   at full speed with sound, lets you choose which cameras to
                   cache, and reloads frames as they are re-rendered.
    audio.py       sound loading and playback for the player.
    drawing.py, drawui.py  drawing over the player.
    profile.py     pipeline profile: where a studio's shots, footage and
                   shared drawings are (optional; works without one).
    continuity/    add-on (bgcache Full): neighbour shots before and after
                   yours, each department's footage. Leave the folder out
                   for bgcache Simple.
    update.py      Help > Check for updates: the profile's releases_folder,
                   or GitHub releases; Update and restart
    install.py     one-step shelf button: import bgcache.install; bgcache.install.shelf()

Usage, inside your animation Maya:
    import bgcache.controller as bgc
    bgc.shelf_click()
"""
__version__ = "0.9.0b3"
