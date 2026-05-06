"""Circuit Breaker pattern — prevents cascading failures by temporarily blocking calls to failing services."""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum

import structlog

from src.core.exceptions import CircuitBreakerOpenError

logger = structlog.get_logger()


class CircuitState(str, Enum):
    CLOSED = "closed"        # Normal operation — requests pass through
    OPEN = "open"            # Circuit tripped — requests are rejected
    HALF_OPEN = "half_open"  # Testing — limited requests allowed to check recovery


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration."""
    failure_threshold: int = 5          # Failures before opening
    recovery_timeout_seconds: float = 60  # Time before half-open
    half_open_max_calls: int = 3        # Test calls in half-open state
    success_threshold: int = 2          # Successes to close from half-open
    excluded_exceptions: tuple[type[Exception], ...] = ()  # Don't count these as failures


@dataclass
class CircuitBreakerStats:
    """Circuit breaker statistics."""
    total_calls: int = 0
    total_failures: int = 0
    total_successes: int = 0
    consecutive_failures: int = 0
    last_failure_time: float = 0
    last_success_time: float = 0
    state_changes: list[tuple[str, str, float]] = field(default_factory=list)  # (from, to, timestamp)


class CircuitBreaker:
    """Circuit breaker implementation with three states: CLOSED, OPEN, HALF_OPEN.

    Usage:
        breaker = CircuitBreaker("llm_service", CircuitBreakerConfig())
        result = await breaker.call(some_async_function, *args)
    """

    def __init__(self, name: str, config: CircuitBreakerConfig | None = None) -> None:
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._stats = CircuitBreakerStats()
        self._half_open_calls = 0
        self._half_open_successes = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Get current circuit state, transitioning OPEN to HALF_OPEN if recovery timeout elapsed."""
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._stats.last_failure_time
            if elapsed >= self.config.recovery_timeout_seconds:
                self._transition(CircuitState.HALF_OPEN)
        return self._state

    @property
    def stats(self) -> CircuitBreakerStats:
        return self._stats

    def _transition(self, new_state: CircuitState) -> None:
        """Transition to a new state."""
        old_state = self._state
        self._state = new_state
        self._stats.state_changes.append((old_state.value, new_state.value, time.monotonic()))

        if new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
            self._half_open_successes = 0

        logger.info(
            "Circuit breaker state change",
            name=self.name,
            from_state=old_state.value,
            to_state=new_state.value,
        )

    async def call(self, func, *args, **kwargs):
        """Execute a function through the circuit breaker.

        Raises CircuitBreakerOpenError if the circuit is OPEN.
        """
        async with self._lock:
            current_state = self.state

            if current_state == CircuitState.OPEN:
                raise CircuitBreakerOpenError(
                    message=f"Circuit breaker '{self.name}' is OPEN",
                    details={
                        "name": self.name,
                        "failure_count": self._stats.consecutive_failures,
                        "recovery_timeout": self.config.recovery_timeout_seconds,
                    },
                )

            if current_state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self.config.half_open_max_calls:
                    raise CircuitBreakerOpenError(
                        message=f"Circuit breaker '{self.name}' is HALF_OPEN, max test calls reached",
                    )
                self._half_open_calls += 1

        # Execute the function
        self._stats.total_calls += 1
        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except Exception as e:
            if not isinstance(e, self.config.excluded_exceptions):
                await self._on_failure(e)
            raise

    async def _on_success(self) -> None:
        """Handle successful call."""
        async with self._lock:
            self._stats.total_successes += 1
            self._stats.consecutive_failures = 0
            self._stats.last_success_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                self._half_open_successes += 1
                if self._half_open_successes >= self.config.success_threshold:
                    self._transition(CircuitState.CLOSED)

    async def _on_failure(self, error: Exception) -> None:
        """Handle failed call."""
        async with self._lock:
            self._stats.total_failures += 1
            self._stats.consecutive_failures += 1
            self._stats.last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open goes back to open
                self._transition(CircuitState.OPEN)
            elif self._state == CircuitState.CLOSED:
                if self._stats.consecutive_failures >= self.config.failure_threshold:
                    self._transition(CircuitState.OPEN)

    def reset(self) -> None:
        """Manually reset the circuit breaker to CLOSED state."""
        self._state = CircuitState.CLOSED
        self._stats.consecutive_failures = 0
        self._half_open_calls = 0
        self._half_open_successes = 0
        logger.info("Circuit breaker manually reset", name=self.name)


class CircuitBreakerRegistry:
    """Registry for managing multiple circuit breakers."""

    def __init__(self) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}

    def get_or_create(
        self, name: str, config: CircuitBreakerConfig | None = None
    ) -> CircuitBreaker:
        """Get an existing circuit breaker or create a new one."""
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(name, config)
        return self._breakers[name]

    def get(self, name: str) -> CircuitBreaker | None:
        """Get a circuit breaker by name."""
        return self._breakers.get(name)

    def reset_all(self) -> None:
        """Reset all circuit breakers."""
        for breaker in self._breakers.values():
            breaker.reset()

    def list_breakers(self) -> list[dict]:
        """List all circuit breakers with their states."""
        return [
            {
                "name": name,
                "state": breaker.state.value,
                "consecutive_failures": breaker.stats.consecutive_failures,
                "total_calls": breaker.stats.total_calls,
                "total_failures": breaker.stats.total_failures,
            }
            for name, breaker in self._breakers.items()
        ]


# Global singleton
circuit_breaker_registry = CircuitBreakerRegistry()
