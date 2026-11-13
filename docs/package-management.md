# Package management (Software Center)

NexusOS uses Ubuntu's APT and dpkg unchanged. The Software Center and `nexus packages`
are front-ends over one backend (`nexus_core.packages`); the terminal (`apt`, `apt-get`,
`dpkg`) keeps working exactly as on Ubuntu and shares the same history.

## Flow

1. **Query (unprivileged)** — catalogue built from `/var/lib/apt/lists/*_Packages*`
   (compressed indexes are read through `apt-helper cat-file`) and cached per index state;
   details via `apt-cache show/policy`; installed state via `dpkg-query`.
2. **Plan (unprivileged)** — `apt-get --simulate` produces the exact list of installs,
   upgrades, removals and purges. Plans that remove anything, or remove packages that were
   not requested, are flagged destructive and listed in the confirmation dialog together
   with the exact command.
3. **Confirm** — the user sees the plan; removal, purge, repository changes and every
   destructive plan require explicit confirmation (also with `--yes` in the CLI).
4. **Execute (privileged agent)** — the UI sends `apt.<op>` with the package names and the
   confirmed change list. The agent re-validates names, checks the dpkg lock, re-simulates
   and **refuses if the plan changed**, then runs
   `apt-get -y -o DPkg::Lock::Timeout=0 -o APT::Status-Fd=N <op> -- <names>` with
   `--force-confdef --force-confold` and `DEBIAN_FRONTEND=noninteractive`.
5. **Progress** — download and dpkg progress stream from the status fd; output lines are
   secret-redacted. **Cancel** is honoured while downloading (SIGINT, nothing changed);
   once dpkg is modifying the system, cancel is refused until it finishes.

## Status

| Feature | Status |
|---------|--------|
| Browse by section, search, details, dependencies, reverse dependencies | Implemented |
| Install / remove / purge / upgrade / full-upgrade / update indexes via agent | **Tested** on 26.04 (install/remove of `hello`) |
| Installed packages and installed applications (packages with launchers) | Implemented |
| Available updates (simulation) | Implemented |
| History from `/var/log/apt/history.log*` | Implemented |
| Repository listing (deb822 and one-line) | Implemented |
| Add/remove NexusOS-managed repositories (https, `Signed-By` keyring required) | Implemented; add tested by unit tests |
| Lock detection (`/proc/locks`) and agent lock refusal | **Tested** |
| polkit authorization (`org.nexusos.agent.packages.manage`, `auth_admin_keep`) | Fail-closed **tested**; interactive prompt needs a Plasma session (VM) |
| Snap / Flatpak management | Unsupported (Discover remains available) |
| Firmware updates (fwupd) | Unsupported in the Command Center (Discover / `fwupdmgr`) |

## Discover and other graphical tools

Ubuntu Software is not part of Kubuntu/NexusOS. **Plasma Discover is not removed in 0.2**:
the Software Center does not yet manage Flatpaks or firmware, and its polkit flow has not
been verified in a real Plasma session. Removal will be reconsidered once both are tested
in the VM (spec §8.4). `packagekit` stays because Plasma components depend on it.

## CLI

```bash
nexus packages search nginx
nexus packages show nginx
nexus packages install nginx --dry-run      # plan only
nexus packages install nginx                # plan, confirm, agent (or sudo fallback)
nexus packages remove vim [--purge]
nexus packages update [--upgrade]
nexus packages list [--apps|--upgradable]
nexus packages history
nexus packages repo list|add|remove
```
