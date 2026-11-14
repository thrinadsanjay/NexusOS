#!/usr/bin/env bash
# Verify NexusOS packages in a real KDE Plasma 6 Wayland session inside a disposable container.
#
#   scripts/validation/plasma-session-container.sh [DEB_DIR] [--screenshots DIR] [--keep]
#
# Boots systemd (PID 1, private cgroup v2) in a privileged *container* — nothing is installed
# on the host and no host disk or device is touched — then checks:
#   * nexusos-agent.socket (root:sudo 0660), its polkit actions, and that the agent
#       - refuses an administrator without a polkit authentication agent,
#       - installs a package once a test-only polkit rule grants the action, and audits it,
#       - still refuses actions the rule does not grant, and users outside the sudo group;
#   * a headless KWin Wayland + plasmashell session (software rendering) for user "nexus":
#     NexusOS global theme, colours, icons, fonts, Konsole profile, panel/dock layout, wallpaper;
#   * the Command Center on Wayland: every module loads without QML warnings, memory budgets;
#   * desktop integration: KCM catalogue vs kcmshell6, Konsole tabs, systemd state, polkit.
#
# Needs Docker with --privileged (systemd in a container). Not run in hosted CI.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEB_DIR="$REPO_ROOT/build/debs"
SHOTS=""
KEEP=0
while [ $# -gt 0 ]; do
    case "$1" in
        --screenshots) SHOTS="$(realpath -m "$2")"; shift 2 ;;
        --keep) KEEP=1; shift ;;
        -h|--help) sed -n '2,17p' "$0"; exit 0 ;;
        *) DEB_DIR="$(realpath "$1")"; shift ;;
    esac
done
ls "$DEB_DIR"/nexusos-command-center_*.deb >/dev/null 2>&1 || { echo "no packages in $DEB_DIR (run scripts/package/build-in-container.sh)" >&2; exit 1; }

IMAGE=nexusos-plasma-test:latest
NAME="nexusos-plasma-$$"
CTX="$(mktemp -d)"
cleanup() {
    [ "$KEEP" = 1 ] && echo "container kept: docker exec -it $NAME bash   (docker rm -f $NAME)" || docker rm -f "$NAME" >/dev/null 2>&1 || true
    rm -r -- "$CTX"
}
trap cleanup EXIT

cp "$REPO_ROOT"/scripts/validation/plasma/{Dockerfile,entry.sh,session.sh,env.sh,session-checks.sh} "$CTX/"
mkdir "$CTX/debs" && cp "$DEB_DIR"/*.deb "$CTX/debs/"
build_args=()
for var in http_proxy https_proxy HTTP_PROXY HTTPS_PROXY no_proxy NO_PROXY; do
    [ -n "${!var:-}" ] && build_args+=(--build-arg "$var")
done
echo "== building $IMAGE (Ubuntu 26.04 + Plasma + NexusOS packages)"
docker build -q "${build_args[@]}" -t "$IMAGE" "$CTX" >/dev/null

docker run -d -t --name "$NAME" --privileged --cgroupns=private --tmpfs /run --tmpfs /run/lock "$IMAGE" >/dev/null
for _ in $(seq 60); do
    state=$(docker exec "$NAME" systemctl is-system-running 2>/dev/null || true)
    case "$state" in running|degraded) break ;; esac
    sleep 1
done
echo "== systemd: $state"

fails=0
docker exec -i "$NAME" bash -s <<'ROOT' || fails=$((fails + $?))
set -u
fails=0
pass() { printf "PASS  %s\n" "$*"; }
fail() { printf "FAIL  %s\n" "$*"; fails=$((fails + 1)); }
. /etc/os-release
[ "$PRETTY_NAME" = "NexusOS Engineering Edition 1.0" ] && pass "os-release: $PRETTY_NAME" || fail "os-release: $PRETTY_NAME"
systemctl is-active -q nexusos-agent.socket && pass "nexusos-agent.socket active" || fail "nexusos-agent.socket"
perm=$(stat -c '%U:%G %a' /run/nexusos/agent.sock 2>/dev/null)
[ "$perm" = "root:sudo 660" ] && pass "agent socket $perm" || fail "agent socket permissions: $perm"
n=$(pkaction | grep -c '^org\.nexusos\.agent\.')
[ "$n" -eq 7 ] && pass "7 polkit actions registered" || fail "polkit actions: $n"

agent() {  # agent USER OP JSON -> prints "ok" or the error message
    su "$1" -c "python3 -c 'import json,sys
from nexus_core import agent_client
try:
    agent_client.call(sys.argv[1], json.loads(sys.argv[2])); print(\"ok\")
except Exception as e:
    print(type(e).__name__, e)' $2 '$3'" 2>&1 | tail -1
}
r=$(agent nexus apt.install '{"packages":["hello"]}')
case "$r" in *uthoriz*|*denied*) pass "administrator without a polkit agent is refused ($r)";; *) fail "unauthenticated install: $r";; esac
# Test-only rule: grant the package action (and nothing else) to the test administrator.
cat > /etc/polkit-1/rules.d/49-nexusos-test.rules <<'RULE'
polkit.addRule(function(action, subject) {
    if (action.id == "org.nexusos.agent.packages.manage" && subject.user == "nexus") return polkit.Result.YES;
});
RULE
sleep 2
r=$(agent nexus apt.install '{"packages":["hello"]}')
[ "$r" = ok ] && dpkg -s hello >/dev/null 2>&1 && pass "socket-activated agent installed 'hello' after polkit authorization" || fail "authorized install: $r"
grep -q '"user": *"nexus"' /var/log/nexusos/agent-audit.log 2>/dev/null && pass "operation recorded in the agent audit log" || fail "audit log"
r=$(agent nexus apt.repo.remove '{"name":"nexus-test"}')
case "$r" in *uthoriz*|*denied*) pass "actions outside the grant stay refused";; *) fail "repo.remove: $r";; esac
r=$(agent guest agent.ping '{}')
case "$r" in *ermission*|*denied*|*navailable*) pass "non-administrator cannot reach the agent socket";; *) fail "guest: $r";; esac
rm -f /etc/polkit-1/rules.d/49-nexusos-test.rules
exit $fails
ROOT

U=$(docker exec "$NAME" id -u nexus)
docker exec "$NAME" systemctl start "user@$U" >/dev/null
echo "== starting Plasma (KWin Wayland, virtual output) for user nexus"
docker exec "$NAME" su nexus -c /opt/nexusos-plasma/session.sh
docker exec "$NAME" su nexus -c "/opt/nexusos-plasma/session-checks.sh ${SHOTS:+/tmp/nexus-shots}" || fails=$((fails + $?))
if [ -n "$SHOTS" ]; then
    mkdir -p "$SHOTS"
    docker exec "$NAME" tar -C /tmp/nexus-shots -c . | tar -x -C "$SHOTS"
    echo "screenshots: $SHOTS"
fi

if [ "$fails" -eq 0 ]; then echo "ALL PLASMA SESSION CHECKS PASSED"; else echo "$fails check(s) FAILED"; exit 1; fi
