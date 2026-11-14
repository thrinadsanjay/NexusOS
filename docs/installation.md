# Installing and testing NexusOS safely

NexusOS is in **development**. There is no installable NexusOS ISO yet. Test
only in virtual machines or containers. Do not install development builds on
machines that hold data you care about, and do not write development images to
physical disks.

## Option A — NexusOS packages in a container (fastest)

```bash
scripts/package/build-in-container.sh
scripts/validation/test-packages-container.sh   # installs, verifies, removes in ubuntu:26.04
```

## Option A2 — a Plasma 6 Wayland session in a container

```bash
scripts/validation/plasma-session-container.sh --screenshots build/plasma-shots
```

Boots systemd in a disposable **privileged** container (nothing is installed on the host,
no host device is used), starts KWin Wayland with a virtual output and plasmashell as a
test user, and checks the agent and polkit decisions, the theme and panel layout, the
Command Center on Wayland (all modules, memory budgets), KCMs and Konsole. It cannot show
interactive polkit prompts (UDisks2, NetworkManager) or use a GPU, so the VM checklist below is still required.

## Option B — NexusOS packages in an Ubuntu/Kubuntu 26.04 VM

1. Create a VM (QEMU/KVM, virt-manager, GNOME Boxes) from the Kubuntu 26.04 ISO,
   ≥ 4 GB RAM, UEFI firmware (OVMF). Take a snapshot after installation.
2. Copy `build/debs/*.deb` into the VM and verify checksums:
   `sha256sum --check SHA256SUMS`.
3. Install:
   ```bash
   sudo apt install ./nexusos-branding_*.deb ./nexusos-defaults_*.deb ./nexus-cli_*.deb \
                    ./nexusos-theme_*.deb ./nexusos-desktop_*.deb
   ```
4. Log out and back in (Wayland session). New users get the Nexus layout;
   existing users can apply it in *System Settings → Colours & Themes → Global Theme → Nexus*
   (tick "Use desktop layout from theme" to replace panels).
5. Roll back with `sudo apt remove nexusos-desktop nexusos-theme nexusos-branding nexusos-defaults nexus-cli`
   or revert the VM snapshot.

## Disposable test VM

The Command Center needs a real Plasma session (polkit prompts, KDE Wallet, Konsole,
Dolphin, NetworkManager, UDisks2). Use a throwaway VM — never your workstation or a
production Proxmox host.

```bash
# on a Linux host with KVM (sudo apt install qemu-system-x86 qemu-utils ovmf cloud-image-utils)
scripts/development/build-packages.sh                     # build/debs/*.deb (+ SHA256SUMS)
scripts/development/vm/create-test-vm.sh --memory 8192 --cpus 4 --disk 60G
#   downloads + verifies the Ubuntu 26.04 cloud image, creates a qcow2 overlay FILE,
#   cloud-init installs kubuntu-desktop, docker.io, nginx, openssh-server; SSH on localhost:2222
scripts/development/vm/install-packages.sh build/debs     # scp + apt install inside the VM
```

In the VM window: log in to **Plasma (Wayland)** as `nexus` (set a password first with
`ssh -p 2222 nexus@127.0.0.1 sudo passwd nexus`), start **Nexus Command Center**, then:

- [ ] Software Center: search, install `hello` → sudo password box → progress → history; remove; cancel during download
- [ ] System Settings: open Display/Users KCMs; change time zone (polkit); start/stop `nginx.service`
- [ ] Terminal & SSH: new local terminal (Konsole tab, split panes); add a profile; save a password in KDE Wallet; verify host key; connect; SFTP upload/download
- [ ] Containers: list/start/stop/logs/inspect; pull an image; deploy a compose file (user in `docker` group *in the VM only*)
- [ ] Nexus Applications: install Open WebUI; health; logs; backup; propose route
- [ ] Gateway: install `nexusos-gateway`; issue internal CA cert; approve + apply route; open `https://<host>` with the CA trusted; break a cert and confirm rollback
- [ ] Storage: inventory, SMART (agent), mount/unmount a **virtual** USB disk (`-drive file=extra.qcow2,if=virtio`); format it via the guarded flow
- [ ] Network: connectivity, diagnostics, static IPv4 with checkpoint (do not confirm → rollback)
- [ ] Local AI: install Ollama on request, pull a small model, chat with streaming and stop
- [ ] `scripts/benchmarks/command-center.sh --installed --runs 5` → record results in docs/performance.md

Destroy the VM afterwards (`rm -rf ~/nexusos-vm`).

## Option C — prototype ISO in a VM

Build it with Cubic following [`iso/prototype/README.md`](../iso/prototype/README.md),
then boot it in QEMU with OVMF. Only install onto a virtual disk.

## VM test checklist

- [ ] Boots in UEFI mode (and Secure Boot with OVMF `secboot` firmware)
- [ ] `cat /etc/os-release` shows `NexusOS Engineering Edition 1.0`; `uname -r` is an Ubuntu kernel
- [ ] `apt update && apt policy` works; `add-apt-repository` still works
- [ ] SDDM appears on Wayland; Plasma session starts
- [ ] `echo $XDG_CONFIG_DIRS` starts with `/usr/share/nexusos/xdg`
- [ ] Top panel: launcher with N icon, CPU/memory/network monitors, clock, tray
- [ ] Bottom dock: Dolphin, browser, Konsole, Kate, Nexus Dev, Nexus Infra, System Monitor, Nexus AI, Command Center, Settings
- [ ] Konsole opens with the Nexus profile (JetBrains Mono, Nexus palette); banner shows once
- [ ] `nexus system health`, `nexus infra status`, `nexus ai status` behave as documented
- [ ] Removing the packages restores Ubuntu identity and Breeze defaults

## Optional post-install components

Not part of any image; install deliberately and review vendor scripts first.

* **Docker Engine**: `sudo apt install docker.io docker-buildx docker-compose-v2`.
  Prefer `sudo docker …` or rootless Docker; the `docker` group is root-equivalent.
* **Virtualisation**: packages in `manifests/infrastructure.yaml`; add yourself to
  `libvirt` (and `kvm`) to manage system VMs.
* **Ollama (CPU)**: follow https://ollama.com/download/linux. Keep it bound to
  `127.0.0.1:11434`. Pull models explicitly, e.g. `ollama pull llama3.2:3b`, then
  `nexus ai models`.
* **Open WebUI**: run as a container bound to localhost, e.g.
  `docker run -d -p 127.0.0.1:3000:8080 --add-host=host.docker.internal:host-gateway -v open-webui:/app/backend/data --name open-webui ghcr.io/open-webui/open-webui:main`
  and create the admin account immediately.
