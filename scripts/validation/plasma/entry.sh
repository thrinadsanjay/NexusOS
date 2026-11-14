#!/bin/sh
# Disposable test container only: give systemd a unified cgroup hierarchy, then boot.
umount /sys/fs/cgroup 2>/dev/null || true
mount -t cgroup2 cgroup2 /sys/fs/cgroup
exec /sbin/init
