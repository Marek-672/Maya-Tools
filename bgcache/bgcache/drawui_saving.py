"""Drawing in the player: Save (Ctrl+S), the unsaved dot, recovery copies, versions and asking to save.

Part of drawui.py (the Drawer and the drawing strip); see DEVELOPER.md."""
from bgcache.drawui_common import *  # noqa: F401,F403 (Qt, drawing, profile, colours)


class SavingMixin(object):
    # ------------------------------------------------------------ saving (0.9.0b3)
    # Changes stay on your screen until Save (Ctrl+S); a private recovery copy
    # follows every change, so a crash loses almost nothing.
    RECOVERY_DELAY_MS = 400

    def edited(self):
        """A change to your drawings: unsaved until Save; recovery copy soon."""
        mine = self.mine_now()
        if mine is None:
            return
        mine.dirty = True
        if self.recovery_timer is not None:
            self.recovery_timer.start(self.RECOVERY_DELAY_MS)
        else:
            self.write_recovery()
        if self.panel is not None:
            self.panel.refresh_save()

    def write_recovery(self):
        for mine in self.mine.values():
            mine.write_recovery()

    def unsaved(self):
        """Cameras with unsaved drawings."""
        return [cam for cam, mine in self.mine.items() if mine.dirty]

    def save_now(self):
        """Save: your drawings go to the shared file, a new version. Returns
        True if everything was saved."""
        ok, warned = True, False
        for cam, mine in list(self.mine.items()):
            if not mine.dirty:
                continue
            error = mine.save()
            if error and not mine.path.startswith(self._fallback_of(cam)):
                mine.path = drawing.layers_path(self._fallback_of(cam), self.user, self._folder_of(cam))
                error2 = mine.save()
                if not self.saved_warned or error2:
                    self.saved_warned = warned = True
                    self.player._flash_message(
                        "Couldn't save in the shot folder (%s); saved in your home folder" % error
                        if not error2 else "Couldn't save drawings: %s" % error2, 6.0)
                ok = ok and not error2
            elif error:
                ok = False
                warned = True
                self.player._flash_message("Couldn't save drawings: %s" % error, 6.0)
        if ok and not warned:
            self.player._flash_message("Drawings saved", 2.0)
        if self.panel is not None:
            self.panel.refresh_save()
        self.player.canvas.update()
        return ok

    def ask_to_save(self, parent, doing="closing", cancel=True):
        """Before Stop or closing with unsaved drawings: Save / Don't save /
        Cancel. True to carry on (saved or discarded), False to cancel.
        cancel=False (b8: your Maya is changing scene, which can't wait):
        no Cancel; closing the box keeps the recovery copy for next time."""
        if not self.unsaved():
            return True
        box = QtWidgets.QMessageBox(parent)
        box.setWindowTitle("bgcache")
        box.setText("Save your drawings before %s?" % doing)
        box.setInformativeText("Nobody else sees them until you save.")
        save = box.addButton("Save", QtWidgets.QMessageBox.AcceptRole)
        drop = box.addButton("Don't save", QtWidgets.QMessageBox.DestructiveRole)
        if cancel:
            box.addButton("Cancel", QtWidgets.QMessageBox.RejectRole)
        box.setDefaultButton(save)
        (getattr(box, "exec", None) or box.exec_)()
        clicked = box.clickedButton()
        if clicked is save:
            return self.save_now()
        if clicked is drop:
            for mine in self.mine.values():
                if mine.dirty:
                    mine.clear_recovery()
                    mine.dirty = False
            return True
        return not cancel         # no Cancel: carry on (the recovery copy stays)

    def offer_recovery(self, cam):
        """Unsaved drawings left by a session that ended without Save (a
        crash): offer them back, once, when that camera's drawings open."""
        mine = self.mine.get(cam)
        data = mine.recovery() if mine is not None else None
        if not data:
            return
        when = time.strftime("%a %H:%M", time.localtime(data.get("written") or time.time()))
        box = QtWidgets.QMessageBox(self.player)
        box.setWindowTitle("bgcache")
        box.setText("Unsaved drawings from %s were found (%s)." % (when, cam))
        box.setInformativeText("bgcache kept them when the last session ended without Save. "
                               "Recover them? They stay unsaved until you press Save.")
        rec = box.addButton("Recover", QtWidgets.QMessageBox.AcceptRole)
        box.addButton("Discard", QtWidgets.QMessageBox.DestructiveRole)
        (getattr(box, "exec", None) or box.exec_)()
        if box.clickedButton() is rec:
            mine.recover(data)
            self.changed()
            if self.panel is not None:
                self.panel.refresh_save()
        else:
            mine.clear_recovery()

    def restore_version(self, path):
        mine = self.mine_now()
        if mine is None:
            return
        error = mine.restore(path)
        self.player._flash_message("Couldn't restore: %s" % error if error else "Earlier drawings restored and saved",
                                   5.0 if error else 3.0)
        self.changed()
        if self.panel is not None:
            self.panel.refresh_save()
