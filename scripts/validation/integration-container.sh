#!/usr/bin/env bash
# End-to-end integration tests for NexusOS 0.2 inside a disposable Ubuntu 26.04 container.
#
#   scripts/validation/integration-container.sh [DEB_DIR] [--image ubuntu:26.04]
#
# Covers, against the real distribution packages (no mocks):
#   * install of python3-nexus-core, nexusos-management-agent, nexusos-command-center,
#     nexus-cli, nexusos-gateway (+ NGINX), nexusos-branding, nexusos-defaults
#   * management agent: unknown ops / invalid input rejected, non-root caller denied when
#     polkit cannot authorize (fail closed), real `apt install` with progress events,
#     dpkg lock detection, audit log written
#   * gateway: internal-CA certificate, HTTPS route to a real backend, HTTP->HTTPS
#     redirect, LAN policy, SSRF refusal, broken certificate -> nginx -t fails ->
#     automatic rollback (previous route keeps serving)
#   * CLI on the target Python: packages/apps/gateway/ssh commands, no secrets printed
#   * Command Center: headless start, all 14 modules load without QML warnings, resource
#     report with Docker and Ollama absent
#   * nexusos-desktop dependency resolution (simulated; Plasma is large)
#
# Nothing touches the host: everything runs in a throwaway container.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEB_DIR="$REPO_ROOT/build/debs"
IMAGE="ubuntu:26.04"
while [ $# -gt 0 ]; do
    case "$1" in
        --image) IMAGE="$2"; shift 2 ;;
        -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
        *) DEB_DIR="$(realpath "$1")"; shift ;;
    esac
done
ls "$DEB_DIR"/nexusos-command-center_*.deb >/dev/null 2>&1 || { echo "no 0.2 packages in $DEB_DIR" >&2; exit 1; }

proxy_args=()
for var in http_proxy https_proxy HTTP_PROXY HTTPS_PROXY no_proxy NO_PROXY; do
    [ -n "${!var:-}" ] && proxy_args+=(-e "$var")
done
ca_args=()
if [ -n "${NEXUSOS_EXTRA_CA:-}" ] && [ -f "$NEXUSOS_EXTRA_CA" ]; then
    ca_args=(-v "$NEXUSOS_EXTRA_CA:/usr/local/share/ca-certificates/nexusos-extra.crt:ro")
fi
REPORT_DIR="$REPO_ROOT/build/integration"
mkdir -p "$REPORT_DIR"

docker run --rm "${proxy_args[@]}" "${ca_args[@]}" -v "$DEB_DIR:/debs:ro" -v "$REPORT_DIR:/report" "$IMAGE" bash -euo pipefail -c '
export DEBIAN_FRONTEND=noninteractive
pass() { printf "PASS  %s\n" "$*"; }
fail() { printf "FAIL  %s\n" "$*"; exit 1; }
command -v update-ca-certificates >/dev/null && update-ca-certificates >/dev/null 2>&1 || true
apt-get update -qq

# ------------------------------------------------------------------ install
apt-get install -y -qq /debs/python3-nexus-core_*.deb /debs/nexusos-management-agent_*.deb \
    /debs/nexusos-command-center_*.deb /debs/nexus-cli_*.deb /debs/nexusos-gateway_*.deb \
    /debs/nexusos-branding_*.deb /debs/nexusos-defaults_*.deb curl python3-paramiko >/tmp/install.log 2>&1 \
    || { tail -30 /tmp/install.log; fail "package installation"; }
pass "installed core, agent, command center, CLI, gateway (+nginx), branding, defaults"
for f in /usr/bin/nexus-center /usr/bin/nexus /usr/lib/nexusos/nexus-askpass /usr/share/polkit-1/actions/org.nexusos.agent.policy \
         /usr/lib/systemd/system/nexusos-agent.socket /etc/nginx/conf.d/nexusos-gateway.conf; do
    [ -e "$f" ] || fail "missing $f"
done
pass "installed paths present (binaries, polkit policy, socket unit, nginx include)"
[ -d /etc/nexusos/gateway/routes ] && [ "$(stat -c %a /etc/nexusos/gateway/ca)" = 700 ] && pass "gateway layout created by postinst (ca/ is 0700)"

