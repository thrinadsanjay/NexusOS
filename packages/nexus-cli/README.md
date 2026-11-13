# nexus-cli

`nexus` is the NexusOS Engineering Edition command-line toolkit.

```text
nexus version                  CLI, OS and Python versions
nexus help [GROUP]             help for all commands or one group
nexus system info|health       read-only system information and checks
nexus system update            preview APT upgrades, then upgrade after confirmation
nexus system cleanup           preview reclaimable space, clean after confirmation
nexus dev list                 project templates and detected toolchains
nexus dev create fastapi NAME  generate a working FastAPI project (offline)
nexus dev create react NAME    scaffold React via the documented Vite workflow
nexus cloud status             detect cloud/Kubernetes CLIs (never prints credentials)
nexus infra status             Docker, KVM/libvirt and Podman availability
nexus infra containers         list Docker containers via the Engine API
nexus ai status|models         detect Ollama and list local models
```

Most read-only commands accept `--json` for automation. Global options:
`--verbose/-v` (debug logging to stderr) and `--log-file PATH`.

## Development

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e 'packages/nexus-cli[test]'
pytest tests/cli
```

## Safety model

* Read-only by default. Nothing runs `sudo` without an interactive confirmation,
  and the exact command is printed first. Without a TTY, privileged steps are refused.
* Diagnostic output never includes environment variables, tokens or credential files.
* External programs are executed with argument lists (no shell) and timeouts.
