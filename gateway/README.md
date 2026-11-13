# NexusOS Gateway

Native NGINX reverse proxy managed declaratively. Implementation:

| Component | Location |
|-----------|----------|
| Route model, validation, SSRF guard | `command-center/backend/nexus_core/gateway/model.py` |
| NGINX rendering | `.../gateway/render.py` |
| Activation (stage → swap → `nginx -t` → reload → rollback) | `.../gateway/apply.py` |
| Certificates (internal CA, self-signed, Let's Encrypt, import) | `.../gateway/certs.py` |
| Gateway API for UIs (status, backend tests) | `.../gateway/status.py` |
| Privileged gateway agent operations | `command-center/privileged-agent/nexus_agent/ops.py` (`gateway.*`) |
| NGINX include (`/etc/nginx/conf.d/nexusos-gateway.conf`) | `nginx/nexusos-gateway.conf` (generated from `render.NGINX_INCLUDE`) |
| Route JSON schema | `schema/route.schema.json` (generated from the Pydantic model) |
| Example routes | `routes/examples/` |

See `docs/gateway.md`.
