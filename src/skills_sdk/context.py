"""SkillContext — runtime API available to skills during execution.

Provides:
- Structured logging (structlog)
- HTTP client (httpx)
- Template rendering (Jinja2)
- Key-value caching
- File I/O (within sandbox)
- Metric recording
- Execution metadata
"""

import json
import time
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()


class SkillContext:
    """Runtime context injected into skill handlers during execution.

    Usage in handler.py:
        def handle(inputs: dict, context: SkillContext) -> dict:
            context.logger.info("Processing", input_keys=list(inputs.keys()))
            result = context.http_request("GET", "https://api.example.com/data")
            template = context.load_template("prompt.jinja2")
            rendered = template.render(**inputs)
            return {"output": rendered}
    """

    def __init__(
        self,
        execution_id: str,
        skill_name: str,
        skill_version: str,
        user_id: str,
        working_dir: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.execution_id = execution_id
        self.skill_name = skill_name
        self.skill_version = skill_version
        self.user_id = user_id
        self.working_dir = Path(working_dir) if working_dir else Path.cwd()
        self.metadata = metadata or {}

        self._cache: dict[str, tuple[Any, float]] = {}  # key -> (value, expires_at)
        self._metrics: list[dict[str, Any]] = []
        self._start_time = time.monotonic()

        self.logger = structlog.get_logger().bind(
            skill=skill_name,
            execution_id=execution_id,
        )

    # ── HTTP Client ──

    def http_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: Any = None,
        timeout: int = 30,
    ) -> dict[str, Any]:
        """Make an HTTP request. Returns {status_code, headers, body}.

        This is a synchronous wrapper. Skills running in async context
        should use httpx.AsyncClient directly.
        """
        import httpx

        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=body if isinstance(body, (dict, list)) else None,
                    content=body if isinstance(body, (bytes, str)) and not isinstance(body, (dict, list)) else None,
                )
                try:
                    response_body = response.json()
                except Exception:
                    response_body = response.text

                return {
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "body": response_body,
                }
        except Exception as e:
            self.logger.error("HTTP request failed", url=url, error=str(e))
            raise

    # ── Template Rendering ──

    def load_template(self, path: str) -> Any:
        """Load a Jinja2 template from the skill directory."""
        from jinja2 import Environment, FileSystemLoader

        template_path = self.working_dir / path
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")

        env = Environment(loader=FileSystemLoader(str(self.working_dir)))
        return env.get_template(path)

    def render_template(self, template_str: str, **kwargs: Any) -> str:
        """Render a Jinja2 template string with variables."""
        from jinja2 import Environment, BaseLoader

        env = Environment(loader=BaseLoader())
        template = env.from_string(template_str)
        return template.render(**kwargs)

    # ── Caching ──

    def cache_get(self, key: str) -> Any | None:
        """Get a value from the cache."""
        if key in self._cache:
            value, expires_at = self._cache[key]
            if expires_at == 0 or time.time() < expires_at:
                return value
            del self._cache[key]
        return None

    def cache_set(self, key: str, value: Any, ttl: int = 3600) -> None:
        """Set a value in the cache with TTL in seconds."""
        expires_at = time.time() + ttl if ttl > 0 else 0
        self._cache[key] = (value, expires_at)

    # ── File I/O ──

    def read_file(self, path: str) -> str:
        """Read a file from the working directory."""
        file_path = self.working_dir / path
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        return file_path.read_text(encoding="utf-8")

    def write_file(self, path: str, content: str) -> None:
        """Write a file to the working directory."""
        file_path = self.working_dir / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

    def read_json(self, path: str) -> Any:
        """Read and parse a JSON file."""
        return json.loads(self.read_file(path))

    def write_json(self, path: str, data: Any) -> None:
        """Write data as JSON to a file."""
        self.write_file(path, json.dumps(data, indent=2, ensure_ascii=False))

    # ── Metrics ──

    def record_metric(self, name: str, value: float, tags: dict[str, str] | None = None) -> None:
        """Record a metric for monitoring."""
        self._metrics.append({
            "name": name,
            "value": value,
            "tags": tags or {},
            "timestamp": time.time(),
        })

    def get_metrics(self) -> list[dict[str, Any]]:
        """Get all recorded metrics."""
        return list(self._metrics)

    # ── Timing ──

    @property
    def elapsed_ms(self) -> int:
        """Get elapsed time in milliseconds since context creation."""
        return int((time.monotonic() - self._start_time) * 1000)

    # ── LLM Client ──

    def get_llm_client(self, model: str = "gpt-4o") -> Any:
        """Get an LLM client for the specified model.

        Returns a ModelRouter instance for making LLM calls.
        """
        from src.services.model_router import ModelRouter
        return ModelRouter()
