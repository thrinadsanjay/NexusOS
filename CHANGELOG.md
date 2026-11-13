# Changelog

All notable changes to NexusOS are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/) for repository releases (see
`docs/release-process.md` for how this maps to the product version `1.0`).

## [Unreleased] — 0.1.0-dev "Foundation"

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
