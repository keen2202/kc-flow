"""Checkpoint Manager — save and restore workflow execution state for pause/resume."""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import structlog

from src.engine.abstractions import NodeStatus
from src.engine.variable_pool import VariablePool

logger = structlog.get_logger()


@dataclass
class CheckpointData:
    """A snapshot of workflow execution state."""
    checkpoint_id: str
    execution_id: str
    sequence_number: int
    graph_state: dict[str, Any]  # node_states, ready_queue, blocked_nodes
    variable_pool_snapshot: dict[str, Any]
    created_at: str


class CheckpointManager:
    """Manages execution checkpoints for pause/resume capability.

    Checkpoints capture:
    - Node execution states (PENDING/RUNNING/SUCCEEDED/etc.)
    - Ready queue contents
    - Variable Pool full snapshot
    """

    def __init__(self, max_checkpoints_per_execution: int = 100) -> None:
        self._checkpoints: dict[str, list[CheckpointData]] = {}  # execution_id → checkpoints
        self._sequence_counters: dict[str, int] = {}
        self.max_checkpoints = max_checkpoints_per_execution

    def save_checkpoint(
        self,
        execution_id: str,
        node_states: dict[str, NodeStatus],
        ready_queue: list[str],
        variable_pool: VariablePool,
    ) -> CheckpointData:
        """Save a checkpoint of the current execution state."""
        seq = self._sequence_counters.get(execution_id, 0) + 1
        self._sequence_counters[execution_id] = seq

        checkpoint = CheckpointData(
            checkpoint_id=str(uuid.uuid4()),
            execution_id=execution_id,
            sequence_number=seq,
            graph_state={
                "node_states": {nid: s.value for nid, s in node_states.items()},
                "ready_queue": list(ready_queue),
            },
            variable_pool_snapshot=variable_pool.snapshot(),
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        if execution_id not in self._checkpoints:
            self._checkpoints[execution_id] = []
        self._checkpoints[execution_id].append(checkpoint)

        # Trim old checkpoints
        if len(self._checkpoints[execution_id]) > self.max_checkpoints:
            self._checkpoints[execution_id] = self._checkpoints[execution_id][-self.max_checkpoints:]

        logger.debug("Checkpoint saved", execution_id=execution_id, sequence=seq)
        return checkpoint

    def get_latest_checkpoint(self, execution_id: str) -> CheckpointData | None:
        """Get the most recent checkpoint for an execution."""
        checkpoints = self._checkpoints.get(execution_id, [])
        return checkpoints[-1] if checkpoints else None

    def get_checkpoint(self, execution_id: str, checkpoint_id: str) -> CheckpointData | None:
        """Get a specific checkpoint by ID."""
        for cp in self._checkpoints.get(execution_id, []):
            if cp.checkpoint_id == checkpoint_id:
                return cp
        return None

    def list_checkpoints(self, execution_id: str) -> list[CheckpointData]:
        """List all checkpoints for an execution."""
        return list(self._checkpoints.get(execution_id, []))

    def restore_checkpoint(
        self,
        checkpoint: CheckpointData,
        variable_pool: VariablePool,
    ) -> tuple[dict[str, NodeStatus], list[str]]:
        """Restore execution state from a checkpoint.

        Returns:
            (node_states, ready_queue) tuple
        """
        # Restore Variable Pool
        variable_pool.restore(checkpoint.variable_pool_snapshot)

        # Restore node states
        node_states = {
            nid: NodeStatus(state)
            for nid, state in checkpoint.graph_state.get("node_states", {}).items()
        }

        # Restore ready queue
        ready_queue = list(checkpoint.graph_state.get("ready_queue", []))

        logger.info(
            "Checkpoint restored",
            execution_id=checkpoint.execution_id,
            sequence=checkpoint.sequence_number,
            ready_queue_size=len(ready_queue),
        )

        return node_states, ready_queue

    def cleanup(self, execution_id: str) -> None:
        """Remove all checkpoints for an execution."""
        self._checkpoints.pop(execution_id, None)
        self._sequence_counters.pop(execution_id, None)
