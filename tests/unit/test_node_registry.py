"""Unit tests for NodeRegistry and @register_node decorator."""

import pytest
from src.engine.abstractions import (
    BaseNode,
    ExecutionContext,
    NodeCategory,
    NodeConfig,
    NodeRegistry,
    NodeResult,
    NodeStatus,
    VariableDef,
    register_node,
)


class TestNodeRegistry:
    """Test node registration, creation, and listing."""

    def setup_method(self):
        NodeRegistry._reset()

    def test_register_node(self):
        registry = NodeRegistry()

        @register_node(
            node_type="test_node",
            display_name="Test Node",
            category=NodeCategory.DATA,
        )
        class TestNode(BaseNode):
            async def execute(self, variable_pool, context=None):
                return NodeResult(status=NodeStatus.SUCCEEDED)

        assert registry.has_node("test_node")
        assert len(registry) == 1

    def test_create_node(self):
        registry = NodeRegistry()

        @register_node(
            node_type="test_create",
            display_name="Test Create",
            category=NodeCategory.DATA,
        )
        class TestNode(BaseNode):
            async def execute(self, variable_pool, context=None):
                return NodeResult(status=NodeStatus.SUCCEEDED)

        node = registry.create_node("test_create", "node_1", {"key": "value"})
        assert node.node_id == "node_1"
        assert node.node_config == {"key": "value"}

    def test_create_unknown_node_raises(self):
        registry = NodeRegistry()
        with pytest.raises(ValueError, match="Unknown node type"):
            registry.create_node("nonexistent", "node_1", {})

    def test_list_nodes_by_category(self):
        registry = NodeRegistry()

        @register_node(node_type="ctrl_node", display_name="Ctrl", category=NodeCategory.CONTROL)
        class CtrlNode(BaseNode):
            async def execute(self, variable_pool, context=None):
                return NodeResult(status=NodeStatus.SUCCEEDED)

        @register_node(node_type="ai_node", display_name="AI", category=NodeCategory.AI)
        class AINode(BaseNode):
            async def execute(self, variable_pool, context=None):
                return NodeResult(status=NodeStatus.SUCCEEDED)

        all_nodes = registry.list_nodes()
        assert len(all_nodes) == 2

        ctrl_nodes = registry.list_nodes(category=NodeCategory.CONTROL)
        assert len(ctrl_nodes) == 1
        assert ctrl_nodes[0].node_type == "ctrl_node"

    def test_unregister_node(self):
        registry = NodeRegistry()

        @register_node(node_type="to_remove", display_name="Remove", category=NodeCategory.DATA)
        class RemoveNode(BaseNode):
            async def execute(self, variable_pool, context=None):
                return NodeResult(status=NodeStatus.SUCCEEDED)

        assert registry.has_node("to_remove")
        registry.unregister("to_remove")
        assert not registry.has_node("to_remove")

    def test_get_node_config(self):
        registry = NodeRegistry()

        @register_node(
            node_type="configured",
            display_name="Configured",
            category=NodeCategory.AI,
            description="A configured node",
            inputs=[VariableDef(name="prompt", type="string", required=True)],
            outputs=[VariableDef(name="text", type="string")],
        )
        class ConfiguredNode(BaseNode):
            async def execute(self, variable_pool, context=None):
                return NodeResult(status=NodeStatus.SUCCEEDED)

        config = registry.get_node_config("configured")
        assert config is not None
        assert config.display_name == "Configured"
        assert len(config.inputs) == 1
        assert config.inputs[0].name == "prompt"

    def test_duplicate_registration_overwrites(self):
        registry = NodeRegistry()

        @register_node(node_type="dup", display_name="First", category=NodeCategory.DATA)
        class FirstNode(BaseNode):
            async def execute(self, variable_pool, context=None):
                return NodeResult(status=NodeStatus.SUCCEEDED)

        @register_node(node_type="dup", display_name="Second", category=NodeCategory.DATA)
        class SecondNode(BaseNode):
            async def execute(self, variable_pool, context=None):
                return NodeResult(status=NodeStatus.SUCCEEDED)

        config = registry.get_node_config("dup")
        assert config.display_name == "Second"
