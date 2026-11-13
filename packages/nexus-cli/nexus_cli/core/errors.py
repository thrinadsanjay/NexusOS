"""Exception types that map to user-facing messages and exit codes."""

from __future__ import annotations


class NexusError(Exception):
    """An expected, user-actionable failure. Printed without a traceback."""

    exit_code = 1

    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


class DependencyMissingError(NexusError):
    """A required external program or service is not available."""

    exit_code = 3


class ValidationError(NexusError):
    """User input failed validation."""

    exit_code = 2


class AbortedError(NexusError):
    """The user declined a confirmation, or confirmation was impossible."""

    exit_code = 4
