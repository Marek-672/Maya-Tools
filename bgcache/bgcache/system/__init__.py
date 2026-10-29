"""What differs between Windows, macOS and Linux, in one place per system:

    linux.py    the studio's original behaviour, unchanged
    windows.py  maya.exe / mayapy.exe, no console windows, Windows process
                checks, file-lock retries
    macos.py    Maya.app paths

Every system file provides the same functions:

    find_maya(extra_names=())   the Maya program to start the background Maya with
    find_mayapy()               mayapy, for the player window
    pid_alive(pid)              is that process still running?
    hidden_console()            subprocess options so console programs
                                (mayapy, ffmpeg) open no window
    retrying(fn)                fn(), retried briefly where the system can
                                refuse a file another program has open

The rest of bgcache imports `from bgcache import system` and calls these;
nothing else checks which system it's on. No Maya imports here.
"""
import sys

if sys.platform.startswith("win"):
    from bgcache.system import windows as _impl
elif sys.platform == "darwin":
    from bgcache.system import macos as _impl
else:
    from bgcache.system import linux as _impl

NAME = _impl.NAME
find_maya = _impl.find_maya
find_mayapy = _impl.find_mayapy
pid_alive = _impl.pid_alive
hidden_console = _impl.hidden_console
retrying = _impl.retrying
