"""Stand-in for animBot, used ONLY inside bgcache's background Maya.

The background Maya just renders frames; animBot's startup (and the dialog it
can pop up) would stop it loading. bgcache puts this folder first on that
Maya's Python path, so `import animBot; animBot.launch()` from userSetup.py,
a module or a plug-in finds this and does nothing. Your own Maya is untouched
and uses the real animBot.
"""


def launch(*args, **kwargs):
    print("bgcache: animBot skipped in the background Maya")


def __getattr__(name):
    return lambda *args, **kwargs: None
