"""Local terminals: launched in Konsole (tabs, split panes, search, themes, shortcuts and
output export are Konsole features). NexusOS never implements a terminal emulator."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from pydantic import BaseModel, Field

from nexus_core import validation
from nexus_core.errors import DependencyMissingError, ValidationError
from nexus_core.store import Store, default_store

SHELLS = {"bash": "/bin/bash", "zsh": "/usr/bin/zsh"}


class TerminalTab(BaseModel):
    title: str = "Terminal"
    workdir: str = "~"
    shell: str = "default"
    command: list[str] | None = None
    konsole_profile: str = "Nexus"


class SessionLayout(BaseModel):
    name: str
    tabs: list[TerminalTab] = Field(default_factory=list)
    ssh_profile_ids: list[str] = Field(default_factory=list)


def konsole_argv(tab: TerminalTab, new_tab: bool = True) -> list[str]:
    if shutil.which("konsole") is None:
        raise DependencyMissingError("Konsole is not installed", hint="sudo apt install konsole")
    title = validation.single_line(tab.title, max_len=80, field="title")
    workdir = Path(os.path.expanduser(tab.workdir))
    if not workdir.is_dir():
        raise ValidationError(f"working directory does not exist: {workdir}")
    argv = ["konsole"]
    if new_tab:
        argv.append("--new-tab")
    argv += [
        "--workdir",
        str(workdir),
        "-p",
        f"tabtitle={title}",
        "--profile",
        validation.display_name(tab.konsole_profile),
    ]
    command = tab.command
    if command is None and tab.shell != "default":
        if tab.shell not in SHELLS:
            raise ValidationError(f"unsupported shell {tab.shell!r}")
        command = [SHELLS[tab.shell], "-l"]
    if command:
        argv += ["-e", *command]
    return argv


def launch(argv: list[str]) -> int:
    proc = subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return proc.pid


def open_terminal(tab: TerminalTab) -> int:
    return launch(konsole_argv(tab))


def save_layout(layout: SessionLayout, store: Store | None = None) -> None:
    store = store or default_store()
    layouts = store.get_setting("terminal.layouts", {}) or {}
    layouts[validation.display_name(layout.name)] = layout.model_dump()
    store.set_setting("terminal.layouts", layouts)


def layouts(store: Store | None = None) -> list[SessionLayout]:
    store = store or default_store()
    return [SessionLayout(**v) for v in (store.get_setting("terminal.layouts", {}) or {}).values()]


def export_note() -> str:
    return json.dumps({"hint": "Use Konsole: File > Save Output As… to export terminal output."})
