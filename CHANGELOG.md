# Changelog

All notable changes to NexusOS are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/) for repository releases (see
`docs/release-process.md` for how this maps to the product version `1.0`).

## [Unreleased] — 0.2.0-dev "Command Center"

### Added
- **Installer and boot branding**: `calamares-settings-nexusos` (NexusOS Calamares branding and
  slides, erase-disk with optional LUKS2, first account in `sudo`/`adm`, Plasma Wayland/SDDM,
  Ubuntu's signed boot chain, installer and live tooling removed from the installed system,
  "Install NexusOS" in the live session) and `plymouth-theme-nexusos` (two-step splash with the
  NexusOS mark; dialog images and Inter fonts in the initrd for encryption prompts).
- **Test ISO build** (`iso/production/build.sh`): mmdebstrap root filesystem from the base and
  desktop manifests plus the NexusOS packages, casper live session, Calamares, zstd squashfs,
  hybrid BIOS/UEFI ISO with Canonical-signed shim and GRUB, on-disc pool for the installer's EFI
  step, checksums and package manifest. Test images only, not a release.
  `scripts/validation/iso-boot-smoke.sh` boots it in QEMU (BIOS, UEFI Secure Boot, live session):
  all 16 checks pass on the 2026-11-14 test image.
- **Operations dashboard** (Overview): CPU, memory, GPU, storage, vulnerabilities (packages
  with Ubuntu security fixes), updates, network and mount tiles with live sparklines and one
  hardware line each; (i) spec cards with CPU specification and per-core load, memory slots
  and modules (SMBIOS via udev, no root), GPU details (DRM sysfs, lspci, nvidia-smi) and
  every drive with interface link, temperature and mount usage; attention list; 24 h usage
  chart (sysstat, or since start); services, infrastructure, activity, sar 7-day history,
  backup timers and gateway certificates. Polls only while visible.
- **Administrative access through the user's own sudo rights**: `nexus-admin` helper run via
  `sudo` executes the same allow-listed, audited operations; NOPASSWD runs directly,
  password sudo shows a floating password box (retry, cancel, sudo's cache), no sudo is
  denied without a prompt and administrative actions are hidden. Tested with sudo-rs and
  sudo 1.9. Services, hostname, time zone and NTP now run through it too.
- `nexus_core.hardware`, `nexus_core.dashboard`, `nexus_core.privilege`; design components
  `NxIcon`, `NxSparkline`, `NxPasswordPrompt`; `nexus-center --size`.
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

- `scripts/validation/plasma-session-container.sh`: boots systemd in a disposable privileged
  container and verifies the packages in a real Plasma 6.6 Wayland session — agent socket,
  polkit actions and authorization (denied without an agent, granted by a test rule, audited),
  theme/layout/wallpaper as applied by plasmashell, the Command Center on KWin Wayland with
  memory budgets, KCM catalogue vs `kcmshell6`, Konsole tabs and systemd service control.
- System Settings marks KDE modules that are not installed and names the package to install.

### Changed
- The image installs neither Plasma Discover nor Flatpak (Software Center for APT, `fwupd` for
  firmware, Flatpak opt-in); Falkon is the default browser until the Firefox snap is seeded.
- `nexusos-branding` keeps `GRUB_DISTRIBUTOR=Ubuntu` (`/etc/default/grub.d/50-nexusos.cfg`):
  26.04 derives it from os-release, which would move GRUB to `/EFI/nexusos` while the
  Canonical-signed GRUB looks in `/EFI/ubuntu` (Secure Boot).
- `nexus-center` uses Qt's `generic` platform theme by default (−93 MiB RSS under Plasma);
  `NEXUS_CENTER_PLATFORMTHEME=kde` restores native KDE file dialogs.
- `nexusos-desktop` recommends the packages that provide the catalogued KCMs (kscreen,
  powerdevil, bluedevil, print-manager, kinfocenter, kde-config-screenlocker).
- Dock: Dolphin and the Command Center are pinned explicitly (Plasma 6.6 dropped the
  `preferred://filemanager` launcher).
- CLI services moved into `nexus_core`; `nexus-cli` depends on `python3-nexus-core`.
- `nexusos-desktop` depends on the Command Center and the management agent.
- Gateway renders IPv6 listeners only when the host has IPv6.

### Removed
- Unused code: `metrics.gpus`/`top_processes` (replaced by `nexus_core.hardware` and the
  dashboard), `network.proxy_settings`, `paths.config_dir`, `privilege.require_admin`,
  `terminal.save_layout`/`export_note`, `validation.path_within`; first-round Overview mockups.

### Fixed
- Command Center under Plasma: full Qt palette from the design tokens (light or unreadable
  controls), Overview header and cards clipped at the right edge, Nexus Applications detail
  pane squeezed by the header, the `palette` id shadowing the window palette, screenshots
  with a transparent content area, Local AI spin boxes (temperature shown as 7, context 0).
- Service states read `loaded` instead of `active` (systemd prints properties in its own order).
- Disk usage listed bind-mounted files such as `/etc/hosts`; Files listed Home twice.

### Known limitations
- Terminals open as Konsole tabs, Files uses Dolphin windows, app UIs open in the browser
  (embedding planned). Interactive polkit prompts, KDE Wallet, NetworkManager checkpoints and
  UDisks2 formatting still need the VM workflow; the Plasma container verifies polkit
  decisions, Konsole, KCMs, theme and layout without a GPU or an authentication agent.

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
