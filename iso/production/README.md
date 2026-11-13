# Production ISO pipeline (planned)

Status: **design only — no production ISO has been built.** Nothing in this
directory produces an image yet. The prototype (`iso/prototype/`) must pass
VM testing and the branding/theme/CLI review first.

## Goals

* Reproducible: the same commit and archive snapshot produce the same package set.
* Built from manifests: `manifests/*.yaml` are the only package source of truth.
* Unprivileged on the host: everything runs in a disposable container or VM.
* Verifiable: every image ships `SHA256SUMS`, a package manifest and an SBOM.

## Planned pipeline

```
manifests/*.yaml ──► resolve package set (snapshot.ubuntu.com @ timestamp)
packages/*       ──► build .debs in ubuntu:26.04 container ──► local APT repo (reprepro, signed)
                                    │
                                    ▼
              mmdebstrap --variant=minbase resolute rootfs  (unshare mode, no host root)
                                    │  + base/desktop/development/infrastructure packages
                                    │  + nexusos-* packages from local repo
                                    │  + casper, calamares, calamares-settings (NexusOS branding)
                                    ▼
              mksquashfs (zstd) ─► casper/filesystem.squashfs + filesystem.manifest
                                    │
                                    ▼
              GRUB EFI + shim (signed, from the archive) ─► xorriso hybrid ISO (UEFI + BIOS)
                                    │
                                    ▼
              QEMU/OVMF smoke tests (boot to SDDM, Calamares to completion on a qcow2 disk)
                                    │
                                    ▼
              SHA256SUMS + SHA512SUMS + SBOM (syft/spdx) ─► draft GitHub release (manual approval)
```

### Tool choice

| Option | Notes |
|--------|-------|
| **mmdebstrap + custom assembly** (preferred) | Small, scriptable, runs without host root in unshare mode, fully driven by our manifests. |
| `livecd-rootfs` + `live-build` | What Launchpad uses for official Ubuntu images; heavier and tied to Launchpad conventions, but closest to upstream behaviour. Evaluate if Calamares/casper integration proves fragile. |
| Cubic | Manual remastering; stays the prototype tool only. |

All of `mmdebstrap`, `squashfs-tools`, `xorriso`, `grub-efi-amd64-signed`,
`shim-signed`, `casper`, `calamares` and `livecd-rootfs` are in the resolute archive.

### Secure Boot

Use Canonical-signed `shim-signed` and `grub-efi-amd64-signed` with the
Ubuntu-signed kernel unchanged. NexusOS does not ship its own kernel or
bootloader signing keys.

## Remaining work

1. `iso/production/build.sh` implementing the pipeline above in a container.
2. NexusOS Calamares branding (`/usr/share/calamares/branding/nexusos/`).
3. Finished Plymouth and SDDM themes.
4. QEMU smoke-test harness and CI job (manual trigger, protected branch only).
5. Release signing key management (see `docs/release-process.md`).
