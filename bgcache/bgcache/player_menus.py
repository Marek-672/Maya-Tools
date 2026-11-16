"""Player: Help > Check for updates, Help > Report a problem (with its dialog) and the camera menu.

Part of the Player (bgcache/player.py); see DEVELOPER.md."""
from bgcache.player_common import *  # noqa: F401,F403 (Qt, colours, helpers)
from bgcache.player_common import __all__ as _names
from bgcache import common, __version__  # noqa: F401


class ReportDialog(QtWidgets.QDialog):
    """Help > Report a problem: what happened, an optional email, what goes
    in the report, Hide names, then Send (if switched on) or Save report."""

    def __init__(self, parent, items, can_send):
        super(ReportDialog, self).__init__(parent)
        self.setWindowTitle("Report a problem")
        self.choice = None
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(QtWidgets.QLabel("What happened? What were you doing just before?"))
        self.text = QtWidgets.QPlainTextEdit()
        self.text.setMinimumSize(420, 110)
        lay.addWidget(self.text)
        self.mail = QtWidgets.QLineEdit()
        self.mail.setPlaceholderText("Your email, if you'd like an answer (optional)")
        lay.addWidget(self.mail)
        lay.addWidget(QtWidgets.QLabel("The report holds:"))
        listing = QtWidgets.QLabel("\n".join(["   \u2022 what you wrote above"] +
                                             ["   \u2022 %s" % name for name, _p, _t in items]))
        listing.setToolTip("\n".join(path for _n, path, _t in items if path))
        lay.addWidget(listing)
        self.b_hide = QtWidgets.QCheckBox("Hide names (show, sequence, shot, scene and your user name)")
        self.b_hide.setChecked(True)
        lay.addWidget(self.b_hide)
        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        save = QtWidgets.QPushButton("Save report...")
        save.clicked.connect(lambda: self._done("save"))
        row.addWidget(save)
        if can_send:
            send = QtWidgets.QPushButton("Send")
            send.setToolTip("Sends the report to bgcache's author (only when you click)")
            send.setDefault(True)
            send.clicked.connect(lambda: self._done("send"))
            row.addWidget(send)
        cancel = QtWidgets.QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        lay.addLayout(row)

    def _done(self, choice):
        self.choice = choice
        self.accept()

    def what(self):
        return self.text.toPlainText()

    def email(self):
        return self.mail.text()

    def hide_names(self):
        return self.b_hide.isChecked()


