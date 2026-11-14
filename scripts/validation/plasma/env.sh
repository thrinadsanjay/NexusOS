# shellcheck shell=bash
# Client environment for the session started by session.sh (source it).
U=$(id -u)
export LANG=C.UTF-8 XDG_RUNTIME_DIR=/run/user/$U DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$U/bus
export XDG_CONFIG_DIRS=/usr/share/nexusos/xdg:/etc/xdg WAYLAND_DISPLAY=wayland-nexus QT_QPA_PLATFORM=wayland
export QT_QUICK_BACKEND=software XDG_CURRENT_DESKTOP=KDE KDE_FULL_SESSION=true XDG_SESSION_TYPE=wayland
