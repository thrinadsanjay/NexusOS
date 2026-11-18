"""Files: thin integration with Dolphin and KIO (no custom file manager).

Listing uses os.scandir for the in-app browser; operations go through KIO
(``kioclient``) so trash, network locations, permissions dialogs and progress
behave exactly like in Dolphin. Deletion moves items to the trash.
"""

from __future__ import annotations

import os
import stat
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote

from pydantic import BaseModel

from nexus_core import runner, validation
from nexus_core.errors import DependencyMissingError, NexusError, ValidationError


class Entry(BaseModel):
    name: str
    path: str
    is_dir: bool
    size: int
    mode: str
    mtime: float
    hidden: bool


class Place(BaseModel):
    title: str
    url: str


def list_dir(path: str, show_hidden: bool = False, limit: int = 5000) -> list[Entry]:
    p = Path(os.path.expanduser(path))
    if not p.is_dir():
        raise ValidationError(f"not a directory: {p}")
    out = []
    with os.scandir(p) as it:
        for e in it:
            if not show_hidden and e.name.startswith("."):
                continue
            try:
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            out.append(
                Entry(
                    name=e.name,
                    path=e.path,
                    is_dir=e.is_dir(),
                    size=st.st_size,
                    mode=stat.filemode(st.st_mode),
                    mtime=st.st_mtime,
                    hidden=e.name.startswith("."),
                )
            )
            if len(out) >= limit:
                break
    return sorted(out, key=lambda x: (not x.is_dir, x.name.lower()))


def places() -> list[Place]:
    """Bookmarks shared with Dolphin (~/.local/share/user-places.xbel)."""
    xbel = Path.home() / ".local" / "share" / "user-places.xbel"
    out = [Place(title="Home", url=str(Path.home()))]
    seen = {_place_key(str(Path.home()))}
    if xbel.exists():
        try:
            for bm in ET.parse(xbel).getroot().iter("bookmark"):  # noqa: S314
                href = bm.get("href", "")
                key = _place_key(href)
                if not href or key in seen:  # Dolphin's own places include Home again
                    continue
                seen.add(key)
                out.append(Place(title=bm.findtext("title") or href, url=href))
        except ET.ParseError:
            pass
    return out


_USER_DIRS = (  # Windows-Explorer-style "Quick access" (XDG user directories)
    ("DESKTOP", "Desktop", "desktop"),
    ("DOCUMENTS", "Documents", "doc"),
    ("DOWNLOAD", "Downloads", "download"),
    ("PICTURES", "Pictures", "image"),
    ("MUSIC", "Music", "music"),
    ("VIDEOS", "Videos", "video"),
)


class QuickPlace(BaseModel):
    title: str
    path: str
    icon: str


def quick_access(home: Path | None = None) -> list[QuickPlace]:
    """Home and the XDG user directories that exist (names from ~/.config/user-dirs.dirs)."""
    home = home or Path.home()
    configured: dict[str, str] = {}
    cfg = home / ".config" / "user-dirs.dirs"
    if cfg.exists():
        for line in cfg.read_text(errors="replace").splitlines():
            key, _, value = line.partition("=")
            if key.startswith("XDG_") and key.endswith("_DIR") and value:
                configured[key[4:-4]] = value.strip().strip('"').replace("$HOME", str(home))
    out = [QuickPlace(title="Home", path=str(home), icon="home")]
    for key, default, icon in _USER_DIRS:
        path = Path(configured.get(key, str(home / default)))
        if path.is_dir() and path != home:
            out.append(QuickPlace(title=path.name, path=str(path), icon=icon))
    return out


def make_folder(parent: str, name: str) -> str:
    """Create a folder in *parent*; returns its path. Never overwrites."""
    if "/" in name or name in (".", "..") or not name:
        raise ValidationError("invalid folder name")
    validation.single_line(name, max_len=255, field="name")
    target = Path(os.path.expanduser(parent)) / name
    if target.exists():
        raise ValidationError(f"{name} already exists")
    target.mkdir()
    return str(target)


def unique_name(parent: str, name: str) -> str:
    """'New folder', 'New folder (2)', … — the first name not taken in *parent*."""
    base = Path(os.path.expanduser(parent))
    candidate, n = name, 2
    while (base / candidate).exists():
        candidate, n = f"{name} ({n})", n + 1
    return candidate


def _place_key(url: str) -> str:
    """Normalise ``file:///home/a/`` and ``/home/a`` to the same key."""
    path = unquote(url[7:]) if url.startswith("file://") else url
    return (path.rstrip("/") or "/") if path.startswith("/") else url


def _detached(argv: list[str]) -> None:
    subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def open_in_dolphin(path: str) -> None:
    if runner.which("dolphin") is None:
        raise DependencyMissingError("Dolphin is not installed", hint="sudo apt install dolphin")
    _detached(["dolphin", "--new-window", os.path.expanduser(path)])


def open_file(path: str) -> None:
    _detached(["kioclient", "exec", os.path.expanduser(path)] if runner.which("kioclient") else ["xdg-open", path])


def _kio(*args: str) -> None:
    if runner.which("kioclient") is None:
        raise DependencyMissingError("kioclient (kde-cli-tools) is not installed")
    result = runner.run(["kioclient", "--noninteractive", *args], timeout=3600)
    if not result.ok:
        raise NexusError("file operation failed", hint=runner.first_line(result.stderr))


def copy(sources: list[str], destination: str) -> None:
    _kio("copy", *[os.path.expanduser(s) for s in sources], os.path.expanduser(destination))


def move(sources: list[str], destination: str) -> None:
    _kio("move", *[os.path.expanduser(s) for s in sources], os.path.expanduser(destination))


def trash(paths: list[str]) -> None:
    _kio("move", *[os.path.expanduser(p) for p in paths], "trash:/")


def rename(path: str, new_name: str) -> None:
    if "/" in new_name or new_name in (".", "..") or not new_name:
        raise ValidationError("invalid file name")
    validation.single_line(new_name, max_len=255, field="name")
    src = Path(os.path.expanduser(path))
    target = src.with_name(new_name)
    if target.exists():
        raise ValidationError(f"{target.name} already exists")
    src.rename(target)


def search(query: str, limit: int = 100) -> list[str]:
    """Indexed search via Baloo when available (respects the user's indexing settings)."""
    query = validation.single_line(query, max_len=200, field="query")
    tool = runner.which("baloosearch6") or runner.which("baloosearch")
    if not tool:
        return []
    result = runner.run([tool, "-l", str(limit), query], timeout=15)
    return [ln for ln in result.stdout.splitlines() if ln.startswith("/")][:limit]


def extract(archive: str, destination: str) -> None:
    if runner.which("ark") is None:
        raise DependencyMissingError("Ark is not installed", hint="sudo apt install ark")
    _detached(["ark", "--batch", "--destination", os.path.expanduser(destination), os.path.expanduser(archive)])


def compress(paths: list[str], archive: str) -> None:
    if runner.which("ark") is None:
        raise DependencyMissingError("Ark is not installed", hint="sudo apt install ark")
    _detached(["ark", "--batch", "--add-to", os.path.expanduser(archive), *[os.path.expanduser(p) for p in paths]])
