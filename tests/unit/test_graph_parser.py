"""Unit tests for GraphParser and ExecutionGraph."""

import pytest
from src.engine.graph_parser import GraphParser, ExecutionGraph
from src.core.exceptions import DSLValidationError, GraphValidationError


class TestGraphParser:
    """Test DSL parsing and graph validation."""

    def _make_dsl(self, nodes=None, edges="default"):
        """Helper to create a minimal valid DSL.

        edges defaults to connecting start→end. Pass edges=[] to suppress,
        or edges=[...] for explicit edges. Pass edges="auto" to only
        generate edges for node IDs that actually exist.
        """
        if nodes is None:
            nodes = [
                {"id": "node_start", "type": "start", "data": {}},
                {"id": "node_end", "type": "end", "data": {}},
            ]
        if edges == "default":
            edges = [{"source": "node_start", "target": "node_end"}]
        elif edges == "auto":
            node_ids = {n["id"] for n in nodes}
            default_edge = {"source": "node_start", "target": "node_end"}
            if default_edge["source"] in node_ids and default_edge["target"] in node_ids:
                edges = [default_edge]
            else:
                edges = []
        return {"workflow": {"nodes": nodes, "edges": edges}}

    def test_parse_simple_dsl(self):
        parser = GraphParser()
        dsl = self._make_dsl()
        graph = parser.parse(dsl)

        assert isinstance(graph, ExecutionGraph)
        assert graph.start_node_id == "node_start"
        assert "node_end" in graph.end_node_ids
        assert len(graph.nodes) == 2
        assert len(graph.edges) == 1

    def test_parse_missing_workflow_key(self):
        parser = GraphParser()
        with pytest.raises(DSLValidationError, match="workflow"):
            parser.parse({"not_workflow": {}})

    def test_parse_duplicate_node_ids(self):
        parser = GraphParser()
        dsl = self._make_dsl(nodes=[
            {"id": "node_start", "type": "start"},
            {"id": "node_start", "type": "end"},
        ])
        with pytest.raises(DSLValidationError, match="Duplicate"):
            parser.parse(dsl)

    def test_parse_missing_node_type(self):
        parser = GraphParser()
        dsl = self._make_dsl(nodes=[{"id": "node_1"}])
        with pytest.raises(DSLValidationError, match="type"):
            parser.parse(dsl)

    def test_parse_edge_missing_source(self):
        parser = GraphParser()
        dsl = self._make_dsl(edges=[{"target": "node_end"}])
        with pytest.raises(DSLValidationError, match="source"):
            parser.parse(dsl)

    def test_parse_no_start_node(self):
        parser = GraphParser()
        dsl = self._make_dsl(
            nodes=[{"id": "node_end", "type": "end"}],
            edges=[],
        )
        with pytest.raises(GraphValidationError, match="Start"):
            parser.parse(dsl)

    def test_parse_no_end_node(self):
        parser = GraphParser()
        dsl = self._make_dsl(
            nodes=[{"id": "node_start", "type": "start"}],
            edges=[],
        )
        with pytest.raises(GraphValidationError, match="End"):
            parser.parse(dsl)

    def test_cycle_detection(self):
        parser = GraphParser()
        dsl = self._make_dsl(
            nodes=[
                {"id": "node_start", "type": "start"},
                {"id": "node_a", "type": "code"},
                {"id": "node_end", "type": "end"},
            ],
            edges=[
                {"source": "node_start", "target": "node_a"},
                {"source": "node_a", "target": "node_a"},  # self-loop (non-loop node)
                {"source": "node_a", "target": "node_end"},
            ],
        )
        with pytest.raises(GraphValidationError, match="Cycle"):
            parser.parse(dsl)

    def test_topological_sort(self):
        parser = GraphParser()
        dsl = self._make_dsl(
            nodes=[
                {"id": "node_start", "type": "start"},
                {"id": "node_a", "type": "code"},
                {"id": "node_b", "type": "code"},
                {"id": "node_end", "type": "end"},
            ],
            edges=[
                {"source": "node_start", "target": "node_a"},
                {"source": "node_start", "target": "node_b"},
                {"source": "node_a", "target": "node_end"},
                {"source": "node_b", "target": "node_end"},
            ],
        )
        graph = parser.parse(dsl)

        assert graph.topo_order[0] == "node_start"
        assert graph.topo_order[-1] == "node_end"
        assert "node_a" in graph.topo_order
        assert "node_b" in graph.topo_order

    def test_parallel_groups(self):
        parser = GraphParser()
        dsl = self._make_dsl(
            nodes=[
                {"id": "node_start", "type": "start"},
                {"id": "node_a", "type": "code"},
                {"id": "node_b", "type": "code"},
                {"id": "node_end", "type": "end"},
            ],
            edges=[
                {"source": "node_start", "target": "node_a"},
                {"source": "node_start", "target": "node_b"},
                {"source": "node_a", "target": "node_end"},
                {"source": "node_b", "target": "node_end"},
            ],
        )
        graph = parser.parse(dsl)
        assert len(graph.parallel_groups) > 0

    def test_dead_code_detection(self):
        parser = GraphParser()
        dsl = self._make_dsl(
            nodes=[
                {"id": "node_start", "type": "start"},
                {"id": "node_end", "type": "end"},
                {"id": "node_dead", "type": "code"},
            ],
            edges=[
                {"source": "node_start", "target": "node_end"},
            ],
        )
        graph = parser.parse(dsl)
        assert "node_dead" in graph.dead_code_nodes

    def test_get_successors_and_predecessors(self):
        parser = GraphParser()
        dsl = self._make_dsl(
            nodes=[
                {"id": "node_start", "type": "start"},
                {"id": "node_a", "type": "code"},
                {"id": "node_end", "type": "end"},
            ],
            edges=[
                {"source": "node_start", "target": "node_a"},
                {"source": "node_a", "target": "node_end"},
            ],
        )
        graph = parser.parse(dsl)

        assert graph.get_successors("node_start") == ["node_a"]
        assert graph.get_predecessors("node_end") == ["node_a"]
        assert graph.get_successors("node_end") == []
