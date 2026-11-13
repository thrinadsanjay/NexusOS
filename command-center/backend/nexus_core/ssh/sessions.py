"""Open SSH sessions in Konsole tabs using OpenSSH (no custom SSH implementation)."""

from __future__ import annotations

from nexus_core import terminal, validation
from nexus_core.errors import NexusError
from nexus_core.ssh import config, hostkeys, profiles
from nexus_core.store import Store

ASKPASS = "/usr/lib/nexusos/nexus-askpass"


def ssh_command(profile: profiles.SSHProfile, store: Store | None = None) -> list[str]:
    """argv for an interactive session. Secrets are never on the command line."""
    cfg = config.write(profiles.list_profiles(store=store))
    argv = ["ssh", "-F", str(cfg), profile.alias]
    if profile.auth == "password":
        # env(1) is used because Konsole may run the tab in an already-running process.
        argv = [
            "env",
            f"SSH_ASKPASS={ASKPASS}",
            "SSH_ASKPASS_REQUIRE=force",
            f"NEXUS_CREDENTIAL_REF={profile.credential_ref}",
            "DISPLAY=:0",
            *argv,
        ]
    return argv


def connect(profile_id: str, *, store: Store | None = None, require_known_host: bool = True) -> int:
    profile = profiles.get(profile_id, store)
    if require_known_host and profile.auth == "password" and not hostkeys.is_known(profile.host, profile.port):
        raise NexusError(
            f"the host key of {profile.host} is not trusted yet",
            hint="verify and trust the host key first (Command Center: Verify host, CLI: `nexus ssh trust`)",
        )
    tab = terminal.TerminalTab(
        title=validation.display_name(profile.name),
        command=ssh_command(profile, store),
        konsole_profile=profile.konsole_profile,
    )
    pid = terminal.launch(terminal.konsole_argv(tab))
    profiles.record_event(profile.id, "connect", store)
    return pid
