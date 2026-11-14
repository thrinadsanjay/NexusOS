#!/bin/bash
# shellcheck disable=SC2015  # pass/fail never fail themselves
# Administrative access through the user's own sudo rights (run as root inside the test container).
# For sudo-rs and sudo 1.9 (sudo.ws) in turn:
#   ops   (NOPASSWD)          → tasks run, no password asked
#   nexus (sudo + password)   → password box: wrong password retried, right one accepted, then cached
#   guest (no sudo)           → access denied, never asked for a password
# plus a real service restart and a real package install through nexus-admin, and the audit log.
set -u
fails=0
pass() { printf "PASS  %s\n" "$*"; }
fail() { printf "FAIL  %s\n" "$*"; fails=$((fails + 1)); }

as_user() {  # as_user USER PASSWORD-ANSWERS PYTHON-SNIPPET → JSON
    local snippet
    snippet=$(mktemp /tmp/nx-check-XXXXXX.py)
    printf '%s\n' "$3" > "$snippet"
    chmod 644 "$snippet"
    su "$1" -c "cd /tmp && NX_ANSWERS='$2' python3 /opt/nexusos-plasma/sudo-driver.py $snippet" 2>&1 | grep '^RESULT ' | cut -c8-
    rm -f "$snippet"
}

field() { python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(eval(sys.argv[2], {}, d))" "$1" "$2" 2>/dev/null; }

for impl in /usr/lib/cargo/bin/sudo /usr/bin/sudo.ws; do
    [ -x "$impl" ] || continue
    update-alternatives --set sudo "$impl" >/dev/null
    name=$(sudo --version 2>&1 | head -1)
    echo "== $name"
    for u in ops nexus guest; do sudo -K -u "$u" 2>/dev/null || true; done

    r=$(as_user ops "" 'out(data=agent_client.call("agent.ping"))')
    [ "$(field "$r" 'len(asked) == 0 and "data" in locals() and auth == "not-required"')" = True ] \
        && pass "NOPASSWD sudo: task runs without a password box" || fail "NOPASSWD sudo: $r"

    r=$(as_user nexus "wrong-password,nexus-test-only" '
agent_client.call("agent.ping", label="Ping")
agent_client.call("agent.ping", label="Ping again")
out(ok=True)')
    [ "$(field "$r" 'ok and len(asked) == 2 and asked[1]["error"] == "Incorrect password, try again" and auth == "required"')" = True ] \
        && pass "password sudo: box shown, wrong password retried, then accepted; second task reused sudo's cache" \
        || fail "password sudo: $r"

    r=$(as_user nexus "" '
try:
    agent_client.call("agent.ping")
    out(ok=True)
except privilege.AuthCancelledError as e:
    out(cancelled=str(e))')
    [ "$(field "$r" '"cancelled" in locals() and len(asked) == 1')" = True ] \
        && pass "password sudo: cancelling the box cancels the task" || fail "cancel: $r"

    r=$(as_user guest "anything" '
try:
    agent_client.call("agent.ping")
    out(ok=True)
except privilege.AccessDeniedError as e:
    out(denied=str(e), hint=e.hint)')
    [ "$(field "$r" '"denied" in locals() and len(asked) == 0 and admin == "none"')" = True ] \
        && pass "no sudo: access denied without a password prompt ($(field "$r" 'denied'))" || fail "no sudo: $r"
done
update-alternatives --auto sudo >/dev/null

# Real administrative tasks through nexus-admin.
before=$(systemctl show nginx.service --property=ExecMainStartTimestampMonotonic --value)
r=$(as_user nexus "nexus-test-only" 'out(data=agent_client.call("service.control", {"unit": "nginx.service", "action": "restart"}, label="Restart nginx"))')
after=$(systemctl show nginx.service --property=ExecMainStartTimestampMonotonic --value)
[ "$before" != "$after" ] && [ "$(systemctl is-active nginx.service)" = active ] \
    && pass "nexus restarted nginx.service through sudo (password)" || fail "service restart: $r"

r=$(as_user ops "" '
try:
    agent_client.call("service.control", {"unit": "systemd-journald.service", "action": "stop"})
    out(ok=True)
except Exception as e:
    out(refused=str(e))')
[ "$(field "$r" '"refused" in locals()')" = True ] && pass "units outside the approved list are refused even for NOPASSWD admins" || fail "unit allow-list: $r"

apt-get remove -y -qq hello >/dev/null 2>&1 || true
r=$(as_user ops "" 'out(data=agent_client.call("apt.install", {"packages": ["hello"], "expected": ["install:hello"]}, label="Install hello"))')
dpkg -s hello >/dev/null 2>&1 && pass "ops installed 'hello' through sudo nexus-admin (real APT)" || fail "apt install: $r"

if grep -q '"via": "sudo"' /var/log/nexusos/agent-audit.log 2>/dev/null \
   && grep '"via": "sudo"' /var/log/nexusos/agent-audit.log | grep -q '"user": "nexus"' \
   && grep '"via": "sudo"' /var/log/nexusos/agent-audit.log | grep -q '"user": "ops"'; then
    pass "audit log records the invoking user for sudo tasks"
else
    fail "audit log"
fi
journalctl -q --no-pager -t sudo 2>/dev/null | grep -q "nexus-admin" && pass "sudo logged the nexus-admin runs (journal)" || echo "INFO  sudo journal entries not found (syslog configuration)"
grep -rq "nexus-test-only" /var/log/nexusos/ 2>/dev/null && fail "password found in NexusOS logs" || pass "password never written to NexusOS logs"
exit $fails