# ------------------------------------------------------------------ agent (no systemd in containers: start it the way the socket unit would)
# This section tests the socket transport (SO_PEERCRED + polkit); the sudo transport is tested below.
export NEXUSOS_ADMIN_TRANSPORT=agent
useradd -m -G sudo alice
install -d -m 0755 /run/nexusos
export NEXUSOS_NGINX_RELOAD="nginx -s reload"
[ -s /proc/net/if_inet6 ] || sed -i "/\[::\]/d" /etc/nginx/sites-enabled/default  # container without IPv6
nginx
( python3 -m nexus_agent --socket /run/nexusos/agent.sock --socket-mode 660 --idle-timeout 0 >/tmp/agent.log 2>&1 & )
for i in $(seq 1 50); do [ -S /run/nexusos/agent.sock ] && break; sleep 0.1; done
chgrp sudo /run/nexusos/agent.sock
python3 - <<"PY"
from nexus_core import agent_client as a
assert a.call("agent.ping")["version"] == "0.2.0"
for op, params, code in [("rm -rf /", {}, "unknown-op"), ("apt.install", {"packages": ["bad name"]}, "invalid"),
                         ("apt.install", {"packages": ["hello"], "shell": "x"}, "invalid")]:
    try:
        a.call(op, params)
        raise SystemExit(f"{op} should fail")
    except a.AgentError as e:
        assert e.code == code, (op, e.code)
PY
pass "agent: ping ok; unknown operation, invalid package name and extra parameters rejected"

cat > /tmp/denied.py <<"PY"
from nexus_core import agent_client as a
try:
    a.call("apt.install", {"packages": ["hello"]})
    raise SystemExit(1)
except a.AgentError as e:
    assert e.code == "unauthorized", e.code
PY
su alice -c "NEXUSOS_ADMIN_TRANSPORT=agent python3 /tmp/denied.py" || fail "non-root caller must be denied without polkit"
dpkg -s hello >/dev/null 2>&1 && fail "hello installed by unauthorized user"
pass "agent: sudo-group user denied when polkit cannot authorize (fail closed)"

# ------------------------------------------------------------------ sudo transport (default): nexus-admin through the sudo rights of the user
# Disposable test accounts: "ops" has a NOPASSWD rule, "guest" has no sudo. (Password sudo,
# retries and sudo-rs vs sudo 1.9 are covered by scripts/validation/plasma-session-container.sh.)
command -v sudo >/dev/null || fail "sudo missing (nexusos-management-agent depends on sudo | sudo-rs)"
[ -x /usr/lib/nexusos/nexus-admin ] || fail "nexus-admin helper missing"
useradd -m ops && useradd -m guest
echo "ops ALL=(ALL:ALL) NOPASSWD: ALL" > /etc/sudoers.d/90-nexusos-test-ops && chmod 0440 /etc/sudoers.d/90-nexusos-test-ops
cat > /tmp/sudo_ok.py <<"PY"
from nexus_core import agent_client as a, privilege
def no_prompt(req):
    raise SystemExit("password box must not appear for NOPASSWD")
privilege.set_password_provider(no_prompt)
assert a.call("agent.ping")["version"] == "0.2.0"
try:
    a.call("service.control", {"unit": "systemd-journald.service", "action": "stop"})
    raise SystemExit("unit outside the allow-list was accepted")
except a.AgentError as e:
    assert e.code == "invalid", e.code
assert privilege.access().auth == "not-required"
PY
su ops -c "NEXUSOS_ADMIN_TRANSPORT=sudo python3 /tmp/sudo_ok.py" || fail "NOPASSWD sudo user could not run an admin task"
pass "sudo: NOPASSWD user runs admin tasks without a password box; allow-list still enforced"
cat > /tmp/sudo_denied.py <<"PY"
from nexus_core import agent_client as a, privilege
asked = []
privilege.set_password_provider(lambda req: asked.append(req) or "x")
try:
    a.call("apt.install", {"packages": ["hello"]})
    raise SystemExit("guest ran an admin task")
except privilege.AccessDeniedError:
    assert not asked, "guest was asked for a password"
assert privilege.access().admin == "none"
PY
su guest -c "NEXUSOS_ADMIN_TRANSPORT=sudo python3 /tmp/sudo_denied.py" || fail "user without sudo must be denied"
dpkg -s hello >/dev/null 2>&1 && fail "hello installed by a user without sudo"
grep -F "\"via\": \"sudo\"" /var/log/nexusos/agent-audit.log | grep -qF "\"user\": \"ops\"" || fail "sudo tasks missing from the audit log"
pass "sudo: user without sudo denied without a password prompt; sudo tasks audited with the invoking user"

python3 - <<"PY"
import fcntl, os
from nexus_core import agent_client as a
fd = os.open("/var/lib/dpkg/lock-frontend", os.O_RDWR | os.O_CREAT)
fcntl.lockf(fd, fcntl.LOCK_EX)
try:
    a.call("apt.install", {"packages": ["hello"]})
    raise SystemExit("lock not detected")
