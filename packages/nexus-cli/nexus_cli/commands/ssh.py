"""``nexus ssh`` -- SSH profiles and sessions (OpenSSH). Never prints secrets."""

from __future__ import annotations

import getpass

import typer
from nexus_core import activity
from nexus_core.errors import AbortedError
from nexus_core.ssh import config, hostkeys, profiles, sessions
from nexus_core.ssh.credentials import CredentialManager

from nexus_cli.core.decorators import handle_errors
from nexus_cli.core.output import confirm, console, print_json, table

app = typer.Typer(help="SSH connection profiles, credentials and sessions.", no_args_is_help=True)
cred_app = typer.Typer(help="Credentials in the Secret Service (KDE Wallet).", no_args_is_help=True)
app.add_typer(cred_app, name="credentials")


def _rows(items: list[profiles.SSHProfile]) -> list[list]:
    return [
        [p.name, f"{p.user}@{p.host}:{p.port}", p.auth, p.group, "★" if p.favorite else "", ", ".join(p.tags)]
        for p in items
    ]


@app.command("list")
@handle_errors
def list_cmd(
    query: str = typer.Argument("", help="Filter by name, host, group or tag."),
    group: str | None = typer.Option(None),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """List SSH profiles."""
    items = profiles.list_profiles(query, group)
    if json_output:
        print_json(items)
        return
    table("SSH profiles", ["Name", "Target", "Auth", "Group", "Fav", "Tags"], _rows(items))


@app.command("profiles")
@handle_errors
def profiles_cmd(json_output: bool = typer.Option(False, "--json")) -> None:
    """Profiles grouped, plus recent connections."""
    list_cmd("", None, json_output)
    if not json_output:
        table("Recent", ["Name", "Target", "Auth", "Group", "Fav", "Tags"], _rows(profiles.recent()))


@app.command("add")
@handle_errors
def add(
    name: str,
    target: str = typer.Argument(..., help="user@host[:port]"),
    auth: str = typer.Option("agent", help="agent | key | password"),
    key: str | None = typer.Option(None),
    credential: str | None = typer.Option(None, help="credential reference (wallet)"),
    jump: str | None = typer.Option(None, help="jump host profile name"),
    group: str = "Custom",
    tag: list[str] = typer.Option([], "--tag"),
    favorite: bool = False,
    forward: list[str] = typer.Option([], "--forward", help="L:bind:port:host:port | R:... | D:bind:port"),
    agent_forwarding: bool = typer.Option(False, help="Forward your SSH agent (asks for consent)"),
) -> None:
    """Create an SSH profile."""
    import time

    user, _, hostport = target.partition("@")
    host, _, port = hostport.partition(":")
    fwds = []
    for spec in forward:
        parts = spec.split(":")
        if parts[0] == "D":
            fwds.append(profiles.Forward(kind="dynamic", bind_address=parts[1], listen_port=int(parts[2])))
        else:
            fwds.append(
                profiles.Forward(
                    kind="local" if parts[0] == "L" else "remote",
                    bind_address=parts[1],
                    listen_port=int(parts[2]),
                    dest_host=parts[3],
                    dest_port=int(parts[4]),
                )
            )
    consent = None
    if agent_forwarding:
        if not confirm("Agent forwarding lets root on the remote host use your keys while connected. Allow?"):
            raise AbortedError("cancelled")
        consent = time.time()
    jump_id = profiles.get(jump).id if jump else None
    p = profiles.save(
        profiles.SSHProfile(
            name=name,
            host=host,
            port=int(port or 22),
            user=user,
            auth=auth,
            key_path=key,
            credential_ref=credential,
            jump_profile_id=jump_id,
            group=group,
            tags=tag,
            favorite=favorite,
            forwards=fwds,
            agent_forwarding=agent_forwarding,
            agent_forwarding_consent=consent,
        )
    )
    activity.record("ssh.profile.add", p.name, "ok")
    console.print(f"[ok]saved {p.name}[/ok] ({p.id})")


@app.command("remove")
@handle_errors
def remove(name: str) -> None:
    """Delete an SSH profile (credentials stay in the wallet)."""
    if not confirm(f"Delete SSH profile {name}?"):
        raise AbortedError("cancelled")
    profiles.delete(profiles.get(name).id)
    activity.record("ssh.profile.remove", name, "ok")


@app.command("connect")
@handle_errors
def connect(
    name: str, here: bool = typer.Option(False, "--here", help="Run ssh in this terminal instead of a Konsole tab.")
) -> None:
    """Open an SSH session (Konsole tab, or this terminal with --here)."""
    profile = profiles.get(name)
    if here:
        import os

        argv = sessions.ssh_command(profile)
        profiles.record_event(profile.id, "connect")
        os.execvp(argv[0], argv)  # noqa: S606 - argv built from validated profile
    sessions.connect(profile.id)
    console.print(f"[ok]opened {profile.name} in Konsole[/ok]")


@app.command("trust")
@handle_errors
def trust(name: str) -> None:
    """Fetch and show a host's key fingerprints, then trust them after you confirm."""
    p = profiles.get(name)
    keys = hostkeys.scan(p.host, p.port)
    table(
        f"Host keys of {p.host}:{p.port}", ["Type", "SHA256 fingerprint"], [[k.key_type, k.fingerprint] for k in keys]
    )
    if hostkeys.is_known(p.host, p.port):
        console.print("[ok]already trusted[/ok]")
        return
    if confirm("Do these fingerprints match the ones from the server administrator?"):
        hostkeys.trust(keys)
        console.print("[ok]trusted[/ok]")


@app.command("config")
@handle_errors
def show_config() -> None:
    """Print the generated OpenSSH config (no secrets)."""
    console.print(config.render(profiles.list_profiles()), markup=False, highlight=False)


@cred_app.command("list")
@handle_errors
def cred_list() -> None:
    """List saved credentials (metadata only; secrets are never printed)."""
    items = CredentialManager().list()
    table(
        "Credentials",
        ["Reference", "Type", "Username", "Rotation due"],
        [[c.ref, c.kind, c.username, "yes" if c.rotation_due else ""] for c in items],
    )


@cred_app.command("set")
@handle_errors
def cred_set(
    ref: str,
    kind: str = typer.Option("ssh-password", help="ssh-password | ssh-key-passphrase | generic"),
    username: str = "",
    rotate_days: int | None = None,
) -> None:
    """Save or update a credential (prompted without echo, stored in the wallet)."""
    secret = getpass.getpass("Secret: ")
    CredentialManager().save(ref, kind, secret, username, rotate_days)  # type: ignore[arg-type]
    console.print(f"[ok]saved {ref} to the Secret Service[/ok]")


@cred_app.command("delete")
@handle_errors
def cred_delete(ref: str) -> None:
    """Delete a credential from the wallet."""
    if confirm(f"Delete credential {ref}?"):
        CredentialManager().delete(ref)
