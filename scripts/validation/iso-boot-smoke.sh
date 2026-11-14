#!/usr/bin/env bash
# Boot-smoke-test a NexusOS ISO in QEMU inside a disposable container (VM only; no host disks).
#
#   scripts/validation/iso-boot-smoke.sh build/iso/nexusos-*.iso [--out DIR] [--live-minutes N]
#
# Checks, with screenshots in --out (default build/iso/smoke):
#   1. legacy BIOS: GRUB shows the NexusOS menu
#   2. UEFI with Secure Boot enforced (OVMF + Microsoft keys): shim -> Canonical-signed GRUB
#      -> NexusOS menu (proves the signed boot chain on the medium)
#   3. live boot (kernel/initrd from the ISO, serial console): casper finds the medium and
#      the squashfs, systemd reaches the graphical target and SDDM starts
# Uses KVM when /dev/kvm exists, otherwise software emulation (slow: allow ~20 minutes).
set -euo pipefail

ISO=""
OUT=""
LIVE_MIN=25
while [ $# -gt 0 ]; do
    case "$1" in
        --out) OUT="$(realpath -m "$2")"; shift 2 ;;
        --live-minutes) LIVE_MIN="$2"; shift 2 ;;
        -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
        *) ISO="$(realpath "$1")"; shift ;;
    esac
done
[ -f "$ISO" ] || { echo "usage: $0 path/to.iso" >&2; exit 2; }
OUT=${OUT:-$(dirname "$ISO")/smoke}
mkdir -p "$OUT"
kvm_args=()
[ -e /dev/kvm ] && kvm_args=(--device /dev/kvm)

docker run --rm "${kvm_args[@]}" -e LIVE_MIN="$LIVE_MIN" -v "$ISO:/test.iso:ro" -v "$OUT:/out" ubuntu:26.04 bash -euo pipefail -c '
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
cyan = sum(1 for p in img.getdata() if p[2] > 150 and p[1] > 150 and p[0] < 80)
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

echo "== 3. live boot (serial console, up to ${LIVE_MIN} min)"
mkdir -p /tmp/k && cd /tmp/k
xorriso -osirrox on -indev /test.iso -extract /casper/vmlinuz vmlinuz -extract /casper/initrd initrd >/dev/null 2>&1
qemu-system-x86_64 $accel -m 4096 -smp 4 -machine q35 -display none -qmp unix:/tmp/live.qmp,server,nowait \
    -cdrom /test.iso -kernel vmlinuz -initrd initrd \
    -append "boot=casper console=ttyS0,115200n8 systemd.show_status=1 ---" \
    -serial file:/out/live-serial.log &
pid=$!
deadline=$(( $(date +%s) + LIVE_MIN * 60 ))
while [ "$(date +%s)" -lt "$deadline" ]; do
    sleep 20
    grep -qE "Started (sddm|SDDM).*|Reached target .*[Gg]raphical" /out/live-serial.log 2>/dev/null && break
done
sleep 60   # let SDDM autologin start Plasma
shot /tmp/live.qmp live-desktop
kill $pid 2>/dev/null; wait $pid 2>/dev/null || true
grep -q "squashfs" /out/live-serial.log && pass "live: casper found the medium and mounted filesystem.squashfs" || fail "casper medium/squashfs (see live-serial.log)"
grep -qE "Reached target .*[Gg]raphical" /out/live-serial.log && pass "live: systemd reached the graphical target" || fail "graphical target not reached in ${LIVE_MIN} min"
grep -qiE "Started.*(sddm|Simple Desktop Display Manager)" /out/live-serial.log && pass "live: SDDM started" || fail "SDDM not started"
grep -E "\[FAILED\]" /out/live-serial.log | sed "s/^/      /" | head -20 || true
echo "screenshots and serial log: /out"
exit $fails
'
