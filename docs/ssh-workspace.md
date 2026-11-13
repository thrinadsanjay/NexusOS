# Terminal & SSH workspace

Local terminals and remote sessions run in **Konsole**, using **OpenSSH**; NexusOS adds
profile management, secure credentials, host-key verification and SFTP on top. No terminal
emulator or SSH protocol is implemented by NexusOS.

## Local terminals

`New terminal` opens a Konsole tab (`konsole --new-tab --workdir … -p tabtitle=… --profile Nexus`)
with the default shell, Bash or Zsh. Tabs, split panes (Ctrl+( / Ctrl+)), search
(Ctrl+Shift+F), copy/paste, fonts, colour schemes, keyboard shortcuts and output export
(File › Save Output As) are Konsole features. Shell history is the user's own.
Named layouts (sets of tabs/profiles) are stored and can be reopened; production profiles
never reconnect automatically (`reconnect_on_restore` defaults to false).

**Status:** launching implemented; verified only by unit tests — needs a Plasma session (VM).
Embedding the terminal inside the Command Center window is **planned**.

## Connection profiles

Stored in `~/.local/share/nexusos/command-center.db` (0600). A profile holds name,
host/IP, port, user, auth method (`agent`, `key`, `password`), key **path** reference,
credential **reference**, jump host (another profile → `ProxyJump`), port forwards
(local, remote, SOCKS), allowed OpenSSH options, group (Favorites, Production,
Development, Homelab, Cloud servers, Custom), tags, favorite, Konsole profile, notes.

Validation rejects anything that could inject commands: only allow-listed options
(`ServerAliveInterval`, `Compression`, `StrictHostKeyChecking` = yes/ask/accept-new — never
`no` — …); `ProxyCommand`, `LocalCommand` and friends are refused; jump-host loops are
refused; agent forwarding requires explicit, recorded consent.

## Sessions

A per-session OpenSSH config is generated into `$XDG_RUNTIME_DIR/nexusos/ssh_config`
(0600, includes `~/.ssh/config` last) and used with `ssh -F <config> nexus-<id>` in a
Konsole tab. Connection events feed history and "Recent".

## Credentials

* Stored in the **Secret Service** (KDE Wallet on Plasma; GNOME Keyring also works) via
  `python3-secretstorage`, attributes `application=nexusos, ref=<name>`.
* **No plaintext fallback**: without a Secret Service, saving fails (tested).
* Profiles store only a reference. Metadata (kind, username, rotation reminder) is in SQLite.
* Password and key-passphrase prompts are answered by `/usr/lib/nexusos/nexus-askpass`
  (`SSH_ASKPASS_REQUIRE=force`). It answers only password/passphrase prompts and **refuses
  host-key and other questions**; password profiles also force `StrictHostKeyChecking yes`,
  so a stored password can never silently accept an unknown host.
* Private keys are referenced by path and never copied.

## Host keys

`Verify host key` / `nexus ssh trust` runs `ssh-keyscan`, shows SHA256 fingerprints and, after
the user confirms they match, appends them to `~/.ssh/known_hosts` (0600).

## SFTP

Paramiko with `RejectPolicy` and the user's `known_hosts`: list, navigate, upload, download
(progress, cancellation), mkdir, rename, delete (confirmation; refuses `/`; directories
must be empty). Credentials come from the Secret Service. SFTP through jump hosts is not
supported yet (use `sftp -J` in a terminal). The connection is closed when the page is hidden.

## Status

| Feature | Status |
|---------|--------|
| Profiles CRUD, groups, favorites, tags, search, history, recent | Implemented, tested |
| Generated OpenSSH config: ports, users, ProxyJump, forwards, options | Implemented, tested |
| Agent forwarding with consent | Implemented, tested |
| Secret Service credentials, rotation reminders, no plaintext | Implemented, tested (memory backend + fail-closed) |
| askpass behaviour | Implemented, tested |
| Known-host verification | Implemented, tested (ssh-keygen) |
| SFTP operations | Implemented, tested with a fake client; **experimental** against real servers |
| Konsole tabs / split panes | Experimental (needs Plasma VM) |
| Embedded terminal widget | Planned |
| KDE Wallet as Secret Service on Plasma 6.6 | To verify in the VM |

## CLI

```bash
nexus ssh add homelab admin@192.168.1.10:2222 --group Homelab --tag nas --forward L:127.0.0.1:8080:127.0.0.1:80
nexus ssh list [query] / profiles / config
nexus ssh trust homelab
nexus ssh connect homelab [--here]
nexus ssh credentials set homelab-root --kind ssh-password   # prompts without echo
nexus ssh credentials list|delete
nexus ssh remove homelab
```
