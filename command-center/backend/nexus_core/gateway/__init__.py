"""Nexus Gateway: declarative routes rendered to native NGINX configuration.

Layout under /etc/nexusos/gateway/ (``nexus_core.paths.gateway_dir()``):

    routes/<id>.yaml          user-approved source definitions (declarative registry)
    generated/<id>.conf       NGINX server blocks rendered from routes (never edit)
    backups/<timestamp>/      previous working generated/ trees (last 10 kept)
    certificates/<name>/      fullchain.pem + privkey.pem (keys 0600 root)
    ca/                       internal certificate authority (ca.crt, ca.key 0600)
    acme/                     webroot for Let's Encrypt HTTP-01 challenges
    state.json                last successful activation

NGINX loads it through /etc/nginx/conf.d/nexusos-gateway.conf (shipped by nexusos-gateway).
"""
