# Build guide

Everything here runs as an unprivileged user in a disposable environment. No
step writes to physical disks or modifies the host's OS identity.

## 1. Development environment

```bash
git clone https://github.com/thrinadsanjay/NexusOS.git && cd NexusOS
scripts/development/setup.sh                # .venv: nexus-core, agent, Command Center (PySide6), CLI, ruff, pytest
. .venv/bin/activate
```

Optional system tools (the setup script lists which are missing; install them yourself):

```bash
sudo apt install dpkg-dev debhelper dh-python pybuild-plugin-pyproject python3-all \
    lintian librsvg2-bin optipng webp fonts-inter fonts-jetbrains-mono \
    shellcheck xorriso squashfs-tools desktop-file-utils docker.io
```

## 2. Validate

```bash
scripts/development/validate.sh [--archive]       # everything available, PASS/FAIL/SKIPPED summary
scripts/development/test-command-center.sh [--benchmark]
scripts/development/test-cli.sh
python3 scripts/validation/validate_manifests.py --check-archive   # names vs resolute archive (network)
python3 scripts/validation/validate_branding.py
python3 scripts/validation/validate_debian.py [--debs build/debs]
```

## 3. Branding derivatives

```bash
python3 scripts/build/generate_theme_colors.py   # after editing design tokens
scripts/build/render-branding.sh                 # PNG/WebP previews -> build/branding/
```

## 4. Debian packages

Reference build (matches the target release exactly):

```bash
scripts/development/build-packages.sh            # ubuntu:26.04 build of all 9 packages, lintian, checksums
scripts/validation/test-packages-container.sh    # branding install / reinstall / remove / purge test
scripts/validation/integration-container.sh      # agent + real APT, real NGINX gateway, CLI, Command Center
scripts/validation/plasma-session-container.sh   # systemd + polkit + Plasma 6 Wayland session (privileged container)
python3 scripts/validation/validate_debian.py --debs build/debs
scripts/build/checksums.sh generate build/debs
```

Host build (Ubuntu 24.04+ with the tools above):

```bash
scripts/package/build-deb.sh                     # all packages
scripts/package/build-deb.sh nexusos-theme       # one package
```

`build-deb.sh` copies `packages/<name>/` plus the files listed in its
`assets.txt` into `build/pkgsrc/<name>/` and runs `dpkg-buildpackage -b -us -uc`
there, so the Git tree is never used as a build directory. Rasters (wallpapers,
icons, theme previews) are rendered from SVG by each package's `debian/rules`.

> Host builds of `nexus-cli` need a standard `/usr/bin/python3` symlink;
> dh-python refuses non-default interpreters. Use the container build otherwise.

Source packages (9): nexusos-branding, nexusos-theme, nexusos-defaults, nexus-core
(binary `python3-nexus-core`), nexusos-management-agent, nexusos-command-center,
nexus-cli, nexusos-gateway, nexusos-desktop. Python projects are built with dh-python /
pybuild-plugin-pyproject; QML, modules, the application registry and manifests are
installed as data under `/usr/share`.

## 5. Command Center benchmarks

```bash
scripts/benchmarks/command-center.sh --runs 3 --idle 20      # writes build/benchmarks/*.json
```

## 6. Prototype ISO

See [`iso/prototype/README.md`](../iso/prototype/README.md) (Cubic, in a VM).
Inspect any image read-only with:

```bash
scripts/build/inspect-iso.sh --sums SHA256SUMS --deep nexusos.iso
```

## 7. Production ISO

Planned; see [`iso/production/README.md`](../iso/production/README.md).
