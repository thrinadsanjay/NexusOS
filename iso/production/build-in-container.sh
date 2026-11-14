#!/bin/bash
# shellcheck disable=SC2016  # mmdebstrap hooks and dpkg-query formats are expanded by those tools
# Build the NexusOS test ISO. Runs INSIDE a disposable ubuntu:26.04 container started by
# iso/production/build.sh: /repo (read-only checkout), /debs (NexusOS .debs), /out (results).
# Everything is written below $WORK in the container; no host disk or device is touched.
set -euo pipefail

WORK=${WORK:-/work}
ROOTFS=$WORK/rootfs
ISO=$WORK/iso
REPO=/repo
SUITE=resolute
ARCHIVE=${NEXUSOS_ARCHIVE:-http://archive.ubuntu.com/ubuntu}
SECURITY=${NEXUSOS_SECURITY_ARCHIVE:-http://security.ubuntu.com/ubuntu}
STAMP=$(date -u +%Y%m%d)
NAME=${NEXUSOS_ISO_NAME:-nexusos-1.0-dev-$STAMP-amd64}
VOLID="NexusOS 1.0 dev amd64"

log() { printf '\n== %s\n' "$*"; }
in_root() { chroot "$ROOTFS" /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin LANG=C.UTF-8 DEBIAN_FRONTEND=noninteractive "$@"; }

mounted=()
mount_chroot() {
    for m in dev dev/pts proc sys run; do mkdir -p "$ROOTFS/$m"; done
    mount --bind /dev "$ROOTFS/dev" && mounted+=("$ROOTFS/dev")
    mount -t devpts devpts "$ROOTFS/dev/pts" && mounted+=("$ROOTFS/dev/pts")
    mount -t proc proc "$ROOTFS/proc" && mounted+=("$ROOTFS/proc")
    mount -t sysfs sysfs "$ROOTFS/sys" && mounted+=("$ROOTFS/sys")
    mount -t tmpfs tmpfs "$ROOTFS/run" && mounted+=("$ROOTFS/run")
}
umount_chroot() {
    local i
    for ((i = ${#mounted[@]} - 1; i >= 0; i--)); do umount -l "${mounted[$i]}" 2>/dev/null || true; done
    mounted=()
}
trap umount_chroot EXIT

# ---------------------------------------------------------------------------- tools
log "build tools"
export DEBIAN_FRONTEND=noninteractive
if command -v update-ca-certificates >/dev/null; then update-ca-certificates >/dev/null 2>&1 || true; fi
apt-get update -qq
apt-get install -y -qq --no-install-recommends mmdebstrap squashfs-tools xorriso grub-pc-bin grub-efi-amd64-bin \
    grub-efi-amd64-signed shim-signed grub2-common grub-common mtools dosfstools dpkg-dev apt-utils python3-yaml \
    ca-certificates zstd gpg >/dev/null

# ---------------------------------------------------------------------------- local repository of NexusOS packages
log "local NexusOS package repository"
mkdir -p "$WORK/localrepo"
cp /debs/*.deb "$WORK/localrepo/"
(cd "$WORK/localrepo" && apt-ftparchive packages . > Packages && apt-ftparchive release . > Release)
find "$WORK/localrepo" -name '*.deb' -printf '   %f\n' | sort

# ---------------------------------------------------------------------------- root filesystem
PKGS=$(python3 "$REPO/iso/production/package-set.py" "$REPO/manifests" base desktop)
log "root filesystem: $(tr ',' '\n' <<<"$PKGS" | wc -l) requested packages (+ dependencies and recommends)"
rm -rf "$ROOTFS"
mmdebstrap --mode=root --variant=apt --format=directory \
    --components=main,restricted,universe,multiverse \
    --aptopt='APT::Install-Recommends "true"' \
    --aptopt='Acquire::Retries "5"' \
    --setup-hook='mkdir -p "$1/etc/apt/preferences.d"' \
    --setup-hook='printf "Package: plasma-discover* flatpak snapd ubiquity* kubuntu-*\nPin: version *\nPin-Priority: -1\n" > "$1/etc/apt/preferences.d/nexusos-image.pref"' \
    --include="$PKGS" \
    "$SUITE" "$ROOTFS" \
    "deb $ARCHIVE $SUITE main restricted universe multiverse" \
    "deb $ARCHIVE $SUITE-updates main restricted universe multiverse" \
    "deb $SECURITY $SUITE-security main restricted universe multiverse" \
    "deb [trusted=yes] copy://$WORK/localrepo ./"

# ---------------------------------------------------------------------------- configure the image
log "configure the image"
rm -f "$ROOTFS/etc/apt/sources.list" "$ROOTFS/etc/apt/sources.list.d/"*.list "$ROOTFS/etc/apt/preferences.d/nexusos-image.pref"
cat > "$ROOTFS/etc/apt/sources.list.d/ubuntu.sources" <<EOF
Types: deb
URIs: http://archive.ubuntu.com/ubuntu
Suites: $SUITE $SUITE-updates $SUITE-backports
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg

Types: deb
URIs: http://security.ubuntu.com/ubuntu
Suites: $SUITE-security
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
EOF
# The installer's EFI step installs shim-signed and the signed GRUB from the medium.
# Test image: the on-disc repository is not signed yet (a NexusOS archive key is planned).
cat > "$ROOTFS/etc/apt/sources.list.d/cdrom.sources" <<EOF
Types: deb
URIs: file:/cdrom
Suites: $SUITE
Components: main
Trusted: yes
EOF
install -m 0644 "$REPO/iso/production/casper.conf" "$ROOTFS/etc/casper.conf"
echo nexusos > "$ROOTFS/etc/hostname"
printf '127.0.0.1\tlocalhost\n127.0.1.1\tnexusos\n::1\tlocalhost ip6-localhost ip6-loopback\n' > "$ROOTFS/etc/hosts"

mount_chroot
in_root locale-gen en_US.UTF-8 >/dev/null
in_root update-locale LANG=en_US.UTF-8
in_root update-alternatives --query default.plymouth | sed -n 's/^Value: /   plymouth theme: /p'
log "initramfs (casper + NexusOS splash)"
in_root update-initramfs -u -k all 2>&1 | tail -2
in_root apt-get clean
umount_chroot

: > "$ROOTFS/etc/machine-id"
rm -f "$ROOTFS/var/lib/dbus/machine-id"
rm -rf "$ROOTFS/var/lib/apt/lists/"* "$ROOTFS/tmp/"* "$ROOTFS/var/tmp/"* "$ROOTFS/root/.cache"
find "$ROOTFS/var/log" -type f -exec truncate -s 0 {} +

# ---------------------------------------------------------------------------- ISO tree
log "ISO tree"
rm -rf "$ISO"
mkdir -p "$ISO/casper" "$ISO/.disk" "$ISO/boot/grub/i386-pc" "$ISO/boot/grub/fonts" "$ISO/EFI/boot"
kernel=$(find "$ROOTFS/boot" -maxdepth 1 -name 'vmlinuz-*' | sort -V | tail -1)
kver=${kernel##*/vmlinuz-}
cp "$kernel" "$ISO/casper/vmlinuz"
cp "$ROOTFS/boot/initrd.img-$kver" "$ISO/casper/initrd"
echo "   kernel $kver"
chroot "$ROOTFS" dpkg-query -W --showformat='${Package} ${Version}\n' > "$ISO/casper/filesystem.manifest"
du -sx --block-size=1 "$ROOTFS" | cut -f1 > "$ISO/casper/filesystem.size"

printf 'NexusOS Engineering Edition 1.0 (development) "Resolute" - amd64 (%s)\n' "$STAMP" > "$ISO/.disk/info"
touch "$ISO/.disk/base_installable"
echo "full_cd/single" > "$ISO/.disk/cd_type"

# On-disc package pool for the installer's EFI step (signed shim and GRUB).
mkdir -p "$ISO/pool/main" "$ISO/dists/$SUITE/main/binary-amd64"
(cd "$ISO/pool/main" && apt-get download -qq grub-efi-amd64-signed shim-signed grub-efi-amd64-bin 2>/dev/null)
(cd "$ISO" && apt-ftparchive packages pool > "dists/$SUITE/main/binary-amd64/Packages" \
    && gzip -k9 "dists/$SUITE/main/binary-amd64/Packages" \
    && apt-ftparchive -o APT::FTPArchive::Release::Suite="$SUITE" -o APT::FTPArchive::Release::Codename="$SUITE" \
       -o APT::FTPArchive::Release::Components=main -o APT::FTPArchive::Release::Architectures=amd64 \
       release "dists/$SUITE" > "dists/$SUITE/Release.tmp" && mv "dists/$SUITE/Release.tmp" "dists/$SUITE/Release")

log "squashfs (zstd)"
# Keep /proc, /sys, /dev and /run as EMPTY directories: casper mounts onto them at boot
# (excluding the directories themselves makes init fail: "mounting /dev on /root/dev failed").
mksquashfs "$ROOTFS" "$ISO/casper/filesystem.squashfs" -comp zstd -Xcompression-level 15 -b 1M -noappend -quiet \
    -wildcards -e 'proc/*' 'sys/*' 'dev/*' 'run/*' 'boot/efi/*'
echo "   $(du -h "$ISO/casper/filesystem.squashfs" | cut -f1) filesystem.squashfs"

# ---------------------------------------------------------------------------- boot loaders
log "boot loaders (BIOS: GRUB El Torito; UEFI: Canonical-signed shim + GRUB)"
install -m 0644 "$REPO/iso/production/grub.cfg" "$ISO/boot/grub/grub.cfg"
cp /usr/share/grub/unicode.pf2 "$ISO/boot/grub/fonts/"
cp /usr/lib/grub/i386-pc/*.mod /usr/lib/grub/i386-pc/*.lst "$ISO/boot/grub/i386-pc/"
grub-mkimage -O i386-pc-eltorito -p /boot/grub -o "$ISO/boot/grub/i386-pc/eltorito.img" \
    biosdisk iso9660 part_msdos part_gpt normal configfile search search_label search_fs_file \
    linux echo test all_video gfxterm font loadenv

shim=$(ls /usr/lib/shim/shimx64.efi.signed.latest 2>/dev/null || ls /usr/lib/shim/shimx64.efi.signed)
cp "$shim" "$ISO/EFI/boot/bootx64.efi"
cp /usr/lib/shim/mmx64.efi "$ISO/EFI/boot/mmx64.efi"
cp /usr/lib/grub/x86_64-efi-signed/gcdx64.efi.signed "$ISO/EFI/boot/grubx64.efi"

efi_img=$WORK/efi.img
rm -f "$efi_img"
mkfs.vfat -C -n NEXUSOS_EFI "$efi_img" 10240 >/dev/null
mmd -i "$efi_img" ::/EFI ::/EFI/boot
mcopy -i "$efi_img" "$ISO/EFI/boot/bootx64.efi" "$ISO/EFI/boot/mmx64.efi" "$ISO/EFI/boot/grubx64.efi" ::/EFI/boot/

# ---------------------------------------------------------------------------- hybrid ISO
log "hybrid ISO (BIOS + UEFI, CD and USB)"
(cd "$ISO" && find . -type f ! -name md5sum.txt ! -path './boot/grub/i386-pc/*' -print0 | sort -z | xargs -0 md5sum > "$WORK/md5sum.txt")
mv "$WORK/md5sum.txt" "$ISO/md5sum.txt"
mkdir -p /out
xorriso -as mkisofs -r -V "$VOLID" -o "/out/$NAME.iso" -J -joliet-long -l \
    --grub2-mbr /usr/lib/grub/i386-pc/boot_hybrid.img \
    -partition_offset 16 --mbr-force-bootable \
    -append_partition 2 28732ac11ff8d211ba4b00a0c93ec93b "$efi_img" -appended_part_as_gpt \
    -iso_mbr_part_type a2a0d0ebe5b9334487c068b6b72699c7 \
    -c /boot.catalog \
    -b /boot/grub/i386-pc/eltorito.img -no-emul-boot -boot-load-size 4 -boot-info-table --grub2-boot-info \
    -eltorito-alt-boot -e '--interval:appended_partition_2:::' -no-emul-boot \
    "$ISO" 2>&1 | grep -vE "^xorriso : (UPDATE|NOTE)" | tail -3

cp "$ISO/casper/filesystem.manifest" "/out/$NAME.manifest"
(cd /out && sha256sum "$NAME.iso" > "$NAME.iso.sha256" && sha512sum "$NAME.iso" > "$NAME.iso.sha512")
log "done: /out/$NAME.iso ($(du -h "/out/$NAME.iso" | cut -f1), $(wc -l < "/out/$NAME.manifest") packages)"
