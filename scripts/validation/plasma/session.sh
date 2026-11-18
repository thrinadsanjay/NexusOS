#!/bin/bash
# Start a headless Plasma 6 Wayland session for the current user, the way startplasma does:
# virtual KWin output, then kactivitymanagerd, kded6 and plasmashell. Software rendering only.
set -u
U=$(id -u)
export XDG_RUNTIME_DIR=/run/user/$U DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$U/bus
export XDG_SESSION_TYPE=wayland XDG_CURRENT_DESKTOP=KDE KDE_FULL_SESSION=true XDG_SESSION_DESKTOP=KDE
export QT_QUICK_BACKEND=software LIBGL_ALWAYS_SOFTWARE=1 LANG=C.UTF-8
# shellcheck disable=SC1090
for f in /etc/xdg/plasma-workspace/env/*.sh; do . "$f"; done   # NexusOS sets XDG_CONFIG_DIRS here
# test container only: let spectacle capture the virtual screen without a portal prompt
KWIN_WAYLAND_NO_PERMISSION_CHECKS=1 kwin_wayland --no-lockscreen --virtual --width 1600 --height 1000 --socket wayland-nexus >"/tmp/nx-kwin-$U.log" 2>&1 &
for _ in $(seq 30); do [ -S "$XDG_RUNTIME_DIR/wayland-nexus" ] && break; sleep 0.5; done
export WAYLAND_DISPLAY=wayland-nexus QT_QPA_PLATFORM=wayland
systemctl --user import-environment WAYLAND_DISPLAY QT_QPA_PLATFORM XDG_CONFIG_DIRS XDG_CURRENT_DESKTOP QT_QUICK_BACKEND KDE_FULL_SESSION
for d in /usr/lib/*-linux-gnu/libexec/kactivitymanagerd /usr/libexec/kactivitymanagerd; do
    [ -x "$d" ] && { "$d" >"/tmp/nx-kamd-$U.log" 2>&1 & break; }
done
kded6 >"/tmp/nx-kded-$U.log" 2>&1 &
sleep 3
plasmashell >"/tmp/nx-plasma-$U.log" 2>&1 &
# plasmashell is ready once its scripting interface answers
for _ in $(seq 90); do
    qdbus6 org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript "print(panels().length)" 2>/dev/null | grep -q '[1-9]' && exit 0
    sleep 1
done
echo "plasmashell did not come up" >&2; tail -20 "/tmp/nx-plasma-$U.log" >&2; exit 1
