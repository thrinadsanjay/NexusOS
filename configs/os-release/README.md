# OS identity

| File | Installed to | Notes |
|------|--------------|-------|
| `os-release` | `/usr/lib/os-release` (diverted) | `/etc/os-release` is base-files' symlink to it, so it follows automatically |
| `nexusos-release` | `/usr/lib/nexusos/release` | product/build metadata for tooling |
| `hostname` | `/usr/share/nexusos/defaults/hostname` | **default only** — consumed by the ISO/installer, never written to `/etc/hostname` by a package |

What is deliberately *not* changed:

* `/etc/lsb-release` — stays Ubuntu's, so APT/PPA tooling (`add-apt-repository`, `ubuntu-drivers`) keeps working.
* Kernel identity (`uname`), `/etc/issue`, `/etc/apt/*`, Ubuntu legal files.
* The machine's hostname. `DEFAULT_HOSTNAME=nexusos` in os-release is only used by systemd when no hostname is configured.
