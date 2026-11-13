# Nexus Gateway (native NGINX)

The gateway publishes Nexus applications (and any local service) through the host's
**native NGINX** — never a container. Package: `nexusos-gateway` (depends on `nginx`,
`openssl`, `nexusos-management-agent`; recommends `certbot`).

## Components

| # | Component | Where |
|---|-----------|-------|
| 1 | Native NGINX | Ubuntu `nginx`; loads `/etc/nginx/conf.d/nexusos-gateway.conf` |
| 2 | Gateway API (read-only, unprivileged) | `nexus_core/gateway/status.py` — status, routes, backend tests |
| 3 | Restricted privileged gateway agent | `nexus_agent/ops.py` — `gateway.*` operations, polkit `org.nexusos.agent.gateway.manage` |
| 4 | Declarative route registry | `/etc/nexusos/gateway/routes/<id>.yaml` (validated by `gateway/model.py`) |
| 5 | Certificate manager | `nexus_core/gateway/certs.py` |
| 6 | Command Center UI | `command-center/modules/gateway/` |
| 7 | CLI | `nexus gateway …` |

```
/etc/nexusos/gateway/
├── routes/<id>.yaml        source definitions (user-approved)
├── generated/<id>.conf     rendered server blocks (never edited by hand)
├── backups/<timestamp>/    previous working generated/ trees (last 10; 0700)
├── certificates/<name>/    fullchain.pem (0644) + privkey.pem (0600)
├── ca/                     internal CA (ca.key 0600)
├── acme/                   Let's Encrypt HTTP-01 webroot
└── state.json              last successful activation
```

## Activation (apply)

1. Load and validate every route; check conflicts (same host+path), backends (SSRF rules)
   and certificate files.
2. Render approved, enabled routes to `generated.staging/`.
3. Back up the current `generated/`, swap staging in.
4. `nginx -t`. **If it fails, the previous tree is restored and NGINX is not reloaded.**
5. Reload NGINX. If the reload fails, restore and reload the previous configuration.
6. Record `state.json`. `nexus gateway rollback` restores the latest backup (again only
   if it passes `nginx -t`).

IPv6 `listen` lines are emitted only when the host has IPv6 (otherwise `nginx -t` fails).
`nginx -s reload` / `systemctl reload nginx` are asynchronous: old workers may answer for
a moment after activation.

## Routes

| Field | Values / rules |
|-------|----------------|
| `hostname` | RFC 1123 name; local (`.lan`, `.local`, `.internal`, `.home.arpa`) or public |
| `path_prefix` | `/[A-Za-z0-9._~/-]*`, no `..` |
| `backend_scheme/host/port` | http/https; host must resolve to loopback or private ranges; link-local, metadata (169.254.169.254, 100.100.100.200), multicast and unspecified are always refused; public backends need `allow_public_backend` |
| `tls` | `none`, `internal-ca`, `self-signed`, `letsencrypt`, `imported` |
| `redirect_http` | 301 to HTTPS when TLS is enabled |
| `websocket` | adds `Upgrade`/`Connection` headers |
| `access` | `lan` (default; RFC 1918, ULA, loopback), `localhost`, `public` |
| `approved` | routes proposed by application installs start unapproved |

Every field is validated before rendering, so no input can inject NGINX directives.

## Certificates

* **Internal CA** — created on first use (`ca.crt`, EC P-256, 10 years); leaf certificates
  397 days with SAN. Trust `ca.crt` on clients.
* **Self-signed** — for tests.
* **Let's Encrypt** — `certbot certonly --webroot`; refused for names that cannot get public
  certificates (`.local`, `.lan`, `.internal`, `.home.arpa`, `.test`, single labels). Renewal
  by certbot's timer, with an NGINX reload deploy hook.
* **Import** — the key must match the certificate; the source files must be readable by
  the requesting user.
* **Inventory/expiry** — ok / warning (< 30 days) / critical (< 7) / expired; the Command
  Center raises de-duplicated notifications; `nexus gateway ssl renew` re-issues internal
  and self-signed certificates due within 30 days.

## Application registration

Installing a Nexus application proposes a route (suggested hostname, `127.0.0.1:<port>`,
`internal-ca`, `lan`, **pending**). The user reviews hostname, TLS and access, approves,
then applies. Application ports are published on 127.0.0.1 only.

## Status

| Feature | Status |
|---------|--------|
| Route validation, SSRF and injection protection | **Tested** (unit + real agent) |
| HTTP, HTTPS, redirect, WebSocket headers, LAN policy | HTTPS + redirect **tested** with real NGINX |
| Apply / nginx -t / backup / rollback on failure | **Tested** (real NGINX, broken certificate) |
| Internal CA, self-signed, import, inventory | **Tested** |
| Let's Encrypt issuance | Implemented; not exercised (needs public DNS) |
| Backend connectivity tests | Implemented |
| Access/error log viewer (agent, administrators) | Implemented |
| Automatic DNS records | Planned (NexusOps integration) |

## CLI

```bash
nexus gateway status
nexus gateway routes list|add|approve|remove|test
nexus gateway apply|rollback
nexus gateway ssl list|status|issue|renew
nexus gateway nginx test|reload|logs
```
