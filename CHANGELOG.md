# Changelog

All notable changes to NexusOS are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/) for repository releases (see
`docs/release-process.md` for how this maps to the product version `1.0`).

## [Unreleased] — 0.2.0-dev "Command Center"

### Added
- **Nexus Command Center** (`nexusos-command-center`, `nexus-center`): native Qt 6/QML
  application with 14 lazily loaded modules (Overview, Software Center, System Settings,
  Terminal & SSH, Containers, Nexus Applications, Gateway, Storage, Network, Files, Local AI,
  Notifications, Security, Activity History), Ctrl+K command palette, dark/light design
  system (`Nexus.Design`), `--smoke`, `--screenshots` and `--benchmark` modes.
- **nexus_core** (`python3-nexus-core`): single backend for CLI, Command Center and agent —
  APT/dpkg catalogue, plans, history, repositories, locks; systemd services; settings and KCM
  catalogue; real-time metrics; SSH profiles, OpenSSH config generation, Secret Service
  credentials, askpass, host keys, SFTP; Docker Engine client and Compose; application
  registry and lifecycle; gateway model/render/apply/certificates; storage (lsblk, UDisks2,
  guarded format); NetworkManager with checkpoint rollback; KIO files; Ollama models and
  streaming chat; notifications, activity, search, profiles, security overview; SQLite store.
- **Management agent** (`nexusos-management-agent`): socket-activated privileged helper,
  polkit per operation, allow-listed operations, APT progress with safe cancel, audit log.
- **Gateway** (`nexusos-gateway`): native NGINX integration, declarative routes in
  `/etc/nexusos/gateway`, internal CA / self-signed / Let's Encrypt / import, nginx -t +
  backup + automatic rollback, SSRF and injection protection.
- **Application platform**: registry for Private Cloud (ForgeCloud), NexusOps, Cloud Desktop
  (CloudDesk), Open WebUI and Ansible UI (unavailable), pinned to real upstream commits.
- CLI groups: `packages`, `ssh`, `containers`, `apps`, `gateway`, `storage`, `network`,
  `profiles`, `system services|settings`, `ai pull|rm|ps|chat`.
- Installation profiles (`manifests/profiles.yaml`), Command Center icon, login background.
- Tests: ~250 new unit tests, container integration suite (real APT, real NGINX), headless UI
  smoke test, benchmarks; CI for Command Center/QML, security and integration.

### Changed
- CLI services moved into `nexus_core`; `nexus-cli` depends on `python3-nexus-core`.
- `nexusos-desktop` depends on the Command Center and the management agent.
- Gateway renders IPv6 listeners only when the host has IPv6.

### Known limitations
- Terminals open as Konsole tabs, Files uses Dolphin windows, app UIs open in the browser
  (embedding planned). Plasma-session features (polkit prompts, KDE Wallet, Konsole, KCMs,
  NetworkManager checkpoints, UDisks2 format) are verified only in the VM workflow.
- Discover is not removed yet (Flatpak/firmware not replaced).

## 0.1.0-dev "Foundation"

### Added
- Design tokens (`branding/design-tokens.json`) and original SVG artwork: primary,
  horizontal, monochrome, installer and terminal logos; geometric "N" icon; boot logo;
  default, abstract-technology and Engineering Edition wallpapers.
- `nexusos-branding` package: NexusOS os-release via `dpkg-divert` (Ubuntu original
  preserved and restored on removal), release metadata, default hostname for installers,
  terminal banner, ASCII logo, fastfetch configuration, KDE wallpaper packages, icons.
- `nexusos-theme` package: "Nexus" Plasma 6 global theme, generated Nexus colour scheme,
  Nexus icon theme (inherits Breeze Dark), Konsole profile and palette, top-panel +
  floating-dock layout.
- `nexusos-defaults` package: zsh template, shared aliases, NexusOS zsh prompt.
- `nexusos-desktop` package: Plasma/SDDM metapackage, NexusOS XDG defaults directory,
  SDDM drop-in, Nexus Dev/Infra/AI launchers.
- `nexus-cli` (`nexus`): version, help, system info/health/update/cleanup, dev
  list/create fastapi/create react, cloud status, infra status/containers, ai status/models.
- Package manifests for Ubuntu 26.04 "resolute" (base, desktop, development,
  infrastructure, ai) with archive verification.
- Build tooling: container-based `.deb` builds, branding renderer, checksums,
  read-only ISO inspector, Cubic prototype guide and chroot customisation script.
- Validators and tests for branding, manifests, Debian metadata, CLI and ISO tooling;
  GitHub Actions workflows.

### Known limitations
- No ISO has been built. SDDM and Plymouth themes are placeholders.
- The Plasma layout and XDG defaults have not been verified in a live Plasma session.
