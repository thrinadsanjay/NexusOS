"""Unified system settings: native operations through polkit-protected systemd services,
and KDE System Settings modules (KCMs) for mature desktop functionality.

NexusOS does not reimplement display, audio, input, Bluetooth, printing or user
management: the Command Center opens the corresponding KCM via ``kcmshell6``.
Hostname, time zone, NTP and locale use hostnamed/timedated/localed, which ask polkit.
"""

from __future__ import annotations

import grp
import pwd
import subprocess
from pathlib import Path

from pydantic import BaseModel

from nexus_core import runner, validation
from nexus_core.errors import DependencyMissingError, NexusError, ValidationError


class SettingsEntry(BaseModel):
    id: str
    category: str
    title: str
    keywords: list[str]
    kcm: str | None = None  # KDE module to open
    native: str | None = None  # Command Center native page/section


# Every KCM listed here was verified to exist in Ubuntu 26.04 Plasma 6.6 packages.
CATALOG: list[SettingsEntry] = [
    SettingsEntry(
        id="theme",
        category="Personalization",
        title="Global theme",
        keywords=["theme", "look and feel"],
        kcm="kcm_lookandfeel",
    ),
    SettingsEntry(
        id="colors",
        category="Personalization",
        title="Colours and accent",
        keywords=["accent", "color", "colour"],
        kcm="kcm_colors",
    ),
    SettingsEntry(
        id="wallpaper",
        category="Personalization",
        title="Wallpaper",
        keywords=["background", "wallpaper"],
        kcm="kcm_wallpaper",
    ),
    SettingsEntry(
        id="fonts", category="Personalization", title="Fonts", keywords=["font", "typography"], kcm="kcm_fonts"
    ),
    SettingsEntry(
        id="appearance",
        category="Personalization",
        title="Application style",
        keywords=["style", "widgets"],
        kcm="kcm_style",
    ),
    SettingsEntry(
        id="display",
        category="Hardware",
        title="Display, resolution and scaling",
        keywords=["display", "monitor", "resolution", "scale"],
        kcm="kcm_kscreen",
    ),
    SettingsEntry(
        id="nightlight",
        category="Personalization",
        title="Night light",
        keywords=["night", "blue light"],
        kcm="kcm_nightlight",
    ),
    SettingsEntry(
        id="users",
        category="Users and security",
        title="User accounts and passwords",
        keywords=["user", "account", "password", "administrator"],
        kcm="kcm_users",
    ),
    SettingsEntry(
        id="screenlock",
        category="Users and security",
        title="Screen lock",
        keywords=["lock", "screen saver"],
        kcm="kcm_screenlocker",
    ),
    SettingsEntry(
        id="login",
        category="Users and security",
        title="Login screen (SDDM)",
        keywords=["login", "sddm", "autologin"],
        kcm="kcm_sddm",
    ),
    SettingsEntry(
        id="hostname", category="System", title="Hostname", keywords=["hostname", "computer name"], native="hostname"
    ),
    SettingsEntry(
        id="datetime",
        category="System",
        title="Date, time and time zone",
        keywords=["time", "date", "timezone", "ntp"],
        native="datetime",
    ),
    SettingsEntry(
        id="locale",
        category="System",
        title="Language and region",
        keywords=["locale", "language", "region"],
        kcm="kcm_regionandlang",
    ),
    SettingsEntry(
        id="autostart",
        category="System",
        title="Startup applications",
        keywords=["autostart", "startup"],
        kcm="kcm_autostart",
    ),
    SettingsEntry(
        id="services", category="System", title="Services", keywords=["systemd", "service", "daemon"], native="services"
    ),
    SettingsEntry(
        id="power",
        category="Hardware",
        title="Power management",
        keywords=["power", "battery", "suspend"],
        kcm="kcm_powerdevilprofilesconfig",
    ),
    SettingsEntry(
        id="about",
        category="System",
        title="System information",
        keywords=["about", "version", "hardware"],
        kcm="kcm_about-distro",
    ),
    SettingsEntry(
        id="audio",
        category="Hardware",
        title="Audio",
        keywords=["sound", "audio", "volume", "microphone"],
        kcm="kcm_pulseaudio",
    ),
    SettingsEntry(
        id="keyboard", category="Hardware", title="Keyboard", keywords=["keyboard", "layout"], kcm="kcm_keyboard"
    ),
    SettingsEntry(id="mouse", category="Hardware", title="Mouse", keywords=["mouse", "pointer"], kcm="kcm_mouse"),
    SettingsEntry(id="touchpad", category="Hardware", title="Touchpad", keywords=["touchpad"], kcm="kcm_touchpad"),
    SettingsEntry(id="bluetooth", category="Hardware", title="Bluetooth", keywords=["bluetooth"], kcm="kcm_bluetooth"),
    SettingsEntry(
        id="printers", category="Hardware", title="Printers", keywords=["printer", "print"], kcm="kcm_printer_manager"
    ),
    SettingsEntry(
        id="notifications-kde",
        category="System",
        title="Desktop notifications",
        keywords=["notification"],
        kcm="kcm_notifications",
    ),
]


