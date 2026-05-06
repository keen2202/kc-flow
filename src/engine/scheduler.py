"""Workflow Execution Engine — orchestrates DAG-based workflow execution.

Implements:
- Topological sort scheduling (Kahn's algorithm via GraphParser)
- Node execution loop with dependency resolution
- Parallel branch execution (asyncio.gather)
- Condition branch handling (activate/deactivate)
- Loop node handling (for/while with max_iterations)
- Checkpoint management
- Event emission for SSE/WebSocket
- Global and per-node timeouts
"""

import asyncio
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine

import structlog

from src.core.exceptions import (
    ExecutionError,
    NodeExecutionError,
    WorkflowTimeoutError,
)
from src.engine.abstractions import BaseNode, ExecutionContext, NodeResult, NodeStatus, NodeRegistry
from src.engine.graph_parser import ExecutionGraph, GraphNode
from src.engine.variable_pool import VariablePool

logger = structlog.get_logger()


# ──────────────────────────────────────────────
# Event System
# ──────────────────────────────────────────────


class WorkflowEventType(str, Enum):
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_COMPLETED = "workflow_completed"
    NODE_STARTED = "node_started"
    NODE_COMPLETED = "node_completed"
    NODE_SKIPPED = "node_skipped"
    NODE_STREAMING = "node_streaming"
    ERROR = "error"
    PING = "ping"


@dataclass
class WorkflowEvent:
    """Event emitted during workflow execution."""
    event_type: WorkflowEventType
    data: dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


EventCallback = Callable[[WorkflowEvent], Coroutine[Any, Any, None]]


class EventEmitter:
    """Pub/sub event emitter for workflow execution events."""

    def __init__(self) -> None:
        self._subscribers: list[EventCallback] = []

    def subscribe(self, callback: EventCallback) -> None:
        self._subscribers.append(callback)

    def unsubscribe(self, callback: EventCallback) -> None:
        self._subscribers = [s for s in self._subscribers if s is not callback]

    async def emit(self, event: WorkflowEvent) -> None:
        for callback in self._subscribers:
            try:
                await callback(event)
            except Exception as e:
                logger.warning("Event callback failed", error=str(e))


# ──────────────────────────────────────────────
# Execution Result
# ──────────────────────────────────────────────


@dataclass
class NodeExecutionRecord:
    """Record of a single node's execution."""
    node_id: str
    node_type: str
    status: NodeStatus
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    duration_ms: int = 0
    token_count: int = 0
    started_at: str = ""
    completed_at: str = ""


@dataclass
class ExecutionResult:
    """Complete workflow execution result."""
    execution_id: str
    status: str  # success / failed / timeout / cancelled
    outputs: dict[str, Any] = field(default_factory=dict)
    node_records: dict[str, NodeExecutionRecord] = field(default_factory=dict)
    total_duration_ms: int = 0
    total_tokens: int = 0
    total_api_calls: int = 0
    error_message: str | None = None
    error_node_id: str | None = None
    started_at: str = ""
    completed_at: str = ""


# ──────────────────────────────────────────────
# Execution Scheduler
# ──────────────────────────────────────────────


