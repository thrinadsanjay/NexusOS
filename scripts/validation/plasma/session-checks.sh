#!/bin/bash
# shellcheck disable=SC2015  # pass/fail never fail themselves, so "A && pass || fail" is safe
# Checks that run as the desktop user inside the Plasma session (see plasma-session-container.sh).
set -u
# shellcheck source=scripts/validation/plasma/env.sh disable=SC1091
. /opt/nexusos-plasma/env.sh
fails=0
pass() { printf "PASS  %s\n" "$*"; }
fail() { printf "FAIL  %s\n" "$*"; fails=$((fails + 1)); }
expect() { [ "$2" = "$3" ] && pass "$1: $2" || fail "$1: got '$2', expected '$3'"; }
SHOTS=${1:-}

# ---- theme and defaults (read through XDG_CONFIG_DIRS like Plasma does) -----------------
case "$XDG_CONFIG_DIRS" in /usr/share/nexusos/xdg:*) pass "XDG_CONFIG_DIRS starts with NexusOS defaults";; *) fail "XDG_CONFIG_DIRS=$XDG_CONFIG_DIRS";; esac
expect "global theme" "$(kreadconfig6 --file kdeglobals --group KDE --key LookAndFeelPackage)" org.nexusos.nexus.desktop
expect "colour scheme" "$(kreadconfig6 --file kdeglobals --group General --key ColorScheme)" Nexus
expect "icon theme" "$(kreadconfig6 --file kdeglobals --group Icons --key Theme)" Nexus
case "$(kreadconfig6 --file kdeglobals --group General --key font)" in Inter,*) pass "UI font Inter";; *) fail "UI font";; esac
expect "Konsole profile" "$(kreadconfig6 --file konsolerc --group 'Desktop Entry' --key DefaultProfile)" Nexus.profile

# ---- layout applied by plasmashell -------------------------------------------------------
layout=$(qdbus6 org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript '
var out = [];
panels().forEach(function(p){ out.push("PANEL " + p.location + " " + p.widgets().map(function(w){return w.type}).join(",")); });
desktops().forEach(function(d){ d.currentConfigGroup=["Wallpaper","org.kde.image","General"]; out.push("WALLPAPER " + d.readConfig("Image")); });
panels().forEach(function(p){ p.widgets("org.kde.plasma.icontasks").forEach(function(w){ w.currentConfigGroup=["General"]; out.push("LAUNCHERS " + w.readConfig("launchers")); }); });
print(out.join("\n"));')
while IFS= read -r line; do printf '      %s\n' "$line"; done <<<"$layout"
echo "$layout" | grep -q "^PANEL top .*org.kde.plasma.kickoff.*org.kde.plasma.digitalclock.*org.kde.plasma.systemtray" && pass "top panel: launcher, clock, tray" || fail "top panel"
echo "$layout" | grep -q "^PANEL top .*org.kde.plasma.systemmonitor" && pass "top panel: system monitors" || fail "top panel monitors"
echo "$layout" | grep -q "^PANEL bottom .*org.kde.plasma.icontasks" && pass "bottom dock with icon tasks" || fail "bottom dock"
echo "$layout" | grep -q "^WALLPAPER .*/usr/share/wallpapers/NexusOS" && pass "NexusOS wallpaper" || fail "wallpaper"
for l in org.kde.dolphin.desktop org.kde.konsole.desktop org.nexusos.dev.desktop org.nexusos.CommandCenter.desktop systemsettings.desktop; do
    echo "$layout" | grep "^LAUNCHERS" | grep -q "$l" && pass "dock launcher $l" || fail "dock launcher $l missing"
done

# ---- Command Center on KWin Wayland --------------------------------------------------------
cd /tmp || exit 1
smoke_args=(--smoke); [ -n "$SHOTS" ] && smoke_args+=(--screenshots "$SHOTS")
if out=$(timeout 300 nexus-center "${smoke_args[@]}" 2>/dev/null); then
    rss=$(echo "$out" | python3 -c 'import json,sys; print(json.load(sys.stdin)["idle_rss_mib"])')
    pass "Command Center: all modules load on Wayland without QML warnings (RSS after all modules ${rss} MiB)"
    python3 -c "import sys; sys.exit(0 if $rss <= 250 else 1)" && pass "RSS after all modules ≤ 250 MiB budget" || fail "RSS $rss MiB > 250 MiB"
else
    fail "Command Center smoke test"; echo "$out" | tail -20
fi
if out=$(timeout 120 nexus-center --benchmark 8 --no-visit 2>/dev/null); then
    read -r rss start < <(echo "$out" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["idle_rss_mib"], d["startup_to_window_ms"])')
    python3 -c "import sys; sys.exit(0 if $rss <= 180 else 1)" && pass "plain launch: ${start} ms to window, idle RSS ${rss} MiB (≤ 180)" || fail "plain launch RSS $rss MiB > 180"
else
    fail "Command Center benchmark"
fi

# ---- desktop integration through nexus_core -----------------------------------------------------
if ! python3 - <<'PY'
import subprocess, sys, time
from nexus_core import services, settings, terminal
fails = 0
def report(ok, msg):
    global fails
    print(("PASS  " if ok else "FAIL  ") + msg); fails += 0 if ok else 1
listed = {l.split()[0] for l in subprocess.run(["kcmshell6", "--list"], capture_output=True, text=True).stdout.splitlines()[1:] if l.strip()}
cat = settings.catalog()
wrong = [e.kcm for e in cat if e.kcm and e.available and e.kcm not in listed]
missing = [e.kcm for e in cat if e.kcm and not e.available]
report(not wrong, f"settings catalogue matches kcmshell6 --list ({sum(1 for e in cat if e.kcm and e.available)} available, not installed: {', '.join(missing) or 'none'})")
report(all(e.package for e in cat if e.kcm and not e.available), "every missing KCM names the package that provides it")
settings.open_kcm("kcm_colors")
terminal.open_terminal(terminal.TerminalTab(title="Nexus check", workdir="~", shell="bash"))
time.sleep(5)
ps = subprocess.run(["ps", "-u", str(__import__("os").getuid()), "-o", "args"], capture_output=True, text=True).stdout
report("kcmshell6 kcm_colors" in ps, "System Settings module opens (kcmshell6 kcm_colors)")
report(any(l.startswith("konsole") and "--profile Nexus" in l for l in ps.splitlines()), "terminal opens as a Konsole tab with the Nexus profile")
state = services.is_active("nexusos-agent.socket")
report(state == "active", f"service state parsing on systemd: nexusos-agent.socket is {state}")
try:
    services.control("nginx.service", "restart")
    report(False, "systemctl restart allowed without authentication")
except Exception as exc:
    report("denied" in str(exc).lower() or "authentication" in str(getattr(exc, "hint", "") or "").lower(), "service control without a polkit agent is refused")
sys.exit(1 if fails else 0)
PY
then
    fails=$((fails + 1))
fi
exit $fails
