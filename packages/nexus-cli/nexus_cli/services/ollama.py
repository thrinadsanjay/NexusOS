"""Ollama local-inference detection via its HTTP API (read-only endpoints)."""

from __future__ import annotations

import os

import httpx

from nexus_cli.core import runner
from nexus_cli.core.errors import ValidationError
from nexus_cli.core.logging import get_logger
from nexus_cli.models import OllamaModel, OllamaStatus

log = get_logger("ollama")

DEFAULT_ENDPOINT = "http://127.0.0.1:11434"
API_TIMEOUT = 3.0


def resolve_endpoint(raw: str | None = None) -> str:
    """Normalise OLLAMA_HOST-style values ("0.0.0.0", "host:port", URLs) into a base URL.

    Credentials embedded in the URL are rejected so they can never be echoed in output.
    """
    value = (raw if raw is not None else os.environ.get("OLLAMA_HOST", "")).strip()
    if not value:
        return DEFAULT_ENDPOINT
    if "://" not in value:
        value = f"http://{value}"
    try:
        url = httpx.URL(value)
    except (httpx.InvalidURL, TypeError) as exc:
        raise ValidationError(f"invalid Ollama endpoint: {value!r}") from exc
    if url.scheme not in {"http", "https"} or not url.host:
        raise ValidationError(f"unsupported Ollama endpoint: {value!r}")
    if url.userinfo:
        raise ValidationError("Ollama endpoint must not contain credentials")
    # A wildcard *bind* address means "this machine" for a client.
    host = "127.0.0.1" if url.host in {"0.0.0.0", "::"} else url.host  # noqa: S104
    port = url.port or 11434
    if ":" in host:  # IPv6 literal
        host = f"[{host}]"
    return f"{url.scheme}://{host}:{port}"


def _client(endpoint: str, transport: httpx.BaseTransport | None) -> httpx.Client:
    return httpx.Client(base_url=endpoint, timeout=API_TIMEOUT, transport=transport)


def ollama_status(endpoint: str | None = None, transport: httpx.BaseTransport | None = None) -> OllamaStatus:
    endpoint = endpoint or resolve_endpoint()
    status = OllamaStatus(endpoint=endpoint, cli_installed=runner.which("ollama") is not None, reachable=False)
    try:
        with _client(endpoint, transport) as client:
            response = client.get("/api/version")
            response.raise_for_status()
            status.version = response.json().get("version")
            status.reachable = True
    except httpx.ConnectError:
        status.error = "Ollama is not running or not installed"
    except (httpx.HTTPError, ValueError) as exc:
        status.error = f"Ollama API error: {exc.__class__.__name__}"
    if not status.reachable:
        status.hint = (
            "start it with `systemctl start ollama` (or `ollama serve`)"
            if status.cli_installed
            else "Ollama is optional; see `manifests/ai.yaml` and docs/installation.md for opt-in install steps"
        )
    return status


def list_models(endpoint: str | None = None, transport: httpx.BaseTransport | None = None) -> list[OllamaModel]:
    """Locally installed models. Raises httpx errors to the caller, which reports them."""
    endpoint = endpoint or resolve_endpoint()
    with _client(endpoint, transport) as client:
        response = client.get("/api/tags")
        response.raise_for_status()
        payload = response.json()
    models = []
    for item in payload.get("models", []):
        details = item.get("details") or {}
        models.append(
            OllamaModel(
                name=item.get("name") or item.get("model") or "?",
                size_bytes=int(item.get("size") or 0),
                modified_at=item.get("modified_at"),
                family=details.get("family"),
                parameter_size=details.get("parameter_size"),
                quantization=details.get("quantization_level"),
            )
        )
    return sorted(models, key=lambda m: m.name)
