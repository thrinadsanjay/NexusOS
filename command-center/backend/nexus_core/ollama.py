"""Ollama local-inference detection via its HTTP API (read-only endpoints)."""

from __future__ import annotations

import os

import httpx

from nexus_core import runner
from nexus_core.errors import ValidationError
from nexus_core.log import get_logger
from nexus_core.models import OllamaModel, OllamaStatus

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


# =====================================================================================
# v0.2: model management and chat (direct Ollama HTTP API; no other inference engine)
# =====================================================================================

import json as _json  # noqa: E402
from collections.abc import Iterator  # noqa: E402

from pydantic import BaseModel, Field  # noqa: E402

from nexus_core.errors import NexusError  # noqa: E402

MODEL_NAME_RE = __import__("re").compile(r"^[a-zA-Z0-9][a-zA-Z0-9._\-/]{0,100}(:[a-zA-Z0-9._\-]{1,64})?$")
INSTALL_DOC = "https://ollama.com/download/linux"


def _model(name: str) -> str:
    if not MODEL_NAME_RE.match(name or ""):
        raise ValidationError(f"invalid model name {name!r}")
    return name


class ModelInfo(OllamaModel):
    context_length: int | None = None
    capabilities: list[str] = Field(default_factory=list)


class RunningModel(BaseModel):
    name: str
    size_bytes: int
    vram_bytes: int
    expires_at: str | None = None

    @property
    def mode(self) -> str:
        if self.vram_bytes <= 0:
            return "CPU"
        return "GPU" if self.vram_bytes >= self.size_bytes else "CPU+GPU"


def show(name: str, endpoint: str | None = None, transport: httpx.BaseTransport | None = None) -> ModelInfo:
    endpoint = endpoint or resolve_endpoint()
    with _client(endpoint, transport) as client:
        response = client.post("/api/show", json={"model": _model(name)})
        if response.status_code == 404:
            raise NexusError(f"model {name} is not installed")
        response.raise_for_status()
        data = response.json()
    details = data.get("details") or {}
    context = next((v for k, v in (data.get("model_info") or {}).items() if k.endswith(".context_length")), None)
    return ModelInfo(
        name=name,
        family=details.get("family"),
        parameter_size=details.get("parameter_size"),
        quantization=details.get("quantization_level"),
        context_length=context,
        capabilities=data.get("capabilities") or [],
    )


def running(endpoint: str | None = None, transport: httpx.BaseTransport | None = None) -> list[RunningModel]:
    endpoint = endpoint or resolve_endpoint()
    with _client(endpoint, transport) as client:
        response = client.get("/api/ps")
        response.raise_for_status()
        models = response.json().get("models", [])
    return [
        RunningModel(
            name=m.get("name", "?"),
            size_bytes=int(m.get("size") or 0),
            vram_bytes=int(m.get("size_vram") or 0),
            expires_at=m.get("expires_at"),
        )
        for m in models
    ]


def pull(
    name: str, endpoint: str | None = None, transport: httpx.BaseTransport | None = None, cancel=None
) -> Iterator[dict]:
    """Stream download progress events ({status, total, completed}). Only on explicit user request."""
    endpoint = endpoint or resolve_endpoint()
    with (
        httpx.Client(base_url=endpoint, timeout=httpx.Timeout(30, read=None), transport=transport) as client,
        client.stream("POST", "/api/pull", json={"model": _model(name), "stream": True}) as response,
    ):
        response.raise_for_status()
        for line in response.iter_lines():
            if cancel is not None and cancel.is_set():
                return
            if line.strip():
                event = _json.loads(line)
                if "error" in event:
                    raise NexusError(f"download failed: {event['error']}")
                yield event


def delete(name: str, endpoint: str | None = None, transport: httpx.BaseTransport | None = None) -> None:
    endpoint = endpoint or resolve_endpoint()
    with _client(endpoint, transport) as client:
        response = client.request("DELETE", "/api/delete", json={"model": _model(name)})
        if response.status_code == 404:
            raise NexusError(f"model {name} is not installed")
        response.raise_for_status()


class ChatOptions(BaseModel):
    temperature: float | None = None
    num_ctx: int | None = None
    top_p: float | None = None
    seed: int | None = None

    def payload(self) -> dict:
        return {k: v for k, v in self.model_dump().items() if v is not None}


def chat_stream(
    model: str,
    messages: list[dict[str, str]],
    options: ChatOptions | None = None,
    endpoint: str | None = None,
    transport: httpx.BaseTransport | None = None,
    cancel=None,
) -> Iterator[str]:
    """Yield response text chunks as they stream. Setting *cancel* stops generation."""
    endpoint = endpoint or resolve_endpoint()
    for m in messages:
        if m.get("role") not in ("system", "user", "assistant"):
            raise ValidationError("invalid chat role")
    body = {"model": _model(model), "messages": messages, "stream": True}
    if options and options.payload():
        body["options"] = options.payload()
    with (
        httpx.Client(base_url=endpoint, timeout=httpx.Timeout(30, read=600), transport=transport) as client,
        client.stream("POST", "/api/chat", json=body) as response,
    ):
        if response.status_code == 404:
            raise NexusError(f"model {model} is not installed", hint=f"download it first: nexus ai pull {model}")
        response.raise_for_status()
        for line in response.iter_lines():
            if cancel is not None and cancel.is_set():
                return
            if not line.strip():
                continue
            event = _json.loads(line)
            if "error" in event:
                raise NexusError(f"Ollama: {event['error']}")
            chunk = (event.get("message") or {}).get("content", "")
            if chunk:
                yield chunk
            if event.get("done"):
                return


def gpu_inference_support() -> dict:
    """What Ollama could use: NVIDIA CUDA (nvidia-smi) or AMD ROCm (/dev/kfd). CPU otherwise."""
    from pathlib import Path

    nvidia = runner.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"], timeout=5)
    return {
        "nvidia": nvidia.stdout.strip().splitlines() if nvidia.ok else [],
        "amd_rocm_device": Path("/dev/kfd").exists(),
        "note": "Ollama decides the backend at load time; see `nexus ai status` for the running mode.",
    }
