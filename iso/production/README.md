# NexusOS ISO build

Status: **test images only — no production ISO has been built.** `build.sh` produces a bootable live/installer ISO for VM
testing. It is not a release: there is no signed NexusOS archive yet, the on-disc package
pool is unsigned, and the image has not been boot- and install-tested on hardware.

## Build a test image

```bash
scripts/package/build-in-container.sh          # build/debs: the 11 NexusOS packages
iso/production/build.sh                        # build/iso: nexusos-1.0-dev-<date>-amd64.iso (+ .sha256, .manifest)
```

Needs Docker with `--privileged` (the build chroots into the new root filesystem and mounts
`/proc`, `/sys`, `/dev` inside the container), about 30 GB of free disk and access to the
Ubuntu archive (about 2.6 GB of packages; set `NEXUSOS_ARCHIVE=http://<cc>.archive.ubuntu.com/ubuntu`
for a nearby mirror). Downloaded packages are kept in `build/apt-cache/` and reused by the next
build, so a rerun after a failure fetches only what is missing (delete the directory to start
clean). The build checks for about 30 GB of free space first. Nothing on the host is modified: no host disk, loop device or bootloader is
touched. Takes 20–40 minutes depending on bandwidth and CPU.

## What is in the image

| Part | Source |
|------|--------|
| Root filesystem | `mmdebstrap` (Ubuntu 26.04 "resolute", main/restricted/universe/multiverse, with recommends) from `manifests/base.yaml` + `manifests/desktop.yaml`; NexusOS packages from a local repository built from `build/debs` |
| Excluded | Plasma Discover, Flatpak, snapd, Kubuntu/ubiquity installer packages (apt pin during the build) |
| Live session | casper; live account `nexus-live` (passwordless sudo, live only); "Install NexusOS" on the desktop |
| Installer | Calamares with `calamares-settings-nexusos` (see `installer/`) |
| Boot splash | `plymouth-theme-nexusos` in the initrd |
| BIOS boot | GRUB El Torito image + `boot_hybrid.img` MBR (CD and USB) |
| UEFI boot | Canonical-signed `shim` + `gcdx64.efi.signed` in an appended EFI partition (Secure Boot capable) |
| Menu | `iso/production/grub.cfg`: Try or Install, safe graphics, verbose/serial troubleshooting |
| On-disc pool | `shim-signed`, `grub-efi-amd64-signed`, `grub-efi-amd64-bin` for the installer's EFI step (`/etc/apt/sources.list.d/cdrom.sources`, `Trusted: yes` until a NexusOS archive key exists) |
| Installed system | `ubuntu.sources` pointing at the Ubuntu archive; installer, casper and the cdrom source removed |

Layout follows Ubuntu desktop images (`casper/vmlinuz`, `casper/initrd`,
`casper/filesystem.squashfs` (zstd), `.disk/info`, `md5sum.txt`), so Calamares' shared Ubuntu
modules work unchanged.

## Test it (VM only)

```bash
# UEFI (OVMF), 8 GB RAM, KVM:
qemu-system-x86_64 -enable-kvm -m 8192 -smp 4 -machine q35 \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
  -drive if=pflash,format=raw,file=ovmf-vars.fd \
  -cdrom build/iso/nexusos-1.0-dev-*.iso -drive file=nexusos-test.qcow2,if=virtio \
  -vga virtio -display gtk
# create the virtual disk first: qemu-img create -f qcow2 nexusos-test.qcow2 60G
# copy the vars template: cp /usr/share/OVMF/OVMF_VARS_4M.fd ovmf-vars.fd
```

Then follow the checklist in [`docs/installation.md`](../../docs/installation.md#option-c--nexusos-test-iso-in-a-vm).

Automated boot test (QEMU in a container, no host disks):
`scripts/validation/iso-boot-smoke.sh build/iso/nexusos-*.iso --live-minutes 40`.
Last result (2026-11-14, `nexusos-1.0-dev-20261114`, software emulation): all 16 checks pass:
BIOS GRUB menu, UEFI with Secure Boot enforced (shim, Canonical-signed GRUB), live console
login, systemd `running` with no failed units, SDDM autologin into Plasma on Wayland, KWin,
plasmashell, os-release, `nexus` CLI, Command Center and installer, desktop install icon,
boot splash, console banner. The installation itself (Calamares to a virtual disk) has not
been run automatically yet; use the manual checklist.

## Before a release

1. Signed NexusOS APT archive and `nexusos-archive-keyring` (also signs the on-disc pool).
2. Reproducible builds from a snapshot (`snapshot.ubuntu.com`), SBOM, signed `SHA256SUMS`.
3. CI job (manual trigger, protected branch) with QEMU/OVMF boot and unattended install tests.
4. Firefox (snap seeding) or another default browser decision; SDDM theme.
