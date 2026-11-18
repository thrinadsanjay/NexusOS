#!/usr/bin/env bash
# Boot-smoke-test a NexusOS ISO in QEMU inside a disposable container (VM only; no host disks).
#
#   scripts/validation/iso-boot-smoke.sh build/iso/nexusos-*.iso [--out DIR] [--live-minutes N]
#
# Checks, with screenshots in --out (default build/iso/smoke):
#   1. legacy BIOS: GRUB shows the NexusOS menu
#   2. UEFI with Secure Boot enforced (OVMF + Microsoft keys): shim -> Canonical-signed GRUB
#      -> NexusOS menu (proves the signed boot chain on the medium)
#   3. live boot (kernel/initrd from the ISO): log in as the live account on the serial
#      console and check systemd, SDDM autologin into a Plasma Wayland session, KWin,
#      plasmashell, no failed units, the CLI, Command Center, installer icon, splash, banner
# Uses KVM when /dev/kvm exists, otherwise software emulation (slow: allow ~20 minutes).
set -euo pipefail

ISO=""
OUT=""
LIVE_MIN=25
LAYOUT=""
while [ $# -gt 0 ]; do
    case "$1" in
        --out) OUT="$(realpath -m "$2")"; shift 2 ;;
        --live-minutes) LIVE_MIN="$2"; shift 2 ;;
        --layout-test) LAYOUT=1; shift ;;   # + virtual disk: LVM layout helper, desktop panels, installer start
        -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
        *) ISO="$(realpath "$1")"; shift ;;
    esac
done
[ -f "$ISO" ] || { echo "usage: $0 path/to.iso" >&2; exit 2; }
OUT=${OUT:-$(dirname "$ISO")/smoke}
mkdir -p "$OUT"
kvm_args=()
[ -e /dev/kvm ] && kvm_args=(--device /dev/kvm)

docker run --rm "${kvm_args[@]}" -e LIVE_MIN="$LIVE_MIN" -e LAYOUT_TEST="$LAYOUT" -v "$ISO:/test.iso:ro" -v "$OUT:/out" \
    -v "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/iso-live-checks.py:/checks/iso-live-checks.py:ro" \
    -v "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/installer/live/nexusos-lvm-layout:/checks/nexusos-lvm-layout:ro" \
    -e LVM_TOOL_OVERRIDE="${LVM_TOOL_OVERRIDE:+/checks/nexusos-lvm-layout}" ubuntu:26.04 bash -euo pipefail -c '
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq --no-install-recommends qemu-system-x86 ovmf python3 python3-pil \
    xorriso socat >/dev/null
pass() { printf "PASS  %s\n" "$*"; }
fail() { printf "FAIL  %s\n" "$*"; fails=$((fails + 1)); }
fails=0
accel="-accel tcg,thread=multi"; [ -e /dev/kvm ] && accel="-accel kvm"

shot() {  # shot QMP_SOCKET NAME
    printf "{\"execute\":\"qmp_capabilities\"}\n{\"execute\":\"screendump\",\"arguments\":{\"filename\":\"/tmp/$2.ppm\"}}\n" \
        | socat - UNIX-CONNECT:"$1" >/dev/null 2>&1 || true
    sleep 1
    python3 -c "from PIL import Image; Image.open(\"/tmp/$2.ppm\").save(\"/out/$2.png\")" 2>/dev/null || true
}
dark_teal() {  # the NexusOS GRUB menu highlight (black on cyan) is present in the screenshot
    python3 - "$1" <<"PY"
import sys
from PIL import Image
img = Image.open(sys.argv[1]).convert("RGB")
pixels = img.get_flattened_data() if hasattr(img, "get_flattened_data") else img.getdata()
cyan = sum(1 for p in pixels if p[2] > 150 and p[1] > 150 and p[0] < 80)
sys.exit(0 if cyan > 500 else 1)
PY
}
run_menu() {  # run_menu NAME QEMU-ARGS...  -> screenshot of the boot menu after a few seconds
    name=$1; shift
    qemu-system-x86_64 $accel -m 2048 -smp 2 -display none -qmp unix:/tmp/$name.qmp,server,nowait \
        -cdrom /test.iso -boot d "$@" &
    pid=$!
    for _ in $(seq 1 90); do sleep 2; shot /tmp/$name.qmp "$name-menu"; [ -f "/out/$name-menu.png" ] && dark_teal "/out/$name-menu.png" && break; done
    kill $pid 2>/dev/null; wait $pid 2>/dev/null || true
    [ -f "/out/$name-menu.png" ] && dark_teal "/out/$name-menu.png"
}

echo "== 1. legacy BIOS"
if run_menu bios -machine pc; then pass "BIOS: GRUB boots from the ISO and shows the NexusOS menu"; else fail "BIOS boot menu"; fi

echo "== 2. UEFI with Secure Boot enforced"
cp /usr/share/OVMF/OVMF_VARS_4M.ms.fd /tmp/vars.fd
if run_menu uefi-secureboot -machine q35,smm=on -global driver=cfi.pflash01,property=secure,value=on \
    -drive if=pflash,format=raw,unit=0,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.secboot.fd \
    -drive if=pflash,format=raw,unit=1,file=/tmp/vars.fd; then
    pass "UEFI Secure Boot: shim and Canonical-signed GRUB load and show the NexusOS menu"
else
    fail "UEFI Secure Boot menu"
fi

echo "== 3. live boot to the Plasma desktop (serial console login, up to ${LIVE_MIN} min)"
mkdir -p /tmp/k && cd /tmp/k
xorriso -osirrox on -indev /test.iso -extract /casper/vmlinuz vmlinuz -extract /casper/initrd initrd >/dev/null 2>&1
disk_args=""
if [ -n "${LAYOUT_TEST:-}" ]; then   # an empty virtual disk inside this container (VM only, never a host disk)
    apt-get install -y -qq --no-install-recommends qemu-utils >/dev/null
    qemu-img create -q -f qcow2 /tmp/disk.qcow2 40G
    disk_args="-drive file=/tmp/disk.qcow2,if=virtio,format=qcow2"
fi
qemu-system-x86_64 $accel -m 6144 -smp 4 -machine q35 -vga std -display none -qmp unix:/tmp/live.qmp,server,nowait \
    -cdrom /test.iso -kernel vmlinuz -initrd initrd $disk_args -qmp unix:/tmp/checks.qmp,server,nowait \
    -append "boot=casper quiet splash console=tty0 console=ttyS0,115200n8 ---" \
    -serial unix:/tmp/serial.sock,server,nowait &
pid=$!
QMP_SOCKET=/tmp/checks.qmp python3 /checks/iso-live-checks.py /tmp/serial.sock /out "$LIVE_MIN" || fails=$((fails + $?))
sleep 20
shot /tmp/live.qmp live-desktop
kill $pid 2>/dev/null; wait $pid 2>/dev/null || true
echo "screenshots and serial log: /out"
exit $fails
'
