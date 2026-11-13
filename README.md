# NexusOS Engineering Edition

**BUILD. AUTOMATE. DEPLOY.**

NexusOS is an Ubuntu-based Linux distribution for engineers: a KDE Plasma 6
Wayland workstation with first-class tooling for development, virtualisation,
containers and local AI.

> NexusOS is an independent project based on Ubuntu 26.04 LTS. It is **not** an
> official Ubuntu product and is not affiliated with or endorsed by Canonical Ltd.
> Ubuntu is a registered trademark of Canonical Ltd.

| | |
|---|---|
| Version | `0.1.0-dev` (foundation; product identity `1.0`) |
| Base | Ubuntu 26.04 LTS "resolute", amd64 |
| Desktop | KDE Plasma 6, Wayland by default, SDDM |
| Packaging | APT / `.deb` |
| Shells | Bash and Zsh, Konsole |
| Virtualisation / containers | KVM, QEMU, libvirt; Docker Engine (`docker.io`) |
| Local AI | Ollama CPU inference (optional, post-install) |

## Development status

This branch is the **foundation**. It contains working components that can be
reviewed and tested today, and documents what is still to be done. **No ISO has
been built yet.** The next milestone is a review of the branding, theme and CLI.

| Component | Status |
|-----------|--------|
| Brand system (tokens, logos, icon, wallpapers) | ✅ SVG masters, validated; rasters rendered at build time |
| `nexusos-branding` (os-release, banner, fastfetch, wallpapers) | ✅ builds on 26.04, install/upgrade/remove tested in a container |
| `nexusos-theme` (Nexus global theme, colours, icons, Konsole) | 🟡 builds, lintian clean, deps resolve; **not yet tested in a live Plasma session** |
| `nexusos-desktop` (metapackage, KDE/SDDM defaults, launchers) | 🟡 builds, deps resolve; session behaviour needs VM testing |
| `nexusos-defaults` (zsh template, aliases, prompt) | ✅ builds and installs |
| `nexus-cli` (`nexus` command) | ✅ all commands implemented, 70+ unit tests, runs on 26.04's Python 3.14 |
| Package manifests | ✅ 141 packages verified against the resolute archive |
| SDDM / Plymouth themes | ⏳ placeholders with implementation notes |
| Prototype ISO (Cubic) | 📄 documented and scripted, not yet produced |
| Production ISO pipeline | 📄 design only |

## Repository layout

```
branding/      design tokens + SVG masters (logos, icon, wallpapers, boot logo)
desktop/       KDE global theme, colour scheme, icon theme, panel layout, wallpaper metadata
configs/       os-release, shell (banner, zsh), KDE defaults, SDDM, Plymouth
packages/      Debian source packages (nexusos-branding, -theme, -defaults, -desktop, nexus-cli)
manifests/     base / desktop / development / infrastructure / ai package sets (resolute)
scripts/       build/, package/, validation/, development/ tooling
iso/           prototype (Cubic) guide + chroot script; production pipeline design
tests/         branding, cli, manifests, packages, iso
docs/          architecture, branding guide, build, installation, release, security
```

## Quick start

Prerequisites: Ubuntu 24.04+ (or any Linux with Python ≥ 3.11). Packaging needs
`dpkg-dev debhelper dh-python pybuild-plugin-pyproject librsvg2-bin optipng`;
the reference build uses Docker with `ubuntu:26.04`.

```bash
git clone https://github.com/thrinadsanjay/NexusOS.git && cd NexusOS
git checkout feature/nexusos-foundation-v0.1

scripts/development/setup-dev-env.sh && . .venv/bin/activate
nexus version
nexus system health

scripts/validation/run-all.sh                    # lint, validators, tests
scripts/package/build-in-container.sh            # build all .debs on Ubuntu 26.04
scripts/validation/test-packages-container.sh    # install/upgrade/remove test in a container
scripts/build/render-branding.sh                 # PNG/WebP previews in build/branding
```

## The `nexus` CLI

```text
nexus version | help [GROUP]
nexus system info | health | update | cleanup
nexus dev list | create fastapi NAME | create react NAME
nexus cloud status
nexus infra status | containers
nexus ai status | models
```

Read-only by default; `update` and `cleanup --apply` show the exact `sudo`
command and ask before running it. See [`packages/nexus-cli/README.md`](packages/nexus-cli/README.md).

## Documentation

* [Architecture](docs/architecture.md)
* [Branding guide](docs/branding-guide.md)
* [Build guide](docs/build-guide.md)
* [Installation and safe testing](docs/installation.md)
* [Release process](docs/release-process.md)
* [Security](docs/security.md)
* [Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md)

## License

NexusOS code, configuration and artwork: GNU GPL v2 or later (see `LICENSE`).
Packages from the Ubuntu archive keep their own licences. NexusOS names and
logos identify this project; see the [branding guide](docs/branding-guide.md#trademark-use).
