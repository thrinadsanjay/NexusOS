"""Terminal & SSH workspace: Konsole tabs, SSH profiles, credentials, host keys and SFTP."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from nexus_center.base import ModuleController
from nexus_core import terminal
from nexus_core.ssh import hostkeys, profiles, sessions
from nexus_core.ssh.credentials import CredentialManager
from nexus_core.ssh.sftp import SFTPSession
from PySide6.QtCore import Slot


class Controller(ModuleController):
    def __init__(self, tasks, app=None) -> None:
        super().__init__(tasks, app)
        self._sftp: SFTPSession | None = None
        self._transfer_cancel = threading.Event()
        self.set(
            profiles=[],
            recent=[],
            groups=list(profiles.GROUPS),
            credentials=[],
            history=[],
            hostkeys=[],
            remote=[],
            remotePath=".",
            transfers=[],
            layouts=[],
            credentialsError="",
        )

    @Slot()
    def refresh(self) -> None:
        def load() -> dict:
            out = {
                "profiles": profiles.list_profiles(),
                "recent": profiles.recent(),
                "history": profiles.history(30),
                "layouts": terminal.layouts(),
            }
            try:
                out["credentials"] = CredentialManager().list()
                out["credentialsError"] = ""
            except Exception as exc:
                out["credentialsError"] = str(exc)
            return out

        self.run(load, lambda d: self.set(**d))

    # ------------------------------------------------------------ local terminal
    @Slot(str, str, str)
    def openTerminal(self, shell: str, workdir: str, title: str) -> None:
        tab = terminal.TerminalTab(shell=shell or "default", workdir=workdir or "~", title=title or "Terminal")
        self.run(lambda: terminal.open_terminal(tab), lambda _: None, record=("terminal.open", workdir or "~"))

    # ------------------------------------------------------------ profiles
    @Slot(str)
    def saveProfile(self, profile_json: str) -> None:
        data = json.loads(profile_json)
        if not data.get("id"):
            data.pop("id", None)
        self.run(
            lambda: profiles.save(profiles.SSHProfile(**data)),
            lambda p: (self.toast.emit("success", f"saved {p.name}"), self.refresh()),
            record=("ssh.profile.save", data.get("name", "?")),
        )

    @Slot(str)
    def deleteProfile(self, profile_id: str) -> None:
        self.run(
            lambda: profiles.delete(profile_id), lambda _: self.refresh(), record=("ssh.profile.delete", profile_id)
        )

    @Slot(str)
    def connect(self, profile_id: str) -> None:
        self.run(lambda: sessions.connect(profile_id), lambda _: self.refresh(), record=("ssh.connect", profile_id))

    @Slot(str)
    def scanHostKey(self, profile_id: str) -> None:
        def scan() -> dict:
            p = profiles.get(profile_id)
            return {
                "hostkeys": hostkeys.scan(p.host, p.port),
                "hostKnown": hostkeys.is_known(p.host, p.port),
                "hostkeysFor": profile_id,
            }

        self.run(scan, lambda d: self.set(**d))

    @Slot()
    def trustHostKeys(self) -> None:
        keys = [hostkeys.HostKey(**k) for k in self._data.get("hostkeys", [])]
        self.run(
            lambda: hostkeys.trust(keys),
            lambda _: (self.set(hostKnown=True), self.toast.emit("success", "host key trusted")),
            record=("ssh.hostkey.trust", self._data.get("hostkeysFor", "")),
        )

    # ------------------------------------------------------------ credentials (Secret Service)
    @Slot(str, str, str, str, int)
    def saveCredential(self, ref: str, kind: str, secret: str, username: str, rotate_days: int) -> None:
        self.run(
            lambda: CredentialManager().save(ref, kind, secret, username, rotate_days or None),
            lambda _: (self.toast.emit("success", f"credential '{ref}' saved to the wallet"), self.refresh()),
            record=("credential.save", ref),
        )

    @Slot(str)
    def deleteCredential(self, ref: str) -> None:
        self.run(lambda: CredentialManager().delete(ref), lambda _: self.refresh(), record=("credential.delete", ref))

    # ------------------------------------------------------------ SFTP
    @Slot(str)
    def sftpOpen(self, profile_id: str) -> None:
        def open_() -> dict:
            if self._sftp:
                self._sftp.close()
            self._sftp = SFTPSession(profiles.get(profile_id))
            return {"remote": self._sftp.listdir("."), "remotePath": "."}

        self.run(open_, lambda d: self.set(**d))

    @Slot(str)
    def sftpList(self, path: str) -> None:
        if self._sftp:
            self.run(lambda: {"remote": self._sftp.listdir(path), "remotePath": path}, lambda d: self.set(**d))

    @Slot(str)
    def sftpMkdir(self, path: str) -> None:
        if self._sftp:
            self.run(lambda: self._sftp.mkdir(path), lambda _: self.sftpList(self._data["remotePath"]))

    @Slot(str, str)
    def sftpRename(self, old: str, new: str) -> None:
        if self._sftp:
            self.run(lambda: self._sftp.rename(old, new), lambda _: self.sftpList(self._data["remotePath"]))

    @Slot(str)
    def sftpDelete(self, path: str) -> None:
        if self._sftp:
            self.run(
                lambda: self._sftp.delete(path, confirmed=True),
                lambda _: self.sftpList(self._data["remotePath"]),
                record=("sftp.delete", path),
            )

    def _transfer(self, kind: str, src: str, dst: str) -> None:
        self._transfer_cancel.clear()
        name = Path(src).name

        def work(emit, cancel):
            fn = self._sftp.download if kind == "download" else self._sftp.upload
            args = (src, Path(dst)) if kind == "download" else (Path(src), dst)
            fn(*args, progress=lambda done, total: emit({"done": done, "total": total}), cancel=self._transfer_cancel)
            return name

        def progress(ev):
            self.set(transfers=[{"name": name, "kind": kind, **ev}])

        self.run(
            work,
            lambda _: (self.set(transfers=[]), self.sftpList(self._data["remotePath"])),
            progress=progress,
            record=(f"sftp.{kind}", name),
        )

    @Slot(str, str)
    def sftpDownload(self, remote: str, local_dir: str) -> None:
        if self._sftp:
            self._transfer("download", remote, str(Path(local_dir.replace("file://", "")) / Path(remote).name))

    @Slot(str, str)
    def sftpUpload(self, local_file: str, remote_dir: str) -> None:
        if self._sftp:
            local = local_file.replace("file://", "")
            self._transfer("upload", local, f"{remote_dir.rstrip('/')}/{Path(local).name}")

    @Slot()
    def cancelTransfer(self) -> None:
        self._transfer_cancel.set()

    @Slot()
    def deactivate(self) -> None:
        super().deactivate()
        if self._sftp:  # free the SSH connection when the page is hidden
            self._sftp.close()
            self._sftp = None
            self.set(remote=[])
