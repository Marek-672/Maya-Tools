bgcache installer

Every build lives in releases/ as bgcache_<version>.zip. To add a new build,
drop its zip into releases/; nothing else changes.

THE EASY WAY: drag drag_into_maya.py into a Maya viewport.
  It shows what you have and the newest build, and offers:
    Install <newest>     the usual choice
    Other version...     any build in releases/, e.g. 0.7.5
    Roll back            what you had before your last install
  Going back to an older build asks first. Nothing is ever deleted: the copy
  you had is kept in ~/maya/<version>/scripts/.bgcache_backups/.
  Stop bgcache before dropping it. It installs for the Maya you drop it into.
  Keep drag_into_maya.py in this folder, next to releases/.

FROM A TERMINAL (close Maya first), in this folder:

    ./install                    installs the newest build in releases/
    ./install --list             every build here, and which one you have
    ./install --version 0.7.5    installs that exact build
    ./install --rollback         puts back what you had before your last install
    ./install --maya 2025        for another Maya version (default 2024)

Both ways install to the same place and share the same backups, so you can
mix them.

The first line it prints says which version and zip it used, e.g.
    Installing bgcache 0.8.0b7 from .../releases/bgcache_0.8.0b7.zip

Version order: 0.7.5, then test builds 0.8.0b1, 0.8.0b2, ..., then 0.8.0.
