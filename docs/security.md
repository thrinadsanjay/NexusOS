# Security

## Principles

1. **Upstream first** — security updates come from the Ubuntu archive
   (`resolute-security`) unchanged; NexusOS does not rebuild Ubuntu packages.
2. **Least privilege** — NexusOS tooling runs unprivileged; privileged steps
   are explicit, previewed and confirmed.
3. **Local by default** — services NexusOS documents bind to `127.0.0.1`.
4. **Reversible** — every system change a NexusOS package makes is undone on removal.

## Privileged operations

| Where | Privileged action | Safeguard |
|-------|-------------------|-----------|
| `nexus system update` | `sudo apt-get update` / `upgrade` | Preview via `apt-get --simulate` first; exact command shown; interactive confirmation; refused without a TTY; APT asks again |
| `nexus system cleanup --apply` | `sudo apt-get clean/autoremove`, `sudo journalctl --vacuum-time=14d` | Per-item confirmation; user caches only inside `$HOME`, symlinks refused |
| `nexusos-branding` maintainer scripts | `dpkg-divert` of `/usr/lib/os-release` | Symmetric preinst/postrm, tested install → reinstall → remove → purge |
| Package builds | none | `Rules-Requires-Root: no`; container builds run as user `builder` |
| `iso/prototype/customize-chroot.sh` | APT inside the image chroot | Refuses to run unless `ischroot` confirms a chroot |

Never run by NexusOS tooling: `mkfs`, `wipefs`, `dd` to devices, `parted`/`fdisk`
writes, installer automation on the host. A test enforces this for all scripts.
`inspect-iso.sh` refuses block devices and never mounts images.

## Secrets management

* No secrets in the repository, packages, manifests or CI (CI uses only the
  default read-only `GITHUB_TOKEN`; workflows declare `permissions: contents: read`).
* `nexus` diagnostics never print environment variables. Child processes receive
  a scrubbed environment (`PATH`, `HOME`, locale, `XDG_RUNTIME_DIR`, `DOCKER_HOST`, `USER` only).
* `nexus cloud status` checks only whether config paths **exist**
  (`~/.aws/config`, `~/.kube/config`, …); it never reads them.
* `OLLAMA_HOST` values containing credentials are rejected so they cannot leak into output.
* Release signing keys stay offline; only signatures are published.

## Service exposure

| Service | Default | Guidance |
|---------|---------|----------|
| Docker Engine | UNIX socket | Do not add users to `docker` casually: it is root-equivalent. Prefer rootless Docker. Never expose `tcp://…:2375`. Publish container ports as `127.0.0.1:host:container`. |
| libvirt | UNIX socket | `libvirt` group membership allows VM management; grant deliberately. |
| Ollama | `127.0.0.1:11434` | Do not set `OLLAMA_HOST=0.0.0.0` on untrusted networks; it has no authentication. |
| Open WebUI | `127.0.0.1:3000` (documented) | Create the admin account immediately; put a TLS reverse proxy with auth in front before any remote access. |
| SSH | client only in base | `openssh-server` is not installed by default. |
| Firewall | `ufw` installed | Enable with `sudo ufw enable` (default deny incoming). |

## Package and supply-chain security

* Only packages from Ubuntu main/universe are in images; names are verified
  against the archive. Third-party software is listed as `external`, opt-in,
  with its official source.
* No AI models or third-party binaries are downloaded during image builds.
* `nexus dev create react` downloads `create-vite` from npm only after showing
  the command and asking for confirmation (or `--yes`).
* GitHub Actions are pinned to full commit SHAs.
* Built artefacts ship with SHA-256/SHA-512 checksums; releases will be signed.
* Future APT repository: dedicated key, `Signed-By:` in deb822 sources, no
  `apt-key`, no unauthenticated repositories.

## Reporting a vulnerability

Report privately via GitHub Security Advisories on this repository ("Report a
vulnerability"). Please do not open public issues for security problems.
