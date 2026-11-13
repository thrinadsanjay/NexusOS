"""SFTP file browsing and transfers via Paramiko (lazy import), honouring known_hosts.

Host keys are verified against ~/.ssh/known_hosts with RejectPolicy: unknown hosts
must be trusted through the host-key flow first. Credentials come from the Secret
Service and are never logged.
"""

from __future__ import annotations

import stat
import threading
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from pydantic import BaseModel

from nexus_core.errors import DependencyMissingError, NexusError, ValidationError
from nexus_core.ssh import hostkeys
from nexus_core.ssh.credentials import CredentialManager
from nexus_core.ssh.profiles import SSHProfile


class RemoteEntry(BaseModel):
    name: str
    path: str
    is_dir: bool
    size: int
    mode: str
    mtime: float


class TransferCancelled(NexusError):
    pass


class SFTPSession:
    def __init__(self, profile: SSHProfile, credentials: CredentialManager | None = None, client=None) -> None:
        self.profile = profile
        self.credentials = credentials
        self._client = client
        self._sftp = client.open_sftp() if client is not None else None

    def connect(self) -> None:
        try:
            import paramiko
        except ImportError as exc:
            raise DependencyMissingError(
                "python3-paramiko is required for SFTP", hint="sudo apt install python3-paramiko"
            ) from exc
        if self.profile.jump_profile_id:
            raise NexusError(
                "SFTP through jump hosts is not supported yet",
                hint="open an SSH session and use `sftp -J` in the terminal",
            )
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        if hostkeys.known_hosts_file().exists():
            client.load_host_keys(str(hostkeys.known_hosts_file()))
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        kwargs = {
            "hostname": self.profile.host,
            "port": self.profile.port,
            "username": self.profile.user,
            "timeout": 15,
            "allow_agent": self.profile.auth == "agent",
            "look_for_keys": False,
        }
        creds = self.credentials or CredentialManager()
        if self.profile.auth == "key":
            kwargs["key_filename"] = str(Path(self.profile.key_path or "").expanduser())
            if self.profile.credential_ref:
                kwargs["passphrase"] = creds.secret(self.profile.credential_ref)
        elif self.profile.auth == "password":
            kwargs["password"] = creds.secret(self.profile.credential_ref or "")
        try:
            client.connect(**kwargs)
        except paramiko.SSHException as exc:
            raise NexusError(
                f"SFTP connection failed: {exc.__class__.__name__}",
                hint="is the host key trusted and the credential correct?",
            ) from None
        self._client, self._sftp = client, client.open_sftp()

    @property
    def sftp(self):
        if self._sftp is None:
            self.connect()
        return self._sftp

    def listdir(self, path: str = ".") -> list[RemoteEntry]:
        path = self._clean(path)
        entries = []
        for attr in self.sftp.listdir_attr(path):
            mode = attr.st_mode or 0
            entries.append(
                RemoteEntry(
                    name=attr.filename,
                    path=str(PurePosixPath(path) / attr.filename),
                    is_dir=stat.S_ISDIR(mode),
                    size=attr.st_size or 0,
                    mode=stat.filemode(mode),
                    mtime=float(attr.st_mtime or 0),
                )
            )
        return sorted(entries, key=lambda e: (not e.is_dir, e.name.lower()))

    def mkdir(self, path: str) -> None:
        self.sftp.mkdir(self._clean(path))

    def rename(self, old: str, new: str) -> None:
        self.sftp.rename(self._clean(old), self._clean(new))

    def delete(self, path: str, *, confirmed: bool) -> None:
        if not confirmed:
            raise ValidationError("deleting remote files requires confirmation")
        path = self._clean(path)
        if path in ("/", ".", ""):
            raise ValidationError("refusing to delete the remote root or working directory")
        if stat.S_ISDIR(self.sftp.stat(path).st_mode or 0):
            self.sftp.rmdir(path)  # only empty directories
        else:
            self.sftp.remove(path)

    def download(
        self,
        remote: str,
        local: Path,
        progress: Callable[[int, int], None] | None = None,
        cancel: threading.Event | None = None,
    ) -> None:
        self.sftp.get(self._clean(remote), str(local), callback=self._callback(progress, cancel))

    def upload(
        self,
        local: Path,
        remote: str,
        progress: Callable[[int, int], None] | None = None,
        cancel: threading.Event | None = None,
    ) -> None:
        if not local.is_file():
            raise ValidationError(f"not a file: {local}")
        self.sftp.put(str(local), self._clean(remote), callback=self._callback(progress, cancel))

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
        self._client = self._sftp = None

    @staticmethod
    def _clean(path: str) -> str:
        if "\x00" in path or "\n" in path:
            raise ValidationError("invalid remote path")
        return path

    @staticmethod
    def _callback(progress, cancel):
        def cb(done: int, total: int) -> None:
            if cancel is not None and cancel.is_set():
                raise TransferCancelled("transfer cancelled")
            if progress:
                progress(done, total)

        return cb