except a.AgentError as e:
    assert e.code == "locked", e.code
finally:
    fcntl.lockf(fd, fcntl.LOCK_UN)
PY
pass "agent: dpkg lock held by another process is reported (code=locked)"

python3 - <<"PY"
from nexus_core import agent_client as a, packages
plan = packages.plan("install", ["hello"])
assert [c.name for c in plan.changes] == ["hello"], plan
events = []
result = a.call("apt.install", {"packages": ["hello"], "expected": [f"{c.action}:{c.name}" for c in plan.changes]},
                on_event=events.append)
assert result["ok"], result
phases = {e.get("phase") for e in events if e.get("type") == "progress"}
assert "install" in phases, phases
print("progress phases:", sorted(p for p in phases if p))
PY
dpkg -s hello >/dev/null && pass "agent: apt install with confirmed plan, streamed progress, package installed"
python3 - <<"PY"
from nexus_core import agent_client as a
try:
    a.call("apt.remove", {"packages": ["hello"], "expected": ["remove:something-else"]})
    raise SystemExit("plan mismatch accepted")
except a.AgentError as e:
    assert e.code == "invalid", e.code
PY
dpkg -s hello >/dev/null && pass "agent: refuses to run when the confirmed plan differs from the current plan"
python3 - <<"PY"
from nexus_core import agent_client as a
assert a.call("apt.remove", {"packages": ["hello"], "expected": ["remove:hello"]})["ok"]
PY
dpkg -s hello >/dev/null 2>&1 && fail "hello still installed" || pass "agent: apt remove"
grep -q "\"op\": \"apt.install\"" /var/log/nexusos/agent-audit.log && grep -q "\"outcome\": \"denied\"" /var/log/nexusos/agent-audit.log \
    && pass "agent: audit log records allowed and denied operations"

# ------------------------------------------------------------------ gateway with real NGINX
mkdir -p /srv/backend && echo "nexus backend ok" > /srv/backend/index.html
( cd /srv/backend && python3 -m http.server 8099 --bind 127.0.0.1 >/dev/null 2>&1 & )
sleep 1
python3 - <<"PY"
from nexus_core import agent_client as a
a.call("gateway.cert.issue", {"mode": "internal-ca", "name": "test-nexus-lan", "hostnames": ["test.nexus.lan"]})
route = {"id": "test", "hostname": "test.nexus.lan", "backend_host": "127.0.0.1", "backend_port": 8099,
         "tls": "internal-ca", "certificate": "test-nexus-lan", "access": "lan", "approved": True}
