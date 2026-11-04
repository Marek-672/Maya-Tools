bgcache: install folder

  >>>  To install or update: drag DRAG_ME_INTO_MAYA.py into a Maya viewport.  <<<

That's the only file artists need. It shows what you have and the newest
build, and offers:
    Install <newest>     the usual choice
    Other version...     any build in releases/
    Roll back            what you had before your last install
Going back to an older build asks first. Nothing is ever deleted: the copy you
had is kept in ~/maya/<version>/scripts/.bgcache_backups/. Stop bgcache before
dropping it. It installs for the Maya you drop it into.

After the first install, updates come from the player: Help > Check for
updates (it looks in this folder's releases/).

What's here:
    DRAG_ME_INTO_MAYA.py   drag into Maya (keep it in this folder, next to releases/)
    releases/              every build, bgcache_<version>.zip; add a build by dropping its zip in
    for_pipeline/          the same install from a terminal, for pipeline TDs (artists can ignore it)

FROM A TERMINAL (close Maya first), in for_pipeline/:
    ./install                    installs the newest build in releases/
    ./install --list             every build, and which one you have
    ./install --version 0.9.0b5  installs that exact build
    ./install --rollback         puts back what you had before your last install
    ./install --maya 2025        for another Maya version (default 2024)
Both ways install to the same place and share the same backups.
