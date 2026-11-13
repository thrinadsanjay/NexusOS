"""NexusOS management agent: a small, socket-activated privileged helper.

It performs only the allow-listed operations in :mod:`nexus_agent.ops`, authorizes
each request with polkit, audits it, and exits after a period of inactivity.
"""

__version__ = "0.2.0"
