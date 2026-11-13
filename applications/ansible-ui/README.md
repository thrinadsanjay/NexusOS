# Ansible UI (planned)

Status: **unavailable** — there is no Ansible UI implementation to deploy yet.

`thrinadsanjay/Ansible-UI_Data` holds Ansible *content* (OCI provisioning playbooks,
roles, inventories, vaults). When an Ansible UI project exists, its registry entry
must declare:

* a restricted execution identity (a dedicated non-login user or container user;
  never root, never the desktop user),
* credentials in its own vault (no secrets in NexusOS),
* the content repository as a project source,
* RBAC and job logs inside the application.
