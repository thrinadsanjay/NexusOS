# Prototype ISO with Cubic

Status: **documented, not yet produced.** No NexusOS ISO has been built from
this repository so far. Follow this guide only on a disposable machine or VM.

The prototype remasters the official **Kubuntu 26.04 LTS** desktop ISO with
[Cubic](https://github.com/PJ-Singh-001/Cubic) (Custom Ubuntu ISO Creator).
Kubuntu already provides Plasma 6, SDDM and the Calamares installer
(`calamares-settings-kubuntu`), so the prototype only adds NexusOS packages.

> Cubic is not in the Ubuntu archive; it is distributed through its own PPA.
> Run it in a VM or on a build machine you can reinstall. Cubic works on copies
> of the ISO in a project directory and does **not** write to disks, but the
> machine running it needs root for the chroot.

## 1. Prepare

```bash
# In a disposable Ubuntu 26.04 VM (≥ 4 CPUs, 8 GB RAM, 60 GB disk)
git clone https://github.com/thrinadsanjay/NexusOS.git && cd NexusOS
git checkout feature/nexusos-foundation-v0.1
scripts/package/build-in-container.sh          # or scripts/package/build-deb.sh
scripts/build/checksums.sh generate build/debs

mkdir -p ~/nexusos-cubic/payload/debs
cp build/debs/*.deb ~/nexusos-cubic/payload/debs/
cp -r manifests iso/prototype/customize-chroot.sh ~/nexusos-cubic/payload/
```

Download `kubuntu-26.04-desktop-amd64.iso` and its `SHA256SUMS` from
`https://cdimage.ubuntu.com/kubuntu/releases/26.04/release/`, then verify:
`sha256sum --check --ignore-missing SHA256SUMS`.

## 2. Cubic project settings

| Field | Value |
|-------|-------|
| Project directory | `~/nexusos-cubic/project` |
| Original ISO | `kubuntu-26.04-desktop-amd64.iso` |
| Custom ISO name | `nexusos-1.0-dev-engineering-amd64.iso` |
| Volume ID | `NexusOS 1.0 Engineering` |
| Release | `1.0 dev` |
| Release URL | `https://github.com/thrinadsanjay/NexusOS` |
| Disk name | `NexusOS 1.0 "Engineering Edition" - Development amd64` |

## 3. Customise in the Cubic chroot terminal

Use Cubic's **Copy** button to copy `~/nexusos-cubic/payload` into the chroot
as `/root/nexusos`, then run:

```bash
bash /root/nexusos/customize-chroot.sh /root/nexusos            # Engineering Edition
bash /root/nexusos/customize-chroot.sh /root/nexusos --minimal  # base + desktop only
```

The script refuses to run outside a chroot (`ischroot`). It installs the
manifest packages and NexusOS `.deb`s, seeds `/etc/skel/.zshrc`, and never
installs Ollama, Open WebUI or AI models.

Then exit the chroot terminal and continue in Cubic:

* **Packages page** — leave the defaults; do not remove `casper`, `calamares*`
  or `kubuntu-settings-desktop` (the live session and installer depend on them).
* **Kernel page** — keep the default `linux-generic` kernel.
* **Compression** — `zstd` (fast to build, good size) or `xz` (smaller ISO).

## 4. Test the ISO (VM only)

```bash
scripts/build/inspect-iso.sh --deep ~/nexusos-cubic/project/nexusos-1.0-dev-engineering-amd64.iso
qemu-img create -f qcow2 /tmp/nexusos-test.qcow2 40G
qemu-system-x86_64 -enable-kvm -m 6144 -smp 4 -machine q35 \
  -bios /usr/share/ovmf/OVMF.fd \
  -cdrom ~/nexusos-cubic/project/nexusos-1.0-dev-engineering-amd64.iso \
  -drive file=/tmp/nexusos-test.qcow2,if=virtio
```

Use the checklist in [`docs/installation.md`](../../docs/installation.md#vm-test-checklist).
Never write the image to a physical disk while it is in development.

## Known prototype limitations

* Calamares still shows Kubuntu branding (a NexusOS Calamares branding module is planned;
  `branding/logo/nexusos-installer-logo.svg` is ready for it).
* Plymouth and SDDM use the Breeze placeholders (`configs/plymouth/`, `configs/sddm/`).
* The live session user is created by casper with Kubuntu defaults.
