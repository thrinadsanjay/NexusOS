# Nexus Application Platform

Nexus applications are optional, independently developed projects deployed with Docker
Compose. NexusOS never installs them automatically and never copies their source code:
the repository holds only the **registry** (`applications/registry/<id>.yaml`),
deployment definitions (`applications/<id>/`), version pins, configuration schemas,
health checks, gateway metadata and integration contracts.

## Applications (as found in their repositories, 2026-11-13)

| App | Source (pinned) | What the source actually is | Status |
|-----|-----------------|-----------------------------|--------|
| Private Cloud | `thrinadsanjay/ForgeCloud` @ `c7daf85` | "Forge" self-service portal, Node.js + PostgreSQL, port 4100, `/health`; **Proxmox VE provider only** | experimental (build from source) |
| NexusOps | `thrinadsanjay/NexusOps` @ `c6ff361` | IPAM/DNS/DHCP/LDAP/PKI/SMTP platform; FastAPI + Celery + Postgres + Redis + OpenLDAP; GHCR images | experimental |
| Cloud Desktop | `thrinadsanjay/CloudDesk` (Development) @ `9fe2ed4` | guacamole-lite Node gateway + guacd → RDP → host `xrdp :3389` | experimental |
| Open WebUI | `ghcr.io/open-webui/open-webui:v0.13.3` | upstream image | available |
| Ansible UI | — | `thrinadsanjay/Ansible-UI_Data` is Ansible **content** (playbooks/roles/inventories), not a UI | **unavailable** |

Notes taken from the source, not invented:

* **Private Cloud** — KVM/libvirt provider, container lifecycle beyond Proxmox and Cloud
  Desktop integration are not in the ForgeCloud code yet; the registry says so.
* **NexusOps** — upstream compose publishes on `0.0.0.0` and mounts the Docker socket. The
  NexusOS override publishes everything on loopback and **removes the Docker socket mount**
  (NexusOps' "manage compose services" feature is therefore unavailable). Upstream
  default passwords are replaced by generated secrets. Its DHCP service uses host
  networking with `NET_ADMIN` and stays disabled until enabled in NexusOps.
* **Cloud Desktop** — needs `xrdp` on the host. xrdp provides X11 sessions; Plasma 6 on
  NexusOS defaults to Wayland, so an X11 Plasma session is required (not yet validated).
* **Ansible UI** — must use a restricted execution identity when implemented.

## Lifecycle (`nexus_core.apps.lifecycle`, `nexus apps …`, Command Center)

| Step | What happens |
|------|--------------|
| Dependency check | Docker + Compose plugin, git for source builds, required host ports (e.g. 3389), port conflicts, app dependencies |
| Install | copies deployment files to `~/.local/share/nexusos/apps/<id>/`; fetches the pinned commit (`git fetch --depth 1 <sha>`); generates secrets into `.env` (0600); `docker compose config` validation; `up -d [--build]`; proposes a pending gateway route |
| Start / stop / restart | `docker compose` on project `nexus-<id>` |
| Update | re-copies definitions, re-fetches if the pin changed, keeps existing secrets, pull/rebuild, `up -d` |
| Status / health | compose services + HTTP health check on loopback |
| Logs | `docker compose logs` (secrets redacted) |
| Backup / restore | config archive + named volumes via a `busybox:1.37` helper container; archive 0600; restore requires confirmation |
| Uninstall | `down` (data kept) or `down --volumes` + delete (`--delete-data`) |

Registry rules (schema + `scripts/validation/validate_apps.py`): full 40-char commit SHA
for source repos, loopback-only ports and health URLs, reasons for planned/unavailable
apps, no Docker socket mounts, no `0.0.0.0` publishing.

## Integration contract

Each registry entry declares `contract`: API and health endpoints, authentication
(`none`, `local`, `oidc`, `keycloak-optional`), navigation entries, UI integration mode
(`window` = open in the browser; `webview` = embedded, only for apps that support it),
permissions and capabilities. The Command Center owns navigation, status and lifecycle;
each application owns its business logic and data. All current apps use `window`;
QtWebEngine is not loaded. Keycloak is optional and not required by the core OS.

## Status

| Feature | Status |
|---------|--------|
| Registry schema + validation | Implemented, tested |
| Lifecycle (install/start/stop/restart/update/uninstall/status/logs) | Implemented; tested with mocked Compose |
| Backup / restore | Implemented; backup tested (config); volume export needs Docker |
| Gateway route proposal | Implemented, tested |
| Real deployment of each app | **Not yet executed** (Docker Hub/GHCR pulls and source builds in the VM) |
| Embedded web UIs | Planned |
| Native service / KVM deployment adapters | Planned |
| Keycloak SSO | Planned (per app) |
