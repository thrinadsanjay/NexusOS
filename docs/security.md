# Security

## Principles

1. **Least privilege** — the Command Center and CLI run as the logged-in user; a small
   helper does the few things that need root, one allow-listed operation at a time.
2. **The user's own rights** — administrative tasks use the signed-in user's `sudo` rights
   (see *Administrative access*); users see only what they can access; destructive actions
   need confirmation (and for disks a typed device token).
3. **Local by default** — application ports bind to 127.0.0.1; gateway routes default to
   LAN-only; the Docker daemon is never exposed.
4. **No secrets at rest outside the Secret Service** — no plaintext passwords anywhere.
5. **Reversible and audited** — backups before gateway changes, automatic rollback, audit log.
6. **Upstream first** — security updates come from Ubuntu unchanged.

## Administrative access (sudo)

Everything in the Command Center and the CLI runs as the logged-in user. Administrative tasks
(packages, repositories, services, hostname/time, gateway, certificates, SMART, firewall) run
`sudo /usr/lib/nexusos/nexus-admin run` with that user's own sudo rights:

| The user's sudo rights | What happens |
|------------------------|--------------|
| `NOPASSWD` rule (or credentials sudo has cached) | The task runs immediately |
| sudo with password (member of `sudo`/`admin`/`wheel`) | A floating password box asks for the user's password; it is written to `sudo -S` once and never stored, logged or kept in the UI. Wrong password → retry (3 attempts); Cancel → task cancelled. sudo's own credential cache then applies to the next tasks of the session |
| No sudo | "Access denied" — no password prompt; administrative actions are hidden or disabled in the UI and the sidebar shows *Standard user* |

* **sudo decides.** NexusOS never parses `/etc/sudoers`; it starts `sudo` and reads the outcome
  (works with sudo-rs, the 26.04 default, and sudo 1.9 — both are tested). sudo logs every run.
* **Classification does not call sudo** (that would log a failed attempt at every start):
  group membership marks an administrator; whether a password is needed is learned at the
  first task. A non-member with a NOPASSWD rule is recognised (`sudo -n` succeeds); a
  non-member with a password rule is treated as a standard user.
* **The helper is narrow.** `nexus-admin` speaks the agent protocol over stdio and executes
  only the operations in `nexus_agent.ops.REGISTRY`, with the same Pydantic validation, unit
  allow-list and audit log (`"via": "sudo"`, `SUDO_UID` as the caller). It never runs a
  command line, shell fragment or arbitrary path. Its Python runs with `-I` (no environment
  or user site). sudo resets the environment.
* **Background reads never prompt.** Reads the user did not ask for (firewall status on page
  load) return "locked" and offer an explicit *Unlock* instead of a password box.
* **Visibility follows access.** Docker without socket access, libvirt without the group,
  system logs without `adm`/`systemd-journal` are shown as "no access", never guessed.
* The socket-activated agent with polkit remains available (`NEXUSOS_ADMIN_TRANSPORT=agent`).

## Privileged agent (socket transport)

| Control | Implementation |
|---------|----------------|
| Activation | systemd socket `/run/nexusos/agent.sock`, `0660 root:sudo`; service exits after 120 s idle |
| Caller identity | `SO_PEERCRED` (pid, uid) + process start time passed to polkit (race-free subject) |
| Authorization | `pkcheck --action-id org.nexusos.agent.* --allow-user-interaction`; root callers allowed; **no polkit → deny** (tested) |
| Operations | fixed registry (`apt.*`, `apt.repo.*`, `gateway.*`, `storage.smart`, `firewall.*`, `agent.ping`) |
| Input | Pydantic models with `extra="forbid"`; package names, hostnames, ports, paths validated; request size ≤ 256 KiB |
| APT | names after `--`; re-simulation must match the confirmed plan; dpkg lock check; `--force-confold`; output redacted |
| Gateway | SSRF guard, injection-proof rendering, `nginx -t` before reload, backup + rollback |
| Certificates | private keys 0600; CA key 0700 dir; imports must be readable by the caller |
| Audit | every request (allowed, denied, invalid, failed) written *before* replying; params redacted |
| Hardening | `ProtectHome=read-only`, `PrivateTmp`, `ProtectKernel*`, `MemoryHigh=512M`, `TasksMax=256` |

## Secrets

* SSH passwords and key passphrases: Secret Service only (KDE Wallet). Saving fails when no
  Secret Service is available (no fallback). A test checks the secret never reaches SQLite.
* `nexus-askpass` answers only password/passphrase prompts; host-key questions are refused;
  password profiles force `StrictHostKeyChecking yes`.
* Child processes get a scrubbed environment. Diagnostics, container inspection
  (`Env` values), logs and activity entries pass through `nexus_core.redact`.
* Application secrets are generated per install into `.env` files with mode 0600 and kept
  stable across updates; backups are written with mode 0600.
* `scripts/validation/check_secrets.py` scans the repository in CI.

## Docker

Docker administration is root-equivalent. NexusOS talks only to the local socket, never
enables TCP, shows this warning in the Containers page, does not add users to the `docker`
group, and **never mounts the Docker socket into application containers** (the NexusOps
upstream mount is removed by the NexusOS override; validated by `validate_apps.py`).

## Network exposure

| Service | Default |
|---------|---------|
| Nexus applications | `127.0.0.1:<port>` only; LAN access through the gateway after approval |
| Gateway routes | `access: lan` (RFC 1918/ULA/loopback allow-list) unless set to `public` with a warning |
| Ollama | 127.0.0.1:11434 (credentials in `OLLAMA_HOST` are rejected) |
| Agent | Unix socket only |
| Firewall | ufw status via the agent; changes need `auth_admin` |

## Storage and network safety

* Formatting goes through UDisks2 (`Block.Format`, polkit), never `mkfs` from NexusOS code.
  Refused for disks holding `/`, `/boot`, `/home`, `/var`…, for mounted filesystems and swap;
  the device is re-validated before execution and the user must type its serial (or path).
  Tests never touch real devices.
* Network changes that can disconnect the machine use NetworkManager checkpoints with
  automatic rollback after 60 s unless confirmed.

## Known limitations

* polkit prompts, KDE Wallet as Secret Service and the agent under real systemd are verified
  in containers only partially (fail-closed path); interactive authorization needs the VM.
* Members of the `sudo` group can reach the agent socket; polkit is the actual gate.
* With sudo the password crosses the Command Center process (a Python string, which cannot
  be wiped from memory); it is never written anywhere. Formatting (UDisks2) and network
  changes (NetworkManager) still authorize through polkit, not sudo.
* The audit log is local and not tamper-proof (forward it with journald/rsyslog if needed).
* Third-party application images (GHCR/Docker Hub) are referenced by tag; NexusOps uses
  `latest` upstream (pinnable via configuration).
* `qmllint` style warnings remain; they are not security issues.

## Reporting a vulnerability

Use GitHub Security Advisories on this repository ("Report a vulnerability").