def open_kcm(kcm: str) -> None:
    if not any(e.kcm == kcm for e in CATALOG):
        raise ValidationError(f"unknown settings module {kcm!r}")
    for launcher in (["kcmshell6", kcm], ["systemsettings", kcm]):
        if runner.which(launcher[0]):
            subprocess.Popen(
                launcher,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return
    raise DependencyMissingError("KDE System Settings is not installed", hint="sudo apt install systemsettings")


class TimeStatus(BaseModel):
    timezone: str | None = None
    ntp_enabled: bool | None = None
    ntp_synchronized: bool | None = None
    local_time: str | None = None


def hostname() -> str:
    result = runner.run(["hostnamectl", "hostname"], timeout=5)
    if result.ok:
        return result.stdout.strip()
    return Path("/etc/hostname").read_text().strip() if Path("/etc/hostname").exists() else "unknown"


def set_hostname(name: str) -> None:
    name = validation.hostname(name)
    if "." in name and len(name.split(".")[0]) > 63:
        raise ValidationError("hostname label too long")
    result = runner.run(["hostnamectl", "set-hostname", name], timeout=120)
    if not result.ok:
        raise NexusError("could not change the hostname", hint=runner.first_line(result.stderr) or "polkit denied?")


def time_status() -> TimeStatus:
    result = runner.run(["timedatectl", "show"], timeout=5)
    if not result.ok:
        return TimeStatus()
    data = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    return TimeStatus(
        timezone=data.get("Timezone"),
        ntp_enabled=data.get("NTP") == "yes",
        ntp_synchronized=data.get("NTPSynchronized") == "yes",
        local_time=data.get("TimeUSec"),
    )


def timezones() -> list[str]:
    result = runner.run(["timedatectl", "list-timezones"], timeout=10)
    return result.stdout.split() if result.ok else []


def set_timezone(tz: str) -> None:
    if tz not in set(timezones()):
        raise ValidationError(f"unknown time zone {tz!r}")
    result = runner.run(["timedatectl", "set-timezone", tz], timeout=120)
    if not result.ok:
        raise NexusError("could not set the time zone", hint=runner.first_line(result.stderr))


def set_ntp(enabled: bool) -> None:
    result = runner.run(["timedatectl", "set-ntp", "true" if enabled else "false"], timeout=120)
    if not result.ok:
        raise NexusError("could not change NTP", hint=runner.first_line(result.stderr))


def locale_status() -> dict[str, str]:
    result = runner.run(["localectl", "status"], timeout=5)
    out = {}
    for line in result.stdout.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            out[key.strip()] = value.strip()
    return out


class UserAccount(BaseModel):
    name: str
    uid: int
    full_name: str
    shell: str
    home: str
    groups: list[str]
    administrator: bool


def users() -> list[UserAccount]:
    """Human accounts (uid 1000-59999). Changes go through kcm_users (AccountsService + polkit)."""
    groups_by_user: dict[str, list[str]] = {}
    for g in grp.getgrall():
        for member in g.gr_mem:
            groups_by_user.setdefault(member, []).append(g.gr_name)
    out = []
    for p in pwd.getpwall():
        if 1000 <= p.pw_uid < 60000:
            groups = sorted(groups_by_user.get(p.pw_name, []))
            out.append(
                UserAccount(
                    name=p.pw_name,
                    uid=p.pw_uid,
                    full_name=p.pw_gecos.split(",")[0],
                    shell=p.pw_shell,
                    home=p.pw_dir,
                    groups=groups,
                    administrator="sudo" in groups or "admin" in groups,
                )
            )
    return out
