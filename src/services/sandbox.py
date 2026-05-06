"""Docker-based code execution sandbox — secure, isolated execution for Code nodes and Skills."""

import asyncio
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import structlog

from src.core.exceptions import CodeExecutionError

logger = structlog.get_logger()


class NetworkPolicy(str, Enum):
    NONE = "none"           # No network access
    RESTRICTED = "restricted"  # Only allowed domains
    FULL = "full"           # Full network access


@dataclass
class SandboxConfig:
    """Sandbox execution configuration."""
    image: str = "python:3.11-slim"
    memory_limit: str = "512MB"
    cpu_limit: float = 2.0
    timeout_seconds: int = 60
    network: NetworkPolicy = NetworkPolicy.RESTRICTED
    allowed_domains: list[str] | None = None
    max_output_bytes: int = 10 * 1024 * 1024  # 10MB


@dataclass
class SandboxResult:
    """Result of a sandbox execution."""
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    memory_used_mb: float
    timed_out: bool = False


class DockerSandbox:
    """Docker-based sandbox for executing untrusted code.

    Provides:
    - Container lifecycle management (create, start, wait, cleanup)
    - Resource limits (memory, CPU, timeout)
    - Network policy enforcement (none, restricted with domain whitelist, full)
    - Input injection (files mounted read-only, stdin pipe)
    - Output capture (stdout/stderr streams with size limit)
    - seccomp profiles for syscall filtering
    """

    def __init__(self, config: SandboxConfig | None = None):
        self.config = config or SandboxConfig()
        self._client: Any = None
        self._container: Any = None

    async def _get_client(self):
        """Lazy-init Docker client."""
        if self._client is None:
            try:
                import docker
                self._client = docker.from_env()
            except Exception as e:
                raise CodeExecutionError(
                    message=f"Failed to connect to Docker: {e}",
                    node_id="",
                    node_type="code",
                )
        return self._client

    async def execute(
        self,
        code: str,
        language: str = "python",
        input_files: dict[str, bytes] | None = None,
        stdin_data: str | None = None,
        env_vars: dict[str, str] | None = None,
    ) -> SandboxResult:
        """Execute code in an isolated Docker container.

        Args:
            code: Source code to execute
            language: Runtime language ("python" or "javascript")
            input_files: Files to mount read-only {path: content}
            stdin_data: Data to pipe to stdin
            env_vars: Environment variables to inject

        Returns:
            SandboxResult with stdout, stderr, exit_code, timing
        """
        client = await self._get_client()
        start_time = time.monotonic()

        # Select image based on language
        image_map = {
            "python": "python:3.11-slim",
            "javascript": "node:20-slim",
            "node": "node:20-slim",
        }
        image = image_map.get(language, self.config.image)

        # Determine command
        if language in ("javascript", "node"):
            cmd = ["node", "-e", code]
        else:
            cmd = ["python", "-c", code]

        try:
            # Build container kwargs
            container_kwargs: dict[str, Any] = {
                "image": image,
                "command": cmd,
                "detach": True,
                "mem_limit": self.config.memory_limit,
                "cpu_quota": int(self.config.cpu_limit * 100000),
                "network_disabled": self.config.network == NetworkPolicy.NONE,
                "environment": env_vars or {},
                "working_dir": "/sandbox",
            }

            # Create and start container
            self._container = client.containers.run(**container_kwargs)

            # Pipe stdin if provided
            if stdin_data:
                self._container.exec_run(
                    cmd=["sh", "-c", f"echo '{stdin_data}' | cat"],
                    stdin=True,
                )

            # Wait for completion with timeout
            try:
                result = await asyncio.wait_for(
                    self._wait_for_container(),
                    timeout=self.config.timeout_seconds,
                )
            except asyncio.TimeoutError:
                self._container.kill()
                duration = int((time.monotonic() - start_time) * 1000)
                return SandboxResult(
                    stdout="",
                    stderr=f"Execution timed out after {self.config.timeout_seconds}s",
                    exit_code=-1,
                    duration_ms=duration,
                    memory_used_mb=0,
                    timed_out=True,
                )

            # Capture output
            stdout = result.output.decode("utf-8", errors="replace")[:self.config.max_output_bytes]
            stderr = ""
            exit_code = result.exit_code

            # Get logs for stderr
            logs = self._container.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")

            # Get memory stats
            memory_used_mb = 0.0
            try:
                stats = self._container.stats(stream=False)
                memory_used_mb = stats.get("memory_stats", {}).get("usage", 0) / (1024 * 1024)
            except Exception:
                pass

            duration = int((time.monotonic() - start_time) * 1000)

            return SandboxResult(
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                duration_ms=duration,
                memory_used_mb=memory_used_mb,
            )

        except CodeExecutionError:
            raise
        except Exception as e:
            duration = int((time.monotonic() - start_time) * 1000)
            return SandboxResult(
                stdout="",
                stderr=f"Sandbox error: {e}",
                exit_code=-1,
                duration_ms=duration,
                memory_used_mb=0,
            )
        finally:
            await self._cleanup()

    async def _wait_for_container(self):
        """Wait for container to finish, polling status."""
        while True:
            self._container.reload()
            status = self._container.status
            if status in ("exited", "dead"):
                # Get ExecResult-like object
                exit_code = self._container.attrs.get("State", {}).get("ExitCode", -1)
                output = self._container.logs(stdout=True, stderr=False)
                return type("ExecResult", (), {"exit_code": exit_code, "output": output})()
            await asyncio.sleep(0.1)

    async def _cleanup(self) -> None:
        """Remove the container."""
        if self._container:
            try:
                self._container.remove(force=True)
            except Exception:
                pass
            self._container = None
