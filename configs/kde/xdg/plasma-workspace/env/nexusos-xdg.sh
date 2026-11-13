# shellcheck shell=sh
# Installed as /etc/xdg/plasma-workspace/env/nexusos-xdg.sh by nexusos-desktop.
# startplasma sources this before launching the session: prepend the NexusOS
# defaults directory so KDE reads NexusOS kdeglobals/konsolerc/etc. as the lowest
# priority system defaults. User configuration in ~/.config always takes precedence.
case ":${XDG_CONFIG_DIRS:-/etc/xdg}:" in
    *:/usr/share/nexusos/xdg:*) ;;
    *) XDG_CONFIG_DIRS="/usr/share/nexusos/xdg:${XDG_CONFIG_DIRS:-/etc/xdg}"; export XDG_CONFIG_DIRS ;;
esac
