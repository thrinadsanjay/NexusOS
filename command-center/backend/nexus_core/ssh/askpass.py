"""SSH_ASKPASS helper: answers OpenSSH password/passphrase prompts from the Secret Service.

Invoked by ssh with the prompt text as argv[1] and the credential reference in
NEXUS_CREDENTIAL_REF. It refuses every other prompt (notably host-key confirmation),
so a stored password can never be used to silently accept an unknown host key.
Installed as /usr/lib/nexusos/nexus-askpass.
"""

from __future__ import annotations

import os
import sys

ANSWERABLE = ("password", "passphrase", "verification code")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    prompt = (argv[1] if len(argv) > 1 else "").lower()
    ref = os.environ.get("NEXUS_CREDENTIAL_REF", "")
    if "yes/no" in prompt or "fingerprint" in prompt or not any(word in prompt for word in ANSWERABLE):
        sys.stderr.write("nexus-askpass: refusing to answer a non-password prompt\n")
        return 1
    if not ref or "verification code" in prompt:
        return 1
    from nexus_core.ssh.credentials import CredentialManager

    try:
        secret = CredentialManager().secret(ref)
    except Exception:
        return 1
    if secret is None:
        return 1
    sys.stdout.write(secret + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
