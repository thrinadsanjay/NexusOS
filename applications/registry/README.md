# Nexus application registry

One YAML file per application (`<id>.yaml`), validated by
`nexus_core.apps.registry.AppDefinition` (`scripts/validation/validate_apps.py`).
Deployment files live in `applications/<id>/`.

Rules enforced by the schema:

* `source_ref` pins a full commit SHA; source code stays in the application's own repository.
* Published ports bind to loopback only; LAN access goes through the NexusOS Gateway.
* Health checks target loopback URLs.
* Secrets are generated at install time into `~/.local/share/nexusos/apps/<id>/.env` (0600).
* `planned` / `unavailable` entries must explain why.

| id | status | source |
|----|--------|--------|
| private-cloud | experimental | ForgeCloud @ c7daf85 (build from source) |
| nexusops | experimental | NexusOps @ c6ff361 (GHCR images) |
| cloud-desktop | experimental | CloudDesk Development @ 9fe2ed4 (build from source) |
| open-webui | available | ghcr.io/open-webui/open-webui:v0.13.3 |
| ansible-ui | unavailable | no UI implementation exists |
