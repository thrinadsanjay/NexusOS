# NexusOS architecture

NexusOS is an Ubuntu 26.04 derivative: the Ubuntu archive is used unchanged and NexusOS
adds a small set of packages. Everything NexusOS installs can be removed again.

## Four layers

| Layer | Contents | Packages |
|-------|----------|----------|
| 1 Desktop | Plasma 6 (Wayland), branding, theme, defaults, CLI, Command Center | nexusos-desktop, -branding, -theme, -defaults, nexus-cli, nexusos-command-center |
| 2 Command Center | 14 modules over `nexus_core`, privileged agent | nexusos-command-center, python3-nexus-core, nexusos-management-agent |
| 3 Application Platform | optional Compose apps from their own repositories | registry in python3-nexus-core; apps installed on request |
| 4 Runtime | APT/dpkg, systemd, Docker, NGINX, libvirt, NetworkManager, UDisks2, Ollama, Postgres/Redis/Keycloak inside apps | Ubuntu archive (+ Ollama upstream, opt-in) |

## Repository layout

```
branding/ desktop/ configs/          identity, artwork, Plasma theme, defaults (v0.1)
command-center/
  backend/nexus_core/                ONE implementation of every operation (CLI + UI + agent)
    packages.py services.py settings.py metrics.py storage.py network.py files.py
    ssh/ (profiles, config, credentials, askpass, hostkeys, sessions, sftp)
    docker.py compose.py apps/ (registry, lifecycle) gateway/ (model, render, apply, certs, status)
    ollama.py chat.py notifications.py activity.py search.py security.py store.py validation.py redact.py
  privileged-agent/nexus_agent/      socket server, polkit auth, allow-listed ops, audit; systemd + polkit files
  frontend/                          nexus_center (PySide6 shell, TaskRunner, base controller) + qml/ (Main, Nexus.Design)
  modules/<id>/                      module.json + controller.py + Page.qml (14 modules)
  tests/                             backend, agent, gateway, SSH, apps, modules, GUI tests
packages/<pkg>/debian                Debian packaging (9 source packages)
packages/nexus-cli/nexus_cli         CLI presentation layer (Typer/Rich) over nexus_core
applications/                        registry + deployment definitions (no application source)
gateway/                             NGINX include, route schema, example routes
manifests/                           package sets + installation profiles (resolute)
scripts/ tests/ iso/ docs/ .github/
```

## Process and privilege model

```
user session                                                     root (on demand)
┌──────────────────────────┐   JSON lines over /run/nexusos/agent.sock   ┌────────────────────────────┐
│ nexus-center / nexus CLI │ ─────────────────────────────────────────►  │ nexusos-agent (socket unit)│
│  nexus_core (queries,    │   SO_PEERCRED → pkcheck (polkit action)     │  allow-listed ops only     │
│  plans, validation)      │ ◄───────── progress / log / result ──────── │  apt · gateway · SMART · ufw│
└──────────────────────────┘                                             │  audit log, exits when idle │
      │ direct, polkit-protected system services                         └────────────────────────────┘
      ├─ systemctl (systemd1.manage-units) ── hostnamectl/timedatectl ── udisksctl/UDisks2 ── nmcli/NetworkManager
      ├─ Docker Engine API (local socket, user must be authorised for Docker)
      └─ Ollama API (127.0.0.1:11434)
```

* The Command Center and CLI always run as the user. Only operations without an existing
  polkit-protected interface (APT, gateway files + NGINX reload, certificates, SMART,
  firewall) go through the agent.
* The agent accepts a fixed set of operations, each with a Pydantic parameter model
  (`extra="forbid"`) and its own polkit action; it never accepts command lines, shell
  fragments or arbitrary write paths. Unknown/invalid requests are rejected and audited.
* Socket `0660 root:sudo`; polkit decides per request (`auth_admin_keep` for software and
  gateway changes, `auth_admin` for repositories and firewall changes). Without polkit the
  agent denies everything except root.

## Data

| Data | Location | Protection |
|------|----------|------------|
| UI settings, SSH profiles, notifications, activity, chat | `~/.local/share/nexusos/command-center.db` | 0600, row limits |
| Secrets (SSH passwords, passphrases) | Secret Service (KDE Wallet) | never in files/DB/logs/argv |
| Generated SSH config | `$XDG_RUNTIME_DIR/nexusos/ssh_config` | 0600, no secrets |
| Application deployments | `~/.local/share/nexusos/apps/<id>/` | dir 0700, `.env` 0600 |
| Gateway routes / certificates | `/etc/nexusos/gateway/` | written by the agent; keys 0600 |
| Agent audit | `/var/log/nexusos/agent-audit.log` | 0640, rotated (5 × 1 MB) |

## Profiles

`manifests/profiles.yaml`: **Base Desktop** (default), **Development Workstation**,
**Private Cloud Host**, **Infrastructure Operations**, **Local AI**. Applied on request
(`nexus profiles apply <id>`); applications are always installed individually.
