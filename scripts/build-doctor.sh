#!/usr/bin/env bash
# shellcheck disable=SC2015  # ok/warn/fail never fail, so "A && ok || fail" is safe
# Check that this machine can build NexusOS packages and the test ISO, before spending an hour.
#
#   scripts/build-doctor.sh
#
# Read-only: it changes nothing on the host. It starts one short-lived privileged container
# (to prove Docker allows what the ISO build needs) and removes it. Each line is OK, WARN or FAIL;
# the exit code is the number of FAILs.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARCHIVE=${NEXUSOS_ARCHIVE:-http://archive.ubuntu.com/ubuntu}
NEED_GB=${NEXUSOS_ISO_MIN_FREE_GB:-30}
fails=0
ok() { printf '\033[32mOK  \033[0m  %s\n' "$*"; }
warn() { printf '\033[33mWARN\033[0m  %s\n' "$*"; }
fail() { printf '\033[31mFAIL\033[0m  %s\n' "$*"; fails=$((fails + 1)); }

# --- machine --------------------------------------------------------------------------------
arch=$(uname -m)
[ "$arch" = x86_64 ] && ok "CPU architecture x86_64" \
    || fail "CPU architecture $arch: NexusOS images are amd64 (x86_64) only"
if grep -qi microsoft /proc/version 2>/dev/null; then
    ok "running under WSL2"
    case "$REPO_ROOT" in
        /mnt/[a-z]/*) warn "checkout on a Windows drive ($REPO_ROOT): works, but slower; a clone under ~ is faster" ;;
    esac
fi
mem_gb=$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo)
if [ "$mem_gb" -ge 7 ]; then ok "memory ${mem_gb} GB"
elif [ "$mem_gb" -ge 4 ]; then warn "memory ${mem_gb} GB: works, 8 GB is more comfortable (Calamares compile, squashfs)"
else fail "memory ${mem_gb} GB: at least 4 GB needed"; fi
cpus=$(nproc)
[ "$cpus" -ge 4 ] && ok "$cpus CPU cores" || warn "$cpus CPU core(s): the first build (Calamares compile) can take over an hour"

# --- docker ---------------------------------------------------------------------------------
if ! command -v docker >/dev/null; then
    fail "docker not installed (https://docs.docker.com/engine/install/ubuntu/, or: curl -fsSL https://get.docker.com | sh)"
elif ! docker info >/dev/null 2>&1; then
    fail "docker installed but not usable by $(id -un): start it (sudo service docker start) or add yourself to the docker group"
else
    if docker info --format '{{.SecurityOptions}}' 2>/dev/null | grep -q rootless; then
        fail "rootless Docker: the ISO build needs privileged containers (use rootful Docker)"
    fi
    if docker run --rm --privileged ubuntu:26.04 sh -c 'mkdir -p /t/proc && mount -t proc proc /t/proc && umount /t/proc' >/dev/null 2>&1; then
        ok "Docker runs privileged containers (needed for the ISO build)"
    else
        fail "Docker cannot run privileged containers or pull ubuntu:26.04 (rootless Docker/Podman, CI runner or Kubernetes pod?)"
    fi
    docker_root=$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || echo /var/lib/docker)
    free_gb=$(df -P -B1G "$docker_root" 2>/dev/null | awk 'NR==2 {print $4}')
    if [ -z "$free_gb" ]; then warn "could not read free space for $docker_root"
    elif [ "$free_gb" -ge "$NEED_GB" ]; then ok "${free_gb} GB free for Docker ($docker_root)"
    else fail "${free_gb} GB free for Docker ($docker_root): the ISO build needs about ${NEED_GB} GB (enlarge the disk or docker system prune)"; fi
fi
out_free=$(df -P -B1G "$REPO_ROOT" | awk 'NR==2 {print $4}')
[ "$out_free" -ge 5 ] && ok "${out_free} GB free for build/ (packages, ISO, package cache)" \
    || fail "${out_free} GB free next to the checkout: build/ needs about 5 GB (ISO + package cache)"

# --- network and clock ------------------------------------------------------------------------
headers=$(curl -fsSI --max-time 20 "$ARCHIVE/dists/resolute/InRelease" 2>/dev/null)
if [ -z "$headers" ]; then
    fail "cannot reach $ARCHIVE (proxy? set http_proxy/https_proxy, or NEXUSOS_ARCHIVE to a reachable mirror)"
else
    ok "Ubuntu archive reachable ($ARCHIVE)"
    server=$(printf '%s\n' "$headers" | awk -F': ' 'tolower($1)=="date" {print $2}' | tr -d '\r')
    if [ -n "$server" ]; then
        skew=$(( $(date -u +%s) - $(date -u -d "$server" +%s) ))
        abs=${skew#-}
        if [ "$abs" -le 300 ]; then ok "clock correct (within ${abs} s of the archive)"
        else fail "clock off by $((abs / 3600)) h $((abs % 3600 / 60)) min: apt will reject the package lists. Fix: sudo date -u -s \"$server\""; fi
    fi
fi

# --- checkout ---------------------------------------------------------------------------------
if [ -d "$REPO_ROOT/.git" ] && command -v git >/dev/null; then
    crlf=$(git -C "$REPO_ROOT" ls-files --eol 2>/dev/null | awk '$2 ~ /crlf/' | wc -l)
    [ "$crlf" -eq 0 ] && ok "line endings LF" || fail "$crlf file(s) checked out with CRLF: git config core.autocrlf false, then re-checkout (see README)"
fi
if ls "$REPO_ROOT"/build/debs/calamares_*nexusos*.deb >/dev/null 2>&1; then
    ok "NexusOS Calamares already built (next package build skips the long compile)"
else
    warn "first build compiles the NexusOS Calamares (20-90 min, once)"
fi

echo
[ "$fails" -eq 0 ] && echo "Ready: scripts/package/build-in-container.sh && iso/production/build.sh" \
    || echo "$fails problem(s) to fix before building."
exit "$fails"
