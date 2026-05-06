"""Retry policy with exponential backoff and jitter for node execution."""

import asyncio
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine

import structlog

logger = structlog.get_logger()


class BackoffStrategy(str, Enum):
    FIXED = "fixed"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"


@dataclass
class RetryPolicy:
    """Configuration for retry behavior.

    Supports:
    - Exponential backoff with configurable base and factor
    - Jitter to prevent thundering herd
    - Maximum delay cap
    - Configurable retryable exception types
    """
    max_retries: int = 3
    backoff_strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL
    base_delay_ms: int = 1000
    max_delay_ms: int = 30000
    backoff_factor: float = 2.0
    jitter: bool = True
    retryable_exceptions: tuple[type[Exception], ...] = (TimeoutError, ConnectionError, OSError)

    def compute_delay(self, attempt: int) -> float:
        """Compute delay in seconds for the given attempt number (0-indexed)."""
        if self.backoff_strategy == BackoffStrategy.FIXED:
            delay_ms = self.base_delay_ms
        elif self.backoff_strategy == BackoffStrategy.LINEAR:
            delay_ms = self.base_delay_ms * (attempt + 1)
        else:  # EXPONENTIAL
            delay_ms = self.base_delay_ms * (self.backoff_factor ** attempt)

        delay_ms = min(delay_ms, self.max_delay_ms)

        if self.jitter:
            # Full jitter: uniform random between 0 and computed delay
            delay_ms = random.uniform(0, delay_ms)

        return delay_ms / 1000.0

    def is_retryable(self, exception: Exception) -> bool:
        """Check if an exception is retryable."""
        return isinstance(exception, self.retryable_exceptions)


@dataclass
class RetryResult:
    """Result of a retry-wrapped execution."""
    success: bool
    result: Any = None
    error: Exception | None = None
    attempts: int = 0
    total_duration_ms: int = 0
    errors: list[Exception] = field(default_factory=list)


async def execute_with_retry(
    func: Callable[..., Coroutine[Any, Any, Any]],
    policy: RetryPolicy,
    *args: Any,
    **kwargs: Any,
) -> RetryResult:
    """Execute an async function with retry logic.

    Args:
        func: Async function to execute
        policy: Retry policy configuration
        *args: Positional arguments for func
        **kwargs: Keyword arguments for func

    Returns:
        RetryResult with success status, result or error, and attempt count
    """
    start_time = time.monotonic()
    errors: list[Exception] = []

    for attempt in range(policy.max_retries + 1):
        try:
            result = await func(*args, **kwargs)
            duration = int((time.monotonic() - start_time) * 1000)
            return RetryResult(
                success=True,
                result=result,
                attempts=attempt + 1,
                total_duration_ms=duration,
                errors=errors,
            )
        except Exception as e:
            errors.append(e)

            if not policy.is_retryable(e) or attempt >= policy.max_retries:
                duration = int((time.monotonic() - start_time) * 1000)
                return RetryResult(
                    success=False,
                    error=e,
                    attempts=attempt + 1,
                    total_duration_ms=duration,
                    errors=errors,
                )

            delay = policy.compute_delay(attempt)
            logger.warning(
                "Retrying after error",
                attempt=attempt + 1,
                max_retries=policy.max_retries,
                delay_seconds=round(delay, 2),
                error=str(e),
            )
            await asyncio.sleep(delay)

    # Should not reach here, but just in case
    duration = int((time.monotonic() - start_time) * 1000)
    return RetryResult(
        success=False,
        error=errors[-1] if errors else RuntimeError("Unknown error"),
        attempts=policy.max_retries + 1,
        total_duration_ms=duration,
        errors=errors,
    )
