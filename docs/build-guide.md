# Build guide

Everything here runs as an unprivileged user in a disposable environment. No
step writes to physical disks or modifies the host's OS identity.

## 1. Development environment

```bash
git clone https://github.com/thrinadsanjay/NexusOS.git && cd NexusOS
scripts/development/setup-dev-env.sh        # .venv with nexus-cli (editable), ruff, yamllint, pytest
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
scripts/validation/run-all.sh                     # everything available, with a PASS/FAIL/SKIPPED summary
python3 scripts/validation/validate_manifests.py --check-archive   # names vs resolute archive (network)
python3 scripts/validation/validate_branding.py
python3 scripts/validation/validate_debian.py [--debs build/debs]
scripts/development/run-cli-tests.sh
```

## 3. Branding derivatives

```bash
python3 scripts/build/generate_theme_colors.py   # after editing design tokens
scripts/build/render-branding.sh                 # PNG/WebP previews -> build/branding/
```

## 4. Debian packages

Reference build (matches the target release exactly):

```bash
scripts/package/build-in-container.sh            # ubuntu:26.04, unprivileged builder, lintian
scripts/validation/test-packages-container.sh    # install / reinstall / remove / purge test
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

## 5. Prototype ISO

See [`iso/prototype/README.md`](../iso/prototype/README.md) (Cubic, in a VM).
Inspect any image read-only with:

```bash
scripts/build/inspect-iso.sh --sums SHA256SUMS --deep nexusos.iso
```

## 6. Production ISO

Planned; see [`iso/production/README.md`](../iso/production/README.md).
