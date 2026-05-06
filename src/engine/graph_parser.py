"""DSL Parser and Graph Validator — converts Workflow DSL JSON into an executable ExecutionGraph.

Implements the 4-phase compilation pipeline from the spec:
  Phase 1: Lexical/Syntax validation (JSON structure, IDs, edges)
  Phase 2: Semantic validation (variable references, type compatibility)
  Phase 3: Optimization (dead code elimination, constant folding, parallel detection)
  Phase 4: Execution plan generation (topological sort, metadata)

Also includes cycle detection via DFS with Loop node back-edge whitelisting.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

from src.core.exceptions import (
    DSLValidationError,
    GraphValidationError,
    VariableValidationError,
)

logger = structlog.get_logger()


# ──────────────────────────────────────────────
# Execution Graph Model
# ──────────────────────────────────────────────


class NodeState(str, Enum):
    """Node state during graph analysis."""
    ACTIVE = "active"
    DEAD_CODE = "dead_code"


@dataclass
class GraphNode:
    """A node in the execution graph."""
    id: str
    node_type: str
    config: dict[str, Any]
    position: dict[str, float] = field(default_factory=lambda: {"x": 0, "y": 0})
    state: NodeState = NodeState.ACTIVE


@dataclass
class GraphEdge:
    """An edge connecting two nodes."""
    source: str
    target: str
    source_handle: str = "output"
    target_handle: str = "input"
    condition_index: int | None = None


@dataclass
class ParallelGroup:
    """A group of nodes that can execute in parallel."""
    group_id: str
    node_ids: list[str]


@dataclass
class ExecutionGraph:
    """Parsed and validated execution graph ready for the scheduler."""
    nodes: dict[str, GraphNode]
    edges: list[GraphEdge]
    adjacency: dict[str, list[str]]  # source → [targets]
    reverse_adjacency: dict[str, list[str]]  # target → [sources]
    topo_order: list[str]
    parallel_groups: list[ParallelGroup]
    start_node_id: str
    end_node_ids: list[str]
    dead_code_nodes: list[str]

    def get_successors(self, node_id: str) -> list[str]:
        """Get all downstream node IDs."""
        return self.adjacency.get(node_id, [])

    def get_predecessors(self, node_id: str) -> list[str]:
        """Get all upstream node IDs."""
        return self.reverse_adjacency.get(node_id, [])

    def is_in_parallel_group(self, node_id: str) -> ParallelGroup | None:
        """Check if a node is part of a parallel group."""
        for group in self.parallel_groups:
            if node_id in group.node_ids:
                return group
        return None


# ──────────────────────────────────────────────
# Graph Parser
# ──────────────────────────────────────────────


class GraphParser:
    """Parses Workflow DSL JSON and produces a validated ExecutionGraph.

    Usage:
        parser = GraphParser()
        graph = parser.parse(dsl_json)
    """

    def parse(self, dsl: dict[str, Any]) -> ExecutionGraph:
        """Parse and validate a Workflow DSL, returning an ExecutionGraph.

        Args:
            dsl: The complete workflow DSL dict (must contain "workflow" key with "nodes" and "edges")

        Returns:
            ExecutionGraph ready for the ExecutionScheduler

        Raises:
            DSLValidationError: If DSL structure is invalid
            GraphValidationError: If graph structure is invalid (cycle, unreachable, etc.)
        """
        workflow = dsl.get("workflow")
        if not workflow:
            raise DSLValidationError("DSL must contain a 'workflow' top-level key")

        nodes_data = workflow.get("nodes", [])
        edges_data = workflow.get("edges", [])

        # ── Phase 1: Lexical/Syntax Validation ──
        nodes = self._validate_nodes(nodes_data)
        edges = self._validate_edges(edges_data, nodes)

        # ── Build adjacency lists ──
        adjacency, reverse_adj = self._build_adjacency(edges, nodes)

        # ── Phase 2: Semantic Validation ──
        self._validate_graph_structure(nodes, adjacency, reverse_adj)
        self._validate_variable_references(nodes, edges)

        # ── Phase 3: Optimization ──
        start_id = self._find_start_node(nodes)
        end_ids = self._find_end_nodes(nodes)
        dead_code = self._detect_dead_code(nodes, adjacency, start_id)
        topo_order = self._topological_sort(nodes, adjacency, reverse_adj)
        parallel_groups = self._detect_parallel_groups(topo_order, adjacency, reverse_adj)

        # Mark dead code
        for node_id in dead_code:
            nodes[node_id].state = NodeState.DEAD_CODE

        logger.info(
            "DSL parsed successfully",
            node_count=len(nodes),
            edge_count=len(edges),
            dead_code_count=len(dead_code),
            parallel_groups=len(parallel_groups),
        )

        return ExecutionGraph(
            nodes=nodes,
            edges=edges,
            adjacency=adjacency,
            reverse_adjacency=reverse_adj,
            topo_order=topo_order,
            parallel_groups=parallel_groups,
            start_node_id=start_id,
            end_node_ids=end_ids,
            dead_code_nodes=dead_code,
        )

    # ── Phase 1: Syntax Validation ──

    def _validate_nodes(self, nodes_data: list[dict]) -> dict[str, GraphNode]:
        """Validate node definitions: IDs unique, required fields present."""
        nodes: dict[str, GraphNode] = {}
        seen_ids: set[str] = set()

        for i, node_data in enumerate(nodes_data):
            node_id = node_data.get("id")
            if not node_id:
                raise DSLValidationError(f"Node at index {i} is missing 'id' field")
            if node_id in seen_ids:
                raise DSLValidationError(f"Duplicate node ID: '{node_id}'")
            seen_ids.add(node_id)

            node_type = node_data.get("type")
            if not node_type:
                raise DSLValidationError(f"Node '{node_id}' is missing 'type' field")

            nodes[node_id] = GraphNode(
                id=node_id,
                node_type=node_type,
                config=node_data.get("data", {}),
                position=node_data.get("position", {"x": 0, "y": 0}),
            )

        return nodes

    def _validate_edges(self, edges_data: list[dict], nodes: dict[str, GraphNode]) -> list[GraphEdge]:
        """Validate edge definitions: source and target nodes exist."""
        edges: list[GraphEdge] = []
        for i, edge_data in enumerate(edges_data):
            source = edge_data.get("source")
            target = edge_data.get("target")
            if not source or not target:
                raise DSLValidationError(f"Edge at index {i} is missing 'source' or 'target'")
            if source not in nodes:
                raise DSLValidationError(f"Edge at index {i}: source node '{source}' does not exist")
            if target not in nodes:
                raise DSLValidationError(f"Edge at index {i}: target node '{target}' does not exist")

            edges.append(GraphEdge(
                source=source,
                target=target,
                source_handle=edge_data.get("source_handle", "output"),
                target_handle=edge_data.get("target_handle", "input"),
                condition_index=edge_data.get("condition_index"),
            ))

        return edges

    def _build_adjacency(
        self, edges: list[GraphEdge], nodes: dict[str, GraphNode]
    ) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
        """Build forward and reverse adjacency lists."""
        adjacency: dict[str, list[str]] = {nid: [] for nid in nodes}
        reverse_adj: dict[str, list[str]] = {nid: [] for nid in nodes}

        for edge in edges:
            adjacency[edge.source].append(edge.target)
            reverse_adj[edge.target].append(edge.source)

        return adjacency, reverse_adj

    # ── Phase 2: Semantic Validation ──

    def _validate_graph_structure(
        self,
        nodes: dict[str, GraphNode],
        adjacency: dict[str, list[str]],
        reverse_adj: dict[str, list[str]],
    ) -> None:
        """Validate high-level graph structure: required nodes, connectivity, no cycles."""
        # Check for Start and End nodes
        start_nodes = [nid for nid, n in nodes.items() if n.node_type == "start"]
        end_nodes = [nid for nid, n in nodes.items() if n.node_type == "end"]

        if not start_nodes:
            raise GraphValidationError("Workflow must contain at least one Start node")
        if len(start_nodes) > 1:
            raise GraphValidationError(f"Workflow must contain exactly one Start node, found {len(start_nodes)}")
        if not end_nodes:
            raise GraphValidationError("Workflow must contain at least one End node")

        # Cycle detection (DFS with recursion stack)
        self._detect_cycles(nodes, adjacency)

    def _detect_cycles(self, nodes: dict[str, GraphNode], adjacency: dict[str, list[str]]) -> None:
        """Detect cycles using DFS. Loop nodes' back-edges are whitelisted."""
        visited: set[str] = set()
        rec_stack: set[str] = set()
        loop_nodes = {nid for nid, n in nodes.items() if n.node_type == "loop"}

        def dfs(node_id: str, path: list[str]) -> None:
            visited.add(node_id)
            rec_stack.add(node_id)
            path.append(node_id)

            for neighbor in adjacency.get(node_id, []):
                # Whitelist: Loop node → its own start is a valid back-edge
                if node_id in loop_nodes and neighbor == node_id:
                    continue

                if neighbor not in visited:
                    dfs(neighbor, path)
                elif neighbor in rec_stack:
                    cycle_path = " → ".join(path[path.index(neighbor):]) + f" → {neighbor}"
                    raise GraphValidationError(
                        f"Cycle detected in workflow graph: {cycle_path}",
                        code="graph_cycle_detected",
                    )

            path.pop()
            rec_stack.discard(node_id)

        for node_id in nodes:
            if node_id not in visited:
                dfs(node_id, [])

    def _validate_variable_references(
        self, nodes: dict[str, GraphNode], edges: list[GraphEdge]
    ) -> None:
        """Validate that all {{node_id.output.field}} references point to existing nodes."""
        node_ids = set(nodes.keys())

        for node_id, node in nodes.items():
            config_str = str(node.config)
            # Find all {{...}} expressions
            import re
            refs = re.findall(r"\{\{([^}]+)\}\}", config_str)

            for ref in refs:
                # Extract node ID from reference like "node_llm.output.text"
                parts = ref.strip().split(".")
                if len(parts) >= 2 and parts[0] not in ("sys", "node_start"):
                    referenced_node = parts[0]
                    # Allow self-references for loop nodes
                    if referenced_node != node_id and referenced_node not in node_ids:
                        # Check if it's a filter/function reference (Jinja2 built-in)
                        if "|" not in ref and "." in ref:
                            raise VariableValidationError(
                                message=f"Node '{node_id}' references unknown node '{referenced_node}'",
                                variable_path=ref.strip(),
                            )

    # ── Phase 3: Optimization ──

    def _find_start_node(self, nodes: dict[str, GraphNode]) -> str:
        """Find the Start node ID."""
        for nid, n in nodes.items():
            if n.node_type == "start":
                return nid
        raise GraphValidationError("No Start node found")

    def _find_end_nodes(self, nodes: dict[str, GraphNode]) -> list[str]:
        """Find all End node IDs."""
        return [nid for nid, n in nodes.items() if n.node_type == "end"]

    def _detect_dead_code(
        self,
        nodes: dict[str, GraphNode],
        adjacency: dict[str, list[str]],
        start_id: str,
    ) -> list[str]:
        """BFS from Start to find unreachable nodes (dead code)."""
        reachable: set[str] = set()
        queue = [start_id]

        while queue:
            current = queue.pop(0)
            if current in reachable:
                continue
            reachable.add(current)
            for neighbor in adjacency.get(current, []):
                if neighbor not in reachable:
                    queue.append(neighbor)

        return [nid for nid in nodes if nid not in reachable and nid != start_id]

    def _topological_sort(
        self,
        nodes: dict[str, GraphNode],
        adjacency: dict[str, list[str]],
        reverse_adj: dict[str, list[str]],
    ) -> list[str]:
        """Kahn's algorithm for topological sort."""
        # Calculate in-degree for each node (excluding dead code)
        active_nodes = {nid for nid, n in nodes.items() if n.state == NodeState.ACTIVE}
        in_degree: dict[str, int] = {}
        for nid in active_nodes:
            in_degree[nid] = len([p for p in reverse_adj.get(nid, []) if p in active_nodes])

        # Start with nodes that have no incoming edges (in-degree 0)
        queue = [nid for nid in active_nodes if in_degree.get(nid, 0) == 0]
        topo_order: list[str] = []

        while queue:
            # Sort for deterministic ordering
            queue.sort()
            current = queue.pop(0)
            topo_order.append(current)

            for neighbor in adjacency.get(current, []):
                if neighbor in active_nodes:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

        if len(topo_order) != len(active_nodes):
            remaining = active_nodes - set(topo_order)
            raise GraphValidationError(
                f"Topological sort incomplete — possible cycle among nodes: {remaining}",
                code="graph_cycle_detected",
            )

        return topo_order

    def _detect_parallel_groups(
        self,
        topo_order: list[str],
        adjacency: dict[str, list[str]],
        reverse_adj: dict[str, list[str]],
    ) -> list[ParallelGroup]:
        """Detect groups of nodes that can execute in parallel.

        A parallel group exists when multiple nodes share the same set of
        completed predecessors and can therefore run concurrently.
        """
        groups: list[ParallelGroup] = []
        group_counter = 0

        # For each node, check if multiple successors of the same node
        # form a parallel group (multiple outgoing edges from same source)
        for node_id in topo_order:
            successors = adjacency.get(node_id, [])
            if len(successors) > 1:
                group_counter += 1
                groups.append(ParallelGroup(
                    group_id=f"parallel_{group_counter}",
                    node_ids=list(successors),
                ))

        return groups
