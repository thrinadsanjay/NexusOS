# NexusOS Engineering Edition

**BUILD. AUTOMATE. DEPLOY.**

NexusOS is an Ubuntu-based engineering workstation: KDE Plasma 6 on Wayland plus the
**Nexus Command Center**, a native application that manages software, settings,
terminals and SSH, containers, Nexus applications, the NGINX gateway, storage, network,
files and local AI from one place, with no browser or web stack involved.

> NexusOS is an independent project based on Ubuntu 26.04 LTS. It is **not** an
> official Ubuntu product and is not affiliated with or endorsed by Canonical Ltd.
> Ubuntu is a registered trademark of Canonical Ltd.

| | |
|---|---|
| Version | `0.2.0-dev` (product identity `1.0`) |
| Base | Ubuntu 26.04 LTS "resolute", amd64, Ubuntu kernel |
| Desktop | KDE Plasma 6, Wayland, SDDM |
| Management | Nexus Command Center (Qt 6/QML + Python), `nexus` CLI, polkit-authorized agent |
| Infrastructure | APT/dpkg, systemd, Docker Engine + Compose, native NGINX, KVM/libvirt, NetworkManager, UDisks2 |
| Local AI | Ollama (optional, installed on request) |

## Architecture in one picture

```
Layer 1  NexusOS Desktop     Plasma 6 · branding · defaults · nexus CLI · Command Center (default)
Layer 2  Command Center      14 modules over nexus_core · management agent (socket-activated, polkit)
Layer 3  Application Platform  Private Cloud · NexusOps · Cloud Desktop · Open WebUI · (Ansible UI)  — optional
Layer 4  Runtime             APT/dpkg · systemd · Docker · NGINX · libvirt · NetworkManager · UDisks2 · Ollama
```

A failure in Docker, Ollama or any application never takes the desktop or the Command
Center down: each module degrades to a clear empty/error state.

## Status (0.2.0-dev)

**Implemented** = code + automated tests · **Tested** = also verified end-to-end in a
disposable Ubuntu 26.04 container with the built packages · **Experimental** = needs a
real Plasma session/hardware · **Planned** · **Unsupported**.

| Area | Status |
|------|--------|
| Branding, theme, defaults, os-release (v0.1) | Tested (install/upgrade/remove) |
| Command Center shell, design system (dark + light), 14 lazy modules, Ctrl+K palette | Tested headless on 26.04 (no QML warnings); **Experimental** on Plasma |
| Software Center (APT/dpkg via agent, plans, progress, locks, cancel, repos, history) | **Tested** |
| Administrative access (user's sudo rights via `nexus-admin`, allow-list, audit; socket agent with polkit) | **Tested** (sudo-rs and sudo 1.9; polkit prompts need the VM) |
| Gateway (native NGINX, routes, internal CA, HTTPS, redirect, SSRF guard, rollback) | **Tested** with real NGINX |
| Terminal & SSH (profiles, OpenSSH config, Secret Service credentials, askpass, host keys, SFTP) | Implemented; Konsole/KWallet **Experimental** |
| Containers (Docker Engine API, images, volumes, networks, Compose) | Implemented |
| Nexus applications (registry from real repos, lifecycle, backup, gateway proposal) | Implemented; real deployments **Experimental** |
| Storage (inventory, SMART via agent, mount, guarded format via UDisks2) | Implemented; format **Experimental** (mocked by design) |
| Network (NetworkManager, DNS, routes, diagnostics, checkpoint rollback) | Implemented; rollback **Experimental** |
| Files (KIO, Dolphin, Baloo, Ark) | Implemented, **Experimental** |
| Local AI (Ollama models, streaming native chat) | Implemented; real Ollama **Experimental** |
| Notifications, security overview, activity history | Implemented |
| Embedded terminal / Dolphin / web UIs inside the window | Planned |
| Production ISO | Not built (by design at this stage) |

Measured (dev container, offscreen): Command Center launch **508 ms**, **131.5 MiB** idle,
**0.29 %** idle CPU; **149.9 MiB** after opening every module; pages load in 5–39 ms.
See [docs/performance.md](docs/performance.md).

## Packages

| Package | Purpose |
|---------|---------|
| `nexusos-branding`, `nexusos-theme`, `nexusos-defaults` | identity, artwork, Plasma theme, shell defaults |
| `python3-nexus-core` | shared backend + application registry + manifests + `nexus-askpass` |
| `nexusos-management-agent` | privileged helper (socket, polkit policy, audit) |
| `nexusos-command-center` | `nexus-center` native application |
| `nexus-cli` | `nexus` command |
| `nexusos-gateway` | NGINX integration for the gateway |
| `nexusos-desktop` | metapackage: Plasma + Command Center + agent + defaults |

## Quick start

```bash
git clone https://github.com/thrinadsanjay/NexusOS.git && cd NexusOS
git checkout feature/nexusos-command-center-v0.2

scripts/development/setup.sh && . .venv/bin/activate      # venv with everything editable
scripts/development/validate.sh                           # lint, validators, all tests
scripts/development/test-command-center.sh --benchmark    # Command Center tests + resource report
scripts/development/build-packages.sh                     # .debs built in ubuntu:26.04
scripts/validation/integration-container.sh               # end-to-end tests in a throwaway container
scripts/validation/plasma-session-container.sh            # systemd + polkit + Plasma 6 Wayland session checks
QT_QPA_PLATFORM=offscreen nexus-center --smoke            # or just: nexus-center (with a display)
```

Testing on a real Plasma desktop: [docs/installation.md](docs/installation.md#disposable-test-vm).

## CLI

```text
nexus version | help
nexus system info | health | update | cleanup | services | settings
nexus packages search | show | install | remove | update | list | history | lock | repo
nexus ssh list | profiles | add | remove | connect | trust | config | credentials
nexus containers list | start | stop | restart | rm | logs | inspect | stats | images | pull | volumes | networks | compose
nexus apps list | status | install | uninstall | start | stop | restart | logs | update | backup | restore
nexus gateway status | apply | rollback | routes … | ssl … | nginx …
nexus storage list | usage | health
nexus network status | interfaces | routes | dns | diagnostics | firewall
nexus ai status | models | pull | rm | ps | chat
nexus profiles list | show | apply
nexus dev …  nexus cloud status  nexus infra …
```

## Documentation

[Architecture](docs/architecture.md) · [Command Center](docs/command-center.md) ·
[Package management](docs/package-management.md) · [Terminal & SSH](docs/ssh-workspace.md) ·
[Gateway](docs/gateway.md) · [Application platform](docs/application-platform.md) ·
[Security](docs/security.md) · [Performance](docs/performance.md) ·
[Branding](docs/branding-guide.md) · [Installation & VM testing](docs/installation.md) ·
[Build](docs/build-guide.md) · [Release](docs/release-process.md) ·
[Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md)

## License

NexusOS code, configuration and artwork: GNU GPL v2 or later (see `LICENSE`). Packages
from the Ubuntu archive keep their own licences. Nexus applications are separate projects
with their own licences.