class MenusMixin(object):
    # ---------------------------------------------------------------- updates
    # 0.9.0b2: only when you ask (Help > Check for updates). Nothing checks or
    # installs by itself, and there's no Update button: the answer shows in the
    # Help menu. Studio builds look in the profile's releases folder, others
    # on GitHub (bgcache's only network use, and only on that click).
    def _update_source(self):
        cfg = self.cfg or {}
        if cfg.get("releases_folder"):
            return "folder"
        if cfg.get("github_releases"):
            return "github"
        return None

    def check_for_update(self):
        source = self._update_source()
        if not source:
            return None
        from bgcache import update
        install_dir = self.cfg.get("install_dir") or ""
        if source == "folder":
            result = update.check_folder(self.cfg["releases_folder"], __version__)
            result["earlier"] = update.earlier_versions(install_dir, __version__, self.cfg["releases_folder"])
            self._update_checked(result)
            return self._update_result
        from bgcache import system
        edition = "full" if self.has_continuity else "simple"
        self._show_update_lines([("Checking for updates...", None)])
        repo = self.cfg["github_releases"]

        def work():
            result = update.check_github(repo, __version__, system.NAME, edition)
            earlier = update.earlier_versions(install_dir, __version__)
            try:
                kept = {v["version"] for v in earlier}
                earlier += [v for v in update.earlier_on_github(repo, __version__, system.NAME, edition)
                            if v["version"] not in kept]
            except RuntimeError:
                pass                      # offline: the copies on this computer are still listed
            result["earlier"] = sorted(earlier, key=lambda v: update.version_key(v["version"]), reverse=True)
            return result
        self._run_in_background(work, self._update_checked)
        return None

    def _run_in_background(self, work, done):
        """work() in a thread (a network call must not freeze the player),
        then done(result) back here."""
        import threading
        box = {}

        def run():
            try:
                box["result"] = work()
            except Exception as error:       # reported as the check's answer, never raised
                box["result"] = {"state": "error", "message": str(error)}
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        timer = QtCore.QTimer(self)

        def poll():
            if not thread.is_alive():
                timer.stop()
                done(box.get("result") or {"state": "error", "message": "no answer"})
        timer.timeout.connect(poll)
        timer.start(50)

    def _update_checked(self, result):
        self._update_result = result
        state = result.get("state")
        if state == "newer":
            lines = [("Latest: %s (you have %s)" % (result["version"], __version__), None)]
            if result.get("notes"):
                lines.append(("What's new in %s" % result["version"], self.show_update_notes))
            lines.append(("Update to %s and restart" % result["version"], self.update_and_restart))
        elif state == "latest":
            lines = [("You have the latest (%s)" % __version__, None)]
        else:
            lines = [("Couldn't check: %s" % result.get("message", "unknown error"), None)]
            if result.get("page"):
                lines.append(("Open the download page", lambda: self._open_url(result["page"])))
        earlier = result.get("earlier") or []
        if earlier:                       # b6: going back, if a new version misbehaves
            lines.append(("Go back to an earlier version", [
                ("%s  (%s)" % (v["version"], v["where"]), lambda v=v: self.go_back_to(v)) for v in earlier[:12]]))
        self._show_update_lines(lines)
        QtCore.QTimer.singleShot(0, self.b_help.showMenu)     # show the answer where you asked

    def _show_update_lines(self, lines):
        """Replace the lines under Check for updates: (text, slot); no slot = a note."""
        for act in self._update_lines:
            self.help_menu.removeAction(act)
        self._update_lines = []
        for text, slot in lines:
            if isinstance(slot, list):        # a submenu: [(text, slot)]
                sub = QtWidgets.QMenu("    " + text, self.help_menu)
                for sub_text, sub_slot in slot:
                    sub.addAction(sub_text, sub_slot)
                act = sub.menuAction()
                self._update_submenus = getattr(self, "_update_submenus", []) + [sub]
            else:
                act = _QAction("    " + text, self.help_menu)
                if slot is None:
                    act.setEnabled(False)
                else:
                    act.triggered.connect(lambda checked=False, fn=slot: fn())
            self.help_menu.insertAction(self._update_sep, act)
            self._update_lines.append(act)

    # ---------------------------------------------------------------- reports
    def report_problem(self):
        """Help > Report a problem: what you write, plus the logs, in one zip.
        You see the list first. Send only when the profile has reports_url."""
        from bgcache import report
        edition = "full" if self.has_continuity else "simple"
        items = report.gather(self.session, self.cfg, __version__, edition)
        dialog = ReportDialog(self, items, bool((self.cfg or {}).get("reports_url")))
        (getattr(dialog, "exec", None) or dialog.exec_)()
        if not dialog.choice:
            return None
        names = report.names_to_hide(self.cfg) if dialog.hide_names() else None
        data = report.build(items, dialog.what(), dialog.email(), names)
        name = report.file_name(__version__)
        if dialog.choice == "send":
            self._flash_message("Sending the report...")
            self._run_in_background(
                lambda: dict(zip(("ok", "message"), report.send(self.cfg["reports_url"], data, name, __version__))),
                self._report_sent)
            return "send"
        start = os.path.join((self.cfg or {}).get("reports_folder") or os.path.expanduser("~"), name)
        path = QtWidgets.QFileDialog.getSaveFileName(self, "Save report", start, "Zip (*.zip)")[0]
        if path:
            report.save(data, path)
            self._flash_message("Report saved: %s" % os.path.basename(path))
        return path

    def _report_sent(self, result):
        self._flash_message(result.get("message") or "Couldn't send the report")
        if not result.get("ok"):
            print("bgcache player: report %s (use Help > Report a problem > Save report...)" % result.get("message"))

    def _open_url(self, url):
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))

    def show_update_notes(self):
        result = getattr(self, "_update_result", None) or {}
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle("What's new in bgcache %s" % result.get("version", ""))
        box.setText(result.get("notes") or "")
        if hasattr(Qt, "MarkdownText"):            # the release notes are Markdown (Qt 5.14+)
            box.setTextFormat(Qt.MarkdownText)
        go = box.addButton("Update and restart", QtWidgets.QMessageBox.AcceptRole)
        box.addButton("Close", QtWidgets.QMessageBox.RejectRole)
        box.exec_() if hasattr(box, "exec_") else box.exec()
        if box.clickedButton() is go:
            self.update_and_restart()

    def update_and_restart(self):
        """Your Maya stops bgcache, swaps in the new copy (the old one is
        kept in .bgcache_backups) and starts it again, without restarting Maya."""
        result = getattr(self, "_update_result", None) or {}
        if result.get("state") != "newer":
            return
        if result.get("zip"):                     # studio releases folder
            self._send_update(result["version"], result["zip"])
            return
        from bgcache import update
        self._flash_message("Downloading bgcache %s..." % result["version"], 30.0)
        folder = self.p.get("tmp") or os.path.join(self.session, "tmp")
        self._run_in_background(lambda: {"state": "ok", "path": update.download(result["zip_url"], folder,
                                                                                result["zip_name"])},
                                lambda got: self._send_update(result["version"], got.get("path"))
                                if got.get("state") == "ok" else
                                self._flash_message("Update didn't download: %s" % got.get("message"), 8.0))

    def go_back_to(self, item):
        """b6: Help > Check for updates > Go back to an earlier version: put
        that version back the way an update installs (the copy you leave is
        kept, so Check for updates can bring it back)."""
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle("bgcache")
        box.setText("Go back to bgcache %s?" % item["version"])
        box.setInformativeText("You have %s. It's kept, and Check for updates can bring it back. "
                               "bgcache restarts; your Maya doesn't." % __version__)
        go = box.addButton("Go back to %s" % item["version"], QtWidgets.QMessageBox.AcceptRole)
        box.addButton("Cancel", QtWidgets.QMessageBox.RejectRole)
        (getattr(box, "exec", None) or box.exec_)()
        if box.clickedButton() is not go:
            return False
        from bgcache import update
        folder = self.p.get("tmp") or os.path.join(self.session, "tmp")
        if item.get("path"):                   # a copy kept on this computer
            self._send_update(item["version"], update.zip_backup(item["path"], folder))
        elif item.get("zip"):                  # the studio's releases folder
            self._send_update(item["version"], item["zip"])
        else:                                  # GitHub
            self._flash_message("Downloading bgcache %s..." % item["version"], 30.0)
            self._run_in_background(
                lambda: {"state": "ok", "path": update.download(item["zip_url"], folder, item["zip_name"])},
                lambda got: self._send_update(item["version"], got.get("path")) if got.get("state") == "ok"
                else self._flash_message("Didn't download: %s" % got.get("message"), 8.0))
        return True

    def _send_update(self, version, path):
        self.send_cmd("update", path=path)
        self._close_quietly = True
        self._flash_message("Updating bgcache to %s: it reopens in a moment" % version, 10.0)

    def _window_height(self):
        return 28 + 40 + 600 + BAR_H + 40 + self._continuity_height()


    # ---------------------------------------------------------------- camera menu
    def _fill_camera_menu(self):
        self.cam_menu.clear()
        cams = self.cfg.get("cameras") or []
        if not cams:
            act = self.cam_menu.addAction("No shot camera in this scene")
            act.setEnabled(False)
            return
        for cam in cams:
            name = cam["name"]
            w = QtWidgets.QWidget()
            row = QtWidgets.QHBoxLayout(w)
            row.setContentsMargins(10, 3, 10, 3)
            row.setSpacing(8)
            box = QtWidgets.QCheckBox()
            box.setStyleSheet(_checkbox_style())
            box.setCursor(Qt.PointingHandCursor)
            box.setChecked(name in self.checked)
            box.setToolTip("Cache this camera")
            box.toggled.connect(lambda on, n=name: self._set_checked(n, on))
            pick = QtWidgets.QPushButton(cam["label"])
            pick.setFlat(True)
            pick.setStyleSheet("text-align: left; border: none; background: transparent; font-size: 13px; "
                               "color: %s; font-weight: %s" % ("#f0f0f0" if name in self.checked else "#9a9a9a",
                                                                "bold" if name == self.view else "normal"))
            pick.clicked.connect(lambda _=False, n=name: self._view_camera(n))
            state = "viewing" if name == self.view else ("cached" if name in self.checked else "off")
            tag = QtWidgets.QLabel(state)
            tag.setStyleSheet("font-size: 11px; color: %s" % ("#cfe0f0" if state == "viewing" else "#8a8a8a"))
            row.addWidget(box)
            row.addWidget(pick, 1)
            row.addWidget(tag)
            w.setMinimumWidth(260)
            act = QtWidgets.QWidgetAction(self.cam_menu)
            act.setDefaultWidget(w)
            self.cam_menu.addAction(act)

    def _set_checked(self, cam, on):
        if on and cam not in self.checked:
            self.checked.append(cam)
            if not self.view:
                self.view = cam
        elif not on and cam in self.checked:
            self.checked.remove(cam)
            for d in (self.data, self.loaded, self.dirty):
                d.pop(cam, None)
            for k in [k for k in self.lru if k[0] == "live" and k[1] == cam]:
                del self.lru[k]
            if self.view == cam:
                self.view = self.checked[0] if self.checked else None
        self._save_cameras()

    def _view_camera(self, cam):
        if cam not in self.checked:
            self.checked.append(cam)       # picking a camera by name also caches it
        self.view = cam
        self.cam_menu.hide()
        self._save_cameras()
        self.drawer.changed()          # drawings are per camera

    def _save_cameras(self):
        # b8: focus_from "maya" when the focus followed your Maya's range: your
        # Maya doesn't apply it back (a late echo would undo a range you're dragging)
        common.write_json_atomic(self.p["cameras"], {"checked": self.checked, "view": self.view,
                                                     "focus": list(self.focus_range) if self.focus_range else None,
                                                     "focus_from": getattr(self, "_focus_from", "player")})