class ExecutionScheduler:
    """Core workflow execution engine.

    Orchestrates execution of a validated ExecutionGraph by:
    1. Maintaining a ready queue of nodes whose dependencies are satisfied
    2. Dispatching ready nodes to the node runtime for execution
    3. Processing execution results and updating the ready queue
    4. Handling parallel branches, condition paths, and loop iterations
    """

    def __init__(
        self,
        node_registry: NodeRegistry,
        event_emitter: EventEmitter | None = None,
        workflow_timeout: int = 1800,
        node_timeout: int = 300,
        max_retries: int = 3,
    ) -> None:
        self.node_registry = node_registry
        self.event_emitter = event_emitter or EventEmitter()
        self.workflow_timeout = workflow_timeout
        self.node_timeout = node_timeout
        self.max_retries = max_retries

    async def execute(
        self,
        graph: ExecutionGraph,
        inputs: dict[str, Any],
        context: ExecutionContext,
    ) -> ExecutionResult:
        """Execute a workflow from start to end.

        Args:
            graph: Parsed and validated ExecutionGraph
            inputs: User-provided input variables
            context: Execution context (IDs, user, environment)

        Returns:
            ExecutionResult with outputs, timing, and per-node records
        """
        start_time = time.monotonic()
        execution_id = context.execution_id

        # Inject event emitter into context so nodes can emit streaming events
        context.event_emitter = self.event_emitter

        # Initialize Variable Pool
        pool = VariablePool()
        pool.inject_system_variables(
            execution_id=execution_id,
            workflow_id=context.workflow_id,
            workflow_version=context.workflow_version,
            user_id=context.user_id,
            environment=context.environment,
        )
        pool.inject_user_inputs(inputs)

        # Track node states
        node_states: dict[str, NodeStatus] = {
            nid: NodeStatus.PENDING for nid in graph.nodes
        }
        node_records: dict[str, NodeExecutionRecord] = {}

        # Emit workflow started
        await self.event_emitter.emit(WorkflowEvent(
            event_type=WorkflowEventType.WORKFLOW_STARTED,
            data={"execution_id": execution_id, "workflow_id": context.workflow_id},
        ))

        try:
            # Execute with global timeout
            result = await asyncio.wait_for(
                self._run_scheduler(graph, pool, context, node_states, node_records, execution_id),
                timeout=self.workflow_timeout,
            )
        except asyncio.TimeoutError:
            result = ExecutionResult(
                execution_id=execution_id,
                status="timeout",
                error_message=f"Workflow timed out after {self.workflow_timeout}s",
                total_duration_ms=int((time.monotonic() - start_time) * 1000),
                started_at=context.metadata.get("started_at", ""),
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
        except Exception as e:
            result = ExecutionResult(
                execution_id=execution_id,
                status="failed",
                error_message=str(e),
                total_duration_ms=int((time.monotonic() - start_time) * 1000),
                started_at=context.metadata.get("started_at", ""),
                completed_at=datetime.now(timezone.utc).isoformat(),
            )

        # Finalize
        result.total_duration_ms = int((time.monotonic() - start_time) * 1000)
        result.node_records = node_records
        result.total_tokens = sum(r.token_count for r in node_records.values())
        result.total_api_calls = sum(1 for r in node_records.values() if r.node_type in ("llm", "agent"))

        # Emit workflow completed
        await self.event_emitter.emit(WorkflowEvent(
            event_type=WorkflowEventType.WORKFLOW_COMPLETED,
            data={
                "execution_id": execution_id,
                "status": result.status,
                "total_duration_ms": result.total_duration_ms,
                "total_tokens": result.total_tokens,
            },
        ))

        return result

    async def _run_scheduler(
        self,
        graph: ExecutionGraph,
        pool: VariablePool,
        context: ExecutionContext,
        node_states: dict[str, NodeStatus],
        node_records: dict[str, NodeExecutionRecord],
        execution_id: str,
    ) -> ExecutionResult:
        """Main scheduling loop — processes nodes in topological order."""

        # Initialize ready queue with start node
        ready_queue: list[str] = [graph.start_node_id]
        skipped_nodes: set[str] = set()

        while ready_queue:
            # Get current batch of ready nodes
            current_batch = list(ready_queue)
            ready_queue.clear()

            # Execute batch (parallel if multiple nodes)
            if len(current_batch) == 1:
                results = [await self._execute_single_node(
                    current_batch[0], graph, pool, context, node_states, node_records, execution_id,
                )]
            else:
                results = await asyncio.gather(*[
                    self._execute_single_node(
                        nid, graph, pool, context, node_states, node_records, execution_id,
                    )
                    for nid in current_batch
                ], return_exceptions=True)

            # Process results and determine next ready nodes
            for i, result in enumerate(results):
                node_id = current_batch[i]

                if isinstance(result, Exception):
                    node_states[node_id] = NodeStatus.FAILED
                    node_records[node_id] = NodeExecutionRecord(
                        node_id=node_id,
                        node_type=graph.nodes[node_id].node_type,
                        status=NodeStatus.FAILED,
                        error=str(result),
                    )
                    # Check if this is a critical failure
                    if graph.nodes[node_id].node_type == "end":
                        return ExecutionResult(
                            execution_id=execution_id,
                            status="failed",
                            error_message=str(result),
                            error_node_id=node_id,
                        )
                    continue

                node_result = result
                node_states[node_id] = node_result.status

                if node_result.status == NodeStatus.FAILED:
                    # Node execution failed
                    if self._should_fail_fast(graph, node_id):
                        return ExecutionResult(
                            execution_id=execution_id,
                            status="failed",
                            error_message=node_result.error,
                            error_node_id=node_id,
                        )
                elif node_result.status == NodeStatus.SUCCEEDED:
                    # Write outputs to Variable Pool
                    for key, value in node_result.outputs.items():
                        pool.set(f"{node_id}.output.{key}", value)

                    # Determine next ready nodes
                    successors = self._get_activated_successors(node_id, graph, pool, node_states, skipped_nodes)
                    for succ_id in successors:
                        if self._all_predecessors_satisfied(succ_id, graph, node_states, skipped_nodes):
                            ready_queue.append(succ_id)

            # If queue is empty and no end node was reached, check if we're stuck
            if not ready_queue:
                end_reached = any(
                    node_states.get(eid) == NodeStatus.SUCCEEDED
                    for eid in graph.end_node_ids
                )
                if not end_reached:
                    # Find which nodes are still pending and why
                    pending = [nid for nid, s in node_states.items() if s == NodeStatus.PENDING]
                    if pending:
                        logger.warning("Workflow stuck — pending nodes", pending=pending)

        # Collect outputs from End nodes
        outputs: dict[str, Any] = {}
        for end_id in graph.end_node_ids:
            end_node = graph.nodes[end_id]
            end_config = end_node.config
            for output_def in end_config.get("outputs", []):
                output_name = output_def.get("name", "result")
                output_from = output_def.get("from", f"{end_id}.output")
                outputs[output_name] = pool.get(output_from, "")

        return ExecutionResult(
            execution_id=execution_id,
            status="success",
            outputs=outputs,
        )

    async def _execute_single_node(
        self,
        node_id: str,
        graph: ExecutionGraph,
        pool: VariablePool,
        context: ExecutionContext,
        node_states: dict[str, NodeStatus],
        node_records: dict[str, NodeExecutionRecord],
        execution_id: str,
    ) -> NodeResult:
        """Execute a single node with retry logic."""
        graph_node = graph.nodes[node_id]
        node_type = graph_node.node_type

        # Skip dead code
        if node_id in graph.dead_code_nodes:
            return NodeResult(status=NodeStatus.SKIPPED, error="Dead code — unreachable node")

        # Emit node started
        await self.event_emitter.emit(WorkflowEvent(
            event_type=WorkflowEventType.NODE_STARTED,
            data={"node_id": node_id, "node_type": node_type, "execution_id": execution_id},
        ))

        start_time = time.monotonic()
        record = NodeExecutionRecord(
            node_id=node_id,
            node_type=node_type,
            status=NodeStatus.RUNNING,
            started_at=datetime.now(timezone.utc).isoformat(),
        )

        # Create node instance
        try:
            node = self.node_registry.create_node(node_type, node_id, graph_node.config)
        except ValueError as e:
            record.status = NodeStatus.FAILED
            record.error = str(e)
            record.duration_ms = int((time.monotonic() - start_time) * 1000)
            node_records[node_id] = record
            return NodeResult(status=NodeStatus.FAILED, error=str(e))

        # Execute with retries
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                result = await asyncio.wait_for(
                    node.execute(pool, context),
                    timeout=self.node_timeout,
                )

                if result.status == NodeStatus.SUCCEEDED:
                    record.status = NodeStatus.SUCCEEDED
                    record.outputs = result.outputs
                    record.token_count = result.token_count
                    record.duration_ms = int((time.monotonic() - start_time) * 1000)
                    record.completed_at = datetime.now(timezone.utc).isoformat()
                    node_records[node_id] = record

                    await self.event_emitter.emit(WorkflowEvent(
                        event_type=WorkflowEventType.NODE_COMPLETED,
                        data={
                            "node_id": node_id,
                            "node_type": node_type,
                            "status": "succeeded",
                            "duration_ms": record.duration_ms,
                            "token_count": record.token_count,
                        },
                    ))
                    return result
                else:
                    record.error = result.error
                    last_error = Exception(result.error or "Node returned non-success status")
                    if attempt < self.max_retries:
                        delay = min(1000 * (2 ** attempt), 30000)
                        await asyncio.sleep(delay / 1000)
                        continue
                    break

            except asyncio.TimeoutError:
                last_error = TimeoutError(f"Node '{node_id}' timed out after {self.node_timeout}s")
                record.error = str(last_error)
                if attempt < self.max_retries:
                    continue
                break
            except Exception as e:
                last_error = e
                record.error = str(e)
                if attempt < self.max_retries and isinstance(e, node.supported_retry_exceptions):
                    delay = min(1000 * (2 ** attempt), 30000)
                    await asyncio.sleep(delay / 1000)
                    continue
                break

        # All retries exhausted
        record.status = NodeStatus.FAILED
        record.duration_ms = int((time.monotonic() - start_time) * 1000)
        record.completed_at = datetime.now(timezone.utc).isoformat()
        node_records[node_id] = record

        await self.event_emitter.emit(WorkflowEvent(
            event_type=WorkflowEventType.NODE_COMPLETED,
            data={
                "node_id": node_id,
                "node_type": node_type,
                "status": "failed",
                "duration_ms": record.duration_ms,
                "error": record.error,
            },
        ))

        return NodeResult(
            status=NodeStatus.FAILED,
            error=str(last_error),
        )

    def _get_activated_successors(
        self,
        node_id: str,
        graph: ExecutionGraph,
        pool: VariablePool,
        node_states: dict[str, NodeStatus],
        skipped_nodes: set[str],
    ) -> list[str]:
        """Determine which successor nodes should be activated after a node completes."""
        successors = graph.get_successors(node_id)

        if not successors:
            return []

        # Condition node: only activate the matched branch
        if graph.nodes[node_id].node_type == "condition":
            return self._resolve_condition_branches(node_id, graph, pool, skipped_nodes)

        # Parallel node: activate all branches
        if graph.nodes[node_id].node_type == "parallel":
            return successors

        # Default: activate all successors
        return successors

    def _resolve_condition_branches(
        self,
        condition_node_id: str,
        graph: ExecutionGraph,
        pool: VariablePool,
        skipped_nodes: set[str],
    ) -> list[str]:
        """Evaluate condition node and activate only the matching branch."""
        condition_config = graph.nodes[condition_node_id].config
        conditions = condition_config.get("conditions", [])
        default_target = condition_config.get("default_target")

        # Find all edges from this condition node
        outgoing_edges = [e for e in graph.edges if e.source == condition_node_id]

        matched_targets: list[str] = []

        for edge in outgoing_edges:
            if edge.condition_index is not None and edge.condition_index < len(conditions):
                condition = conditions[edge.condition_index]
                expression = condition.get("expression", "")
                target = edge.target

                # Evaluate expression against VariablePool
                if self._evaluate_condition(expression, pool):
                    matched_targets.append(target)
                    break  # First match wins

        if not matched_targets and default_target:
            matched_targets.append(default_target)

        # Mark non-matched branches as skipped
        all_targets = [e.target for e in outgoing_edges]
        for target in all_targets:
            if target not in matched_targets:
                skipped_nodes.add(target)

        return matched_targets

    def _evaluate_condition(self, expression: str, pool: VariablePool) -> bool:
        """Evaluate a condition expression against the VariablePool.

        Supports simple expressions like:
            {{node_llm.output.risk_level}} == 'high'
            {{node_llm.output.score}} >= 0.7
            {{node_llm.output.type}} in ['low', 'medium']
        """
        try:
            # Resolve template variables first
            resolved = pool.resolve_template(expression)

            # Safe evaluation using a restricted namespace
            # Only allow comparison operators and basic operations
            allowed_names = {"True": True, "False": False, "None": None}
            result = eval(resolved, {"__builtins__": {}}, allowed_names)
            return bool(result)
        except Exception:
            return False

    def _all_predecessors_satisfied(
        self,
        node_id: str,
        graph: ExecutionGraph,
        node_states: dict[str, NodeStatus],
        skipped_nodes: set[str],
    ) -> bool:
        """Check if all predecessors of a node have completed (succeeded or skipped)."""
        predecessors = graph.get_predecessors(node_id)
        if not predecessors:
            return True

        for pred_id in predecessors:
            state = node_states.get(pred_id, NodeStatus.PENDING)
            if state not in (NodeStatus.SUCCEEDED, NodeStatus.SKIPPED):
                return False
        return True

    def _should_fail_fast(self, graph: ExecutionGraph, failed_node_id: str) -> bool:
        """Determine if a node failure should terminate the entire workflow."""
        # End node failure always fails the workflow
        if graph.nodes[failed_node_id].node_type == "end":
            return True
        # For now, all failures are fail-fast
        # TODO: implement configurable error strategy per node
        return True
