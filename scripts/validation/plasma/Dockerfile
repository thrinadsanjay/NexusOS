# Disposable Plasma 6 verification image for NexusOS (used by plasma-session-container.sh).
# systemd runs as PID 1 on a private cgroup v2 hierarchy; a headless KWin Wayland session
# (virtual backend, software rendering) hosts Plasma, Konsole and the Command Center.
FROM ubuntu:26.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -qq \
 && apt-get install -y -qq --no-install-recommends systemd systemd-sysv dbus dbus-user-session polkitd pkexec sudo sudo-rs sysstat pciutils \
      kde-plasma-desktop plasma-session-wayland kwin-wayland konsole dolphin kate kde-spectacle kwalletmanager \
      kde-cli-tools plasma-systemmonitor systemsettings libkf6kcmutils-bin xwayland python3-secretstorage python3-dbus \
      python3-paramiko udisks2 network-manager nginx openssl curl fonts-inter fonts-jetbrains-mono \
      mesa-libgallium libgl1-mesa-dri libegl-mesa0 >/dev/null \
 && apt-get clean
# Disposable test accounts (container only, never real credentials):
#   nexus  administrator, sudo asks for a password      ops  administrator, sudo NOPASSWD
#   guest  standard user, no sudo
RUN useradd -m -s /bin/bash -G sudo nexus && echo 'nexus:nexus-test-only' | chpasswd \
 && useradd -m -s /bin/bash ops && echo 'ops ALL=(ALL:ALL) NOPASSWD: ALL' > /etc/sudoers.d/90-nexusos-test-ops \
 && chmod 0440 /etc/sudoers.d/90-nexusos-test-ops && useradd -m -s /bin/bash guest \
 && sed -i '/\[::\]/d' /etc/nginx/sites-enabled/default   # containers here have no IPv6
COPY debs /opt/nexusos-debs
RUN apt-get update -qq && apt-get install -y -qq /opt/nexusos-debs/*.deb >/dev/null && apt-get clean
COPY entry.sh session.sh env.sh session-checks.sh sudo-checks.sh sudo-driver.py /opt/nexusos-plasma/
CMD ["/opt/nexusos-plasma/entry.sh"]
