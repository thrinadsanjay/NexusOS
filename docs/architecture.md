# NexusOS architecture

NexusOS is a *derivative* of Ubuntu 26.04 LTS: it consumes the Ubuntu archive
unchanged and layers a small set of NexusOS packages on top. Anything NexusOS
ships can be removed, returning the system to stock Ubuntu/Kubuntu behaviour.

```
┌────────────────────────────────────────────────────────────────────────┐
│ User layer        ~/.config (always wins)                              │
├────────────────────────────────────────────────────────────────────────┤
│ NexusOS layer     nexusos-desktop   metapackage + session defaults     │
│                   nexusos-theme     Nexus LnF, colours, icons, Konsole │
│                   nexusos-branding  identity, artwork, banner          │
│                   nexusos-defaults  shell defaults                     │
│                   nexus-cli         `nexus` toolkit                    │
├────────────────────────────────────────────────────────────────────────┤
│ Ubuntu layer      resolute main/universe: kernel, systemd, APT,        │
│                   Plasma 6, SDDM, KVM/libvirt, docker.io, Python 3.14  │
└────────────────────────────────────────────────────────────────────────┘
```

## Package graph

```
nexusos-desktop ──► nexusos-theme ──► nexusos-branding
      │                  └─► plasma-workspace, breeze-icon-theme
      ├──► nexusos-defaults
      ├──► nexus-cli ──► python3-{typer,rich,pydantic,httpx}
      └──► kde-plasma-desktop, plasma-session-wayland, sddm, konsole, dolphin, kate, plasma-systemmonitor
```

All NexusOS packages are `Architecture: all`, built with debhelper 13 and
`Rules-Requires-Root: no`. Package versions move in lockstep (`0.1.0~dev1`).

## Identity (nexusos-branding)

* `/usr/lib/os-release` is **diverted** with `dpkg-divert --rename` to
  `/usr/lib/os-release.ubuntu`; NexusOS installs its own file there. Ubuntu's
  `/etc/os-release` symlink follows automatically. On removal the diversion is
  undone and Ubuntu's file is restored (tested in CI).
* `ID=nexusos`, `ID_LIKE=ubuntu`; `VERSION_CODENAME` and `UBUNTU_CODENAME` stay
  `resolute` so third-party APT repositories and installers keyed on the Ubuntu
  codename keep working.
* `/etc/lsb-release`, kernel identity (`uname`), APT sources and the hostname are
  **not** modified. `DEFAULT_HOSTNAME=nexusos` is only a fallback for systemd and
  the installer.

## Desktop configuration

KDE reads configuration from `$XDG_CONFIG_HOME` (`~/.config`) and then each
directory in `$XDG_CONFIG_DIRS`. NexusOS installs its defaults in
`/usr/share/nexusos/xdg` and prepends that directory through a Plasma env script
(`/etc/xdg/plasma-workspace/env/nexusos-xdg.sh`). This avoids file conflicts
with other packages that ship `/etc/xdg/*`, keeps user settings authoritative,
and disappears cleanly when `nexusos-desktop` is removed.

The global theme `org.nexusos.nexus.desktop` composes upstream components:
Breeze application style, window decoration and Plasma style (which follow the
colour scheme), the Nexus colour scheme, the Nexus icon theme (inherits
`breeze-dark`) and the NexusOS wallpaper. Its layout script creates a top
system panel and a floating bottom dock using only stock Plasma widgets.

## nexus-cli

```
nexus_cli/
├── main.py            Typer root app, global options, version/help
├── commands/          one Typer sub-app per group (system, dev, cloud, infra, ai) — rendering only
├── services/          data collection, no printing (system, health, packages, cleanup,
│                      docker, ollama, tools, scaffold, release)
├── core/              logging, safe subprocess runner, output/confirm, error types, decorators
├── models.py          Pydantic models (shared by tables and --json)
└── templates/         project templates (FastAPI)
```

Design rules: services return models; commands render tables or JSON; external
programs run as argv lists with timeouts and a scrubbed environment; Docker and
Ollama are queried through their local HTTP APIs with HTTPX; exit codes are
stable (0 ok, 1 failure, 2 invalid input, 3 missing dependency, 4 cancelled).

## Image build

* **Prototype**: Kubuntu 26.04 ISO remastered with Cubic + `iso/prototype/customize-chroot.sh`.
* **Production (planned)**: mmdebstrap rootfs from manifests + local APT repo of
  NexusOS packages → squashfs → signed shim/GRUB → xorriso hybrid ISO, built in a
  container, smoke-tested in QEMU/OVMF. See `iso/production/README.md`.

## Optional components

AI (Ollama, Open WebUI), Kubernetes tooling, Terraform/OpenTofu and VS Code are
*external*: documented post-install steps, never part of the ISO and never
downloaded during the build.
