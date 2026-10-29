"""0.8.0b14: the player's toolbar after the toolbar/menu guidelines (menus
first: bgcache, View, Help; then camera, Draw, the three cache buttons, Pause;
Loop/Sound/Sync with the playback buttons; one Continuity switch on the strip,
Update footage beside it); image planes as in your Maya."""
import os, re
TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
p = open(os.path.join(REPO, "bgcache", "player.py")).read()
bar = p[p.index("    def _build_ui(self):"):p.index("    def _build_playback_toggles(self):")]
order = [bar.index(x) for x in ('_menu_word(row, "bgcache"', '_menu_word(row, "View"', '_menu_word(row, "Help"',
                                'self.cam_button = _tool', 'self.b_draw = _tool', 'self.b_refresh = _tool',
                                'self.b_reload = _tool', 'self.b_rerender = _tool', 'self.b_pause = _tool')]
assert order == sorted(order), order
print("ok: toolbar order: bgcache, View, Help menus, then camera, Draw, Refresh, Reload scene, Re-render all, Pause")
for gone in ('menu_button("Cache"', '"Scene"', 'MenuButtonPopup', 'QLabel("Camera")', '_tool("Scrub"',
             '_tool("Stop"', '_tool("Gate"', '_tool("Drawings"'):
    assert gone not in bar, gone
print("ok: no Cache/Scene menu, no split button (Sound is a plain on/off), no extra Camera label")
menus = {"bgcache": ("Push selected", "Restart bgcache", "Stop bgcache"),
         "View": ("Film gate", "Show drawings", "Keep on top", "Sound while scrubbing", "Sync test", "Reset sound offset"),
         "Help": ("Self-test", "Check for updates", "About bgcache")}
for name, items in menus.items():
    chunk = bar[bar.index('_menu_word(row, "%s"' % name):]
    nxt = re.search(r'_menu_word\(row, "(?!%s)' % name, chunk[10:])
    chunk = chunk[:nxt.start() + 10] if nxt else chunk
    for item in items:
        assert item in chunk, (name, item)
assert "Sync test..." not in bar and "Sync test…" not in bar
print("ok: bgcache: Push selected, Restart, Stop | View: Film gate, Show drawings, Keep on top, Sound section | "
      "Help: Self-test, Check for updates, About")
tr = p[p.index("    def _build_transport(self):"):p.index("    # ---------------------------------------------------------------- updates")]
assert "for b in (self.b_loop, self.b_sound, self.b_sync):" in tr
print("ok: Loop, Sound and Sync sit with the playback buttons at the bottom")
assert "QToolButton:checked { background: #3d6a8f; border-color: #8fc0e8;" in p
print("ok: lit buttons have a bright outline as well as the colour")
u = open(os.path.join(REPO, "bgcache", "continuity", "ui.py")).read()
assert 'self.switch = _tool("Continuity", True' in u and "self.b_cont = self.browser.switch" in u
assert '"""b14: nothing on the toolbar; the Continuity switch is on the strip\'s header."""\n        return []' in u
assert '_tool("Update footage"' in u and '"Update this shot\'s footage"' in u and '"Refresh all"' not in u
assert "self.browser.setVisible(True)" in u and "return 26 + (116 if self.browser_open and self.continuity_on else 0)" in u
print("ok: one Continuity switch, on the strip's header (always there, lit when on); Update footage next to it")
