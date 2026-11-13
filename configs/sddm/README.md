# SDDM (login screen)

Status: **placeholder**.

Shipped now (`nexusos-desktop`):
* `/etc/sddm.conf.d/50-nexusos.conf` — selects the upstream `breeze` greeter and
  a Wayland greeter (`DisplayServer=wayland`, supported by SDDM ≥ 0.20).

Not done yet:
1. A `nexus` SDDM QML theme (`/usr/share/sddm/themes/nexus/`) — background from
   `branding/wallpapers/nexusos-default.svg`, horizontal logo, glass login card,
   Inter typography. Must use only SDDM's documented QML API (`sddm`, `userModel`,
   `sessionModel`, `config`) and Qt 6 (`QtVersion=6` in `metadata.desktop`).
2. Packaging it in `nexusos-theme` and switching `Current=nexus`.
3. Testing with `sddm-greeter-qt6 --test-mode --theme <dir>` in a VM.

Why not set the Breeze greeter background now? Breeze reads
`/usr/share/sddm/themes/breeze/theme.conf.user`, a path managed by the SDDM KCM;
writing it from a package would fight the KCM. The custom theme avoids that.
