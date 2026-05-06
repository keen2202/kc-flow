"""Unit tests for CircuitBreaker."""

import pytest
import asyncio
from src.engine.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState
from src.core.exceptions import CircuitBreakerOpenError


class TestCircuitBreaker:
    """Test circuit breaker state transitions."""

    @pytest.fixture
    def breaker(self):
        return CircuitBreaker("test", CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout_seconds=0.1,
            half_open_max_calls=2,
            success_threshold=2,
        ))

    @pytest.mark.asyncio
    async def test_initial_state_closed(self, breaker):
        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_success_stays_closed(self, breaker):
        async def success():
            return "ok"

        result = await breaker.call(success)
        assert result == "ok"
        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_failures_open_circuit(self, breaker):
        async def fail():
            raise ConnectionError("fail")

        for _ in range(3):
            with pytest.raises(ConnectionError):
                await breaker.call(fail)

        assert breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_open_circuit_raises(self, breaker):
        async def fail():
            raise ConnectionError("fail")

        for _ in range(3):
            with pytest.raises(ConnectionError):
                await breaker.call(fail)

        async def success():
            return "ok"

        with pytest.raises(CircuitBreakerOpenError):
            await breaker.call(success)

    @pytest.mark.asyncio
    async def test_half_open_recovery(self, breaker):
        async def fail():
            raise ConnectionError("fail")

        # Trip the circuit
        for _ in range(3):
            with pytest.raises(ConnectionError):
                await breaker.call(fail)

        assert breaker.state == CircuitState.OPEN

        # Wait for recovery timeout
        await asyncio.sleep(0.15)

        # Should be half-open now
        assert breaker.state == CircuitState.HALF_OPEN

        # Successful calls should close it
        async def success():
            return "ok"

        for _ in range(2):
            await breaker.call(success)

        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_half_open_failure_reopens(self, breaker):
        async def fail():
            raise ConnectionError("fail")

        # Trip the circuit
        for _ in range(3):
            with pytest.raises(ConnectionError):
                await breaker.call(fail)

        # Wait for recovery
        await asyncio.sleep(0.15)
        assert breaker.state == CircuitState.HALF_OPEN

        # Failure in half-open reopens
        with pytest.raises(ConnectionError):
            await breaker.call(fail)

        assert breaker.state == CircuitState.OPEN

    def test_reset(self, breaker):
        breaker.reset()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.stats.consecutive_failures == 0
