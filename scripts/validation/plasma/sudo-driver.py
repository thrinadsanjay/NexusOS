"""Run a check snippet as the current user with a scripted password box (test container only).

usage: NX_ANSWERS=pw1,pw2 python3 sudo-driver.py SNIPPET.py   → prints one "RESULT {json}" line
"""

import json
import os
import sys

from nexus_core import agent_client, privilege

answers = [a for a in os.environ.get("NX_ANSWERS", "").split(",") if a]
asked: list[dict] = []


def provider(req: privilege.AuthRequest) -> str | None:
    asked.append({"attempt": req.attempt, "error": req.error, "action": req.action})
    return answers.pop(0) if answers else None


privilege.set_password_provider(provider)


def out(**kw) -> None:
    profile = privilege.access()
    print("RESULT " + json.dumps({**kw, "asked": asked, "auth": profile.auth, "admin": profile.admin}, default=str))


with open(sys.argv[1], encoding="utf-8") as f:
    exec(compile(f.read(), sys.argv[1], "exec"), {"agent_client": agent_client, "privilege": privilege, "out": out})  # noqa: S102 — test snippets written by sudo-checks.sh
