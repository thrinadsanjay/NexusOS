# Security

## Principles

1. **Least privilege** — the Command Center and CLI run as the user; a small agent does
   the few things that need root, one allow-listed operation at a time.
2. **Explicit authorization** — polkit per operation; destructive actions need confirmation
   (and for disks a typed device token).
3. **Local by default** — application ports bind to 127.0.0.1; gateway routes default to
   LAN-only; the Docker daemon is never exposed.
4. **No secrets at rest outside the Secret Service** — no plaintext passwords anywhere.
5. **Reversible and audited** — backups before gateway changes, automatic rollback, audit log.
6. **Upstream first** — security updates come from Ubuntu unchanged.

## Privileged agent

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
* The audit log is local and not tamper-proof (forward it with journald/rsyslog if needed).
* Third-party application images (GHCR/Docker Hub) are referenced by tag; NexusOps uses
  `latest` upstream (pinnable via configuration).
* `qmllint` style warnings remain; they are not security issues.

## Reporting a vulnerability

Use GitHub Security Advisories on this repository ("Report a vulnerability").