a.call("gateway.route.save", {"route": route})
r = a.call("gateway.apply")
assert r["ok"], r
PY
pass "gateway: internal CA certificate issued, route saved, nginx -t passed, reloaded"
[ "$(stat -c %a /etc/nexusos/gateway/certificates/test-nexus-lan/privkey.pem)" = 600 ] && pass "gateway: private key mode 0600"
body=$(curl -s --noproxy "*" --retry 5 --retry-connrefused --retry-delay 1 --cacert /etc/nexusos/gateway/ca/ca.crt --resolve test.nexus.lan:443:127.0.0.1 https://test.nexus.lan/)
[ "$body" = "nexus backend ok" ] && pass "gateway: HTTPS routing to backend with internal-CA trust" || fail "https body: $body"
sleep 3  # nginx reload is asynchronous: let old workers drain before testing port 80
code=$(curl -s --noproxy "*" --retry 5 --retry-connrefused --retry-delay 1 -o /dev/null -w "%{http_code} %{redirect_url}" --resolve test.nexus.lan:80:127.0.0.1 http://test.nexus.lan/x)
if [ "$code" != "301 https://test.nexus.lan/x" ]; then
    curl -sv --noproxy "*" --resolve test.nexus.lan:80:127.0.0.1 http://test.nexus.lan/x 2>&1 | grep -E "^[<>] " | head
    cat /etc/nexusos/gateway/generated/test.conf; cat /etc/nexusos/gateway/routes/test.yaml
    fail "redirect: $code"
fi
pass "gateway: HTTP -> HTTPS redirect"
python3 - <<"PY"
from nexus_core import agent_client as a
try:
    a.call("gateway.route.save", {"route": {"id": "meta", "hostname": "x.nexus.lan", "backend_host": "169.254.169.254", "backend_port": 80}})
    raise SystemExit("ssrf accepted")
except a.AgentError as e:
    assert "forbidden" in str(e), e
try:
    a.call("gateway.route.save", {"route": {"id": "inj", "hostname": "a.lan; include /etc/shadow", "backend_port": 80}})
    raise SystemExit("injection accepted")
except a.AgentError as e:
    assert e.code == "invalid"
PY
pass "gateway: SSRF (metadata address) and directive injection refused"
# Break it: a route whose certificate files exist but are garbage -> nginx -t fails -> rollback.
install -d /etc/nexusos/gateway/certificates/broken
echo garbage > /etc/nexusos/gateway/certificates/broken/fullchain.pem
echo garbage > /etc/nexusos/gateway/certificates/broken/privkey.pem
python3 - <<"PY"
from nexus_core import agent_client as a
a.call("gateway.route.save", {"route": {"id": "broken", "hostname": "broken.nexus.lan", "backend_port": 8099,
       "tls": "imported", "certificate": "broken", "approved": True}})
r = a.call("gateway.apply")
assert r["ok"] is False and r["rolled_back"], r
print("nginx said:", r["nginx_output"].splitlines()[-1][:120])
PY
[ ! -e /etc/nexusos/gateway/generated/broken.conf ] && pass "gateway: failing nginx -t -> previous configuration restored, not reloaded"
body=$(curl -s --noproxy "*" --retry 5 --retry-connrefused --retry-delay 1 --cacert /etc/nexusos/gateway/ca/ca.crt --resolve test.nexus.lan:443:127.0.0.1 https://test.nexus.lan/)
[ "$body" = "nexus backend ok" ] && pass "gateway: existing route keeps serving after the failed activation"
nexus gateway routes list >/dev/null && nexus gateway ssl list | grep -q test-nexus-lan && pass "CLI: gateway routes list / ssl list"
python3 - <<"PY"
from pathlib import Path
from nexus_core.gateway import certs
try:
    certs.letsencrypt_command(Path("/etc/nexusos/gateway"), "nas.local", "a@b.c")
    raise SystemExit(1)
except Exception as e:
    assert "not a public DNS name" in str(e)
PY
pass "gateway: Lets Encrypt refused for .local names"

# ------------------------------------------------------------------ CLI as a normal user
su alice -c "nexus packages search nginx --limit 3" | grep -q nginx && pass "CLI: packages search"
su alice -c "nexus apps list" | grep -q "Private Cloud" && pass "CLI: apps list (registry installed in /usr/share/nexusos/applications)" || fail "apps registry"
su alice -c "nexus profiles list" | grep -q "Private Cloud Host" && pass "CLI: profiles list"
su alice -c "nexus ssh add homelab admin@192.168.1.10:2222 --group Homelab --tag nas" >/dev/null && su alice -c "nexus ssh list" | grep -q homelab && pass "CLI: ssh add / list"
out=$(su alice -c "printf dummy-not-a-secret | nexus ssh credentials set test-ref 2>&1" || true)
echo "$out" | grep -qiE "secret service|wallet|secretstorage" && pass "CLI: credential save refused without a Secret Service (no plaintext fallback)" || fail "credential: $out"
out=$(su alice -c "nexus system services list 2>&1" || true)
echo "$out" | grep -qi "cannot query systemd" && pass "CLI: system services reports missing systemd clearly (container)"

# ------------------------------------------------------------------ Command Center headless
apt-get install -y -qq libegl1 libgl1 fonts-inter >/dev/null 2>&1 || true
su alice -c "QT_QPA_PLATFORM=offscreen XDG_RUNTIME_DIR=/tmp/alice-run nexus-center --benchmark 10" >/report/benchmark-container.json 2>/tmp/cc.err || { tail -20 /tmp/cc.err; fail "nexus-center failed"; }
python3 - <<"PY"
import json
r = json.load(open("/report/benchmark-container.json"))
assert len(r["modules"]) == 14, r["modules"]
assert not r["qml_warnings"], r["qml_warnings"]
print("startup %s ms, idle RSS %s MiB, idle CPU %s %%, threads %s" % (r["startup_to_window_ms"], r["idle_rss_mib"], r["idle_cpu_percent"], r["threads"]))
PY
pass "Command Center: starts headless on 26.04 PySide6, 14 modules load, no QML warnings (Docker/Ollama absent)"

# ------------------------------------------------------------------ desktop metapackage
apt-get install -y -qq --simulate /debs/*.deb >/tmp/sim.log 2>&1 || { tail -20 /tmp/sim.log; fail "full set dependency resolution"; }
pass "all NexusOS 0.2 packages incl. nexusos-desktop resolve ($(grep -c "^Inst " /tmp/sim.log) packages would be installed)"
echo "ALL INTEGRATION TESTS PASSED"
'
