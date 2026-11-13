#!/usr/bin/env bash
# Create a DISPOSABLE Ubuntu 26.04 test VM for NexusOS (QEMU/KVM, qcow2 overlay file).
#
#   scripts/development/vm/create-test-vm.sh [--dir ~/nexusos-vm] [--memory 8192] [--cpus 4] [--disk 60G]
#
# * Downloads the official Ubuntu 26.04 cloud image and verifies it against SHA256SUMS.
# * Creates a qcow2 overlay disk *file* and a cloud-init seed (user `nexus`, your SSH key,
#   Kubuntu desktop, Docker, NGINX). Physical disks are never touched; block devices are refused.
# * Starts QEMU with UEFI (OVMF), user-mode networking and SSH on localhost:2222.
# Requires: qemu-system-x86, qemu-utils, ovmf, cloud-image-utils, curl, an SSH public key.
# Status: written for the NexusOS test workflow; not executed in CI (needs KVM).
set -euo pipefail

DIR="$HOME/nexusos-vm"; MEM=8192; CPUS=4; DISK=60G
while [ $# -gt 0 ]; do
    case "$1" in
        --dir) DIR="$2"; shift 2 ;;
        --memory) MEM="$2"; shift 2 ;;
        --cpus) CPUS="$2"; shift 2 ;;
        --disk) DISK="$2"; shift 2 ;;
        -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
        *) echo "unknown option $1" >&2; exit 2 ;;
    esac
done
for tool in qemu-system-x86_64 qemu-img cloud-localds curl sha256sum; do
    command -v "$tool" >/dev/null || { echo "missing $tool (sudo apt install qemu-system-x86 qemu-utils ovmf cloud-image-utils)" >&2; exit 1; }
done
case "$DIR" in /dev/*) echo "refusing to use a device path" >&2; exit 1 ;; esac
PUBKEY="$(cat "$HOME"/.ssh/id_ed25519.pub 2>/dev/null || cat "$HOME"/.ssh/id_rsa.pub 2>/dev/null || true)"
[ -n "$PUBKEY" ] || { echo "no SSH public key in ~/.ssh (ssh-keygen -t ed25519)" >&2; exit 1; }

mkdir -p "$DIR" && cd "$DIR"
BASE="https://cloud-images.ubuntu.com/releases/resolute/release"
IMG="ubuntu-26.04-server-cloudimg-amd64.img"
if [ ! -f "$IMG" ]; then
    curl -fLO "$BASE/$IMG"
    curl -fsSL "$BASE/SHA256SUMS" -o SHA256SUMS
    grep " \*\?$IMG\$" SHA256SUMS | sha256sum --check -
fi
[ -f nexusos-test.qcow2 ] || qemu-img create -f qcow2 -F qcow2 -b "$IMG" nexusos-test.qcow2 "$DISK"

cat > user-data <<CLOUD
#cloud-config
hostname: nexusos-test
users:
  - name: nexus
    groups: [sudo]
    shell: /bin/bash
    sudo: "ALL=(ALL) NOPASSWD:ALL"
    ssh_authorized_keys: ["$PUBKEY"]
package_update: true
packages: [kubuntu-desktop, sddm, docker.io, docker-compose-v2, nginx, openssh-server, smartmontools, udisks2]
runcmd:
  - [systemctl, set-default, graphical.target]
CLOUD
printf 'instance-id: nexusos-test\nlocal-hostname: nexusos-test\n' > meta-data
cloud-localds seed.img user-data meta-data

OVMF=/usr/share/ovmf/OVMF.fd
exec qemu-system-x86_64 -enable-kvm -machine q35 -cpu host -smp "$CPUS" -m "$MEM" \
    -bios "$OVMF" -drive file=nexusos-test.qcow2,if=virtio -drive file=seed.img,if=virtio,format=raw \
    -nic user,model=virtio-net-pci,hostfwd=tcp:127.0.0.1:2222-:22 -device virtio-vga -display gtk
