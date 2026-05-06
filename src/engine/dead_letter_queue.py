"""Dead Letter Queue — stores failed node executions for inspection, replay, and debugging."""

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger()


class DLQEntryStatus(str, Enum):
    PENDING = "pending"        # Awaiting inspection or replay
    REPLAYING = "replaying"    # Currently being replayed
    RESOLVED = "resolved"      # Manually resolved
    EXPIRED = "expired"        # Past retention period


@dataclass
class DLQEntry:
    """A single entry in the dead letter queue."""
    entry_id: str
    execution_id: str
    node_id: str
    node_type: str
    error_message: str
    error_type: str
    inputs: dict[str, Any]
    node_config: dict[str, Any]
    attempt_count: int
    max_retries: int
    status: DLQEntryStatus = DLQEntryStatus.PENDING
    created_at: str = ""
    updated_at: str = ""
    resolved_at: str | None = None
    resolution: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "execution_id": self.execution_id,
            "node_id": self.node_id,
            "node_type": self.node_type,
            "error_message": self.error_message,
            "error_type": self.error_type,
            "inputs": self.inputs,
            "node_config": self.node_config,
            "attempt_count": self.attempt_count,
            "max_retries": self.max_retries,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "resolved_at": self.resolved_at,
            "resolution": self.resolution,
            "metadata": self.metadata,
        }


class DeadLetterQueue:
    """In-memory dead letter queue for failed node executions.

    Features:
    - Add failed executions with full context
    - List/filter/search entries
    - Replay entries (re-execute the node)
    - Mark entries as resolved with resolution notes
    - Auto-expire old entries based on retention period
    - Statistics and monitoring
    """

    def __init__(
        self,
        max_size: int = 10000,
        retention_seconds: int = 7 * 24 * 3600,  # 7 days default
    ) -> None:
        self._entries: dict[str, DLQEntry] = {}
        self._max_size = max_size
        self._retention_seconds = retention_seconds
        self._entry_counter = 0

    def add(
        self,
        execution_id: str,
        node_id: str,
        node_type: str,
        error: Exception,
        inputs: dict[str, Any],
        node_config: dict[str, Any],
        attempt_count: int,
        max_retries: int,
        metadata: dict[str, Any] | None = None,
    ) -> DLQEntry:
        """Add a failed execution to the dead letter queue."""
        self._entry_counter += 1
        now = datetime.now(timezone.utc).isoformat()

        entry = DLQEntry(
            entry_id=f"dlq_{self._entry_counter}_{int(time.time())}",
            execution_id=execution_id,
            node_id=node_id,
            node_type=node_type,
            error_message=str(error),
            error_type=type(error).__name__,
            inputs=inputs,
            node_config=node_config,
            attempt_count=attempt_count,
            max_retries=max_retries,
            status=DLQEntryStatus.PENDING,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )

        self._entries[entry.entry_id] = entry

        # Evict oldest if over max size
        if len(self._entries) > self._max_size:
            oldest_key = min(self._entries, key=lambda k: self._entries[k].created_at)
            del self._entries[oldest_key]

        logger.warning(
            "Entry added to dead letter queue",
            entry_id=entry.entry_id,
            execution_id=execution_id,
            node_id=node_id,
            error_type=entry.error_type,
        )

        return entry

    def get(self, entry_id: str) -> DLQEntry | None:
        """Get a specific entry by ID."""
        return self._entries.get(entry_id)

    def list_entries(
        self,
        execution_id: str | None = None,
        node_type: str | None = None,
        status: DLQEntryStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[DLQEntry]:
        """List entries with optional filtering."""
        entries = list(self._entries.values())

        if execution_id:
            entries = [e for e in entries if e.execution_id == execution_id]
        if node_type:
            entries = [e for e in entries if e.node_type == node_type]
        if status:
            entries = [e for e in entries if e.status == status]

        # Sort by creation time, newest first
        entries.sort(key=lambda e: e.created_at, reverse=True)

        return entries[offset:offset + limit]

    def mark_replaying(self, entry_id: str) -> bool:
        """Mark an entry as being replayed."""
        entry = self._entries.get(entry_id)
        if entry and entry.status == DLQEntryStatus.PENDING:
            entry.status = DLQEntryStatus.REPLAYING
            entry.updated_at = datetime.now(timezone.utc).isoformat()
            return True
        return False

    def mark_resolved(self, entry_id: str, resolution: str = "") -> bool:
        """Mark an entry as resolved."""
        entry = self._entries.get(entry_id)
        if entry:
            entry.status = DLQEntryStatus.RESOLVED
            entry.resolved_at = datetime.now(timezone.utc).isoformat()
            entry.resolution = resolution
            entry.updated_at = datetime.now(timezone.utc).isoformat()
            return True
        return False

    def mark_pending(self, entry_id: str) -> bool:
        """Reset an entry back to pending (e.g., after failed replay)."""
        entry = self._entries.get(entry_id)
        if entry:
            entry.status = DLQEntryStatus.PENDING
            entry.updated_at = datetime.now(timezone.utc).isoformat()
            return True
        return False

    def cleanup_expired(self) -> int:
        """Remove expired entries. Returns count of removed entries."""
        now = time.time()
        expired_ids: list[str] = []

        for entry_id, entry in self._entries.items():
            try:
                created = datetime.fromisoformat(entry.created_at).timestamp()
                if now - created > self._retention_seconds:
                    expired_ids.append(entry_id)
            except (ValueError, TypeError):
                continue

        for entry_id in expired_ids:
            del self._entries[entry_id]

        if expired_ids:
            logger.info("Cleaned up expired DLQ entries", count=len(expired_ids))

        return len(expired_ids)

    def get_stats(self) -> dict[str, Any]:
        """Get queue statistics."""
        entries = list(self._entries.values())
        status_counts = {}
        node_type_counts = {}

        for entry in entries:
            status_counts[entry.status.value] = status_counts.get(entry.status.value, 0) + 1
            node_type_counts[entry.node_type] = node_type_counts.get(entry.node_type, 0) + 1

        return {
            "total_entries": len(entries),
            "by_status": status_counts,
            "by_node_type": node_type_counts,
            "max_size": self._max_size,
            "retention_seconds": self._retention_seconds,
        }

    def clear(self) -> int:
        """Clear all entries. Returns count of removed entries."""
        count = len(self._entries)
        self._entries.clear()
        return count

    def remove_entry(self, entry_id: str) -> bool:
        """Remove a specific entry."""
        if entry_id in self._entries:
            del self._entries[entry_id]
            return True
        return False


# Global singleton
dead_letter_queue = DeadLetterQueue()
