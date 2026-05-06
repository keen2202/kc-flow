"""Core node abstractions: BaseNode, NodeConfig, NodeResult, NodeRegistry, @register_node.

This module defines the foundational types for the workflow engine's node system.
All node implementations (control flow, AI, data processing) must extend BaseNode
and register via the @register_node decorator.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────


class NodeCategory(str, Enum):
    """Node type categories for palette grouping."""
    CONTROL = "control"
    AI = "ai"
    DATA = "data"
    INTEGRATION = "integration"


class NodeStatus(str, Enum):
    """Node execution lifecycle states."""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    TIMEOUT = "timeout"


# ──────────────────────────────────────────────
# Pydantic Models
# ──────────────────────────────────────────────


class VariableDef(BaseModel):
    """Variable definition for node inputs/outputs."""
    name: str
    type: str  # string / number / boolean / object / array / any
    required: bool = False
    default: Any = None
    description: str = ""


class NodeConfig(BaseModel):
    """Node type metadata and schema — attached to each node class via @register_node."""
    node_type: str = Field(..., description="Unique node type identifier (e.g. 'llm', 'condition')")
    display_name: str = Field(..., description="Human-readable name")
    description: str = Field("", description="Node functionality description")
    icon: str = Field("default", description="Icon identifier for the canvas")
    category: NodeCategory = Field(..., description="Category for palette grouping")
    inputs: list[VariableDef] = Field(default_factory=list)
    outputs: list[VariableDef] = Field(default_factory=list)
    config_schema: dict[str, Any] = Field(default_factory=dict, description="JSON Schema for node configuration parameters")
    version: str = Field("1.0.0")
    author: str = Field("")
    tags: list[str] = Field(default_factory=list)


class NodeResult(BaseModel):
    """Node execution result — returned by BaseNode.execute()."""
    status: NodeStatus
    outputs: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    duration_ms: int = 0
    token_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionContext(BaseModel):
    """Runtime context passed to nodes during execution."""
    execution_id: str
    workflow_id: str
    workflow_version: str
    user_id: str
    environment: str
    trace_enabled: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    event_emitter: Any = Field(default=None, exclude=True)

    model_config = {"arbitrary_types_allowed": True}


# ──────────────────────────────────────────────
# BaseNode
# ──────────────────────────────────────────────


class BaseNode(ABC):
    """Abstract base class for all workflow node implementations.

    Subclasses MUST:
    1. Define a `config` class attribute (NodeConfig) — typically via @register_node
    2. Implement `execute(variable_pool)` returning a NodeResult
    """

    config: NodeConfig

    def __init__(self, node_id: str, node_config: dict[str, Any]) -> None:
        self.node_id = node_id
        self.node_config = node_config

    @abstractmethod
    async def execute(self, variable_pool: Any, context: ExecutionContext | None = None) -> NodeResult:
        """Execute node logic and return result. Must be overridden."""
        ...

    async def pre_execute(self, variable_pool: Any, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Hook called before execute(). Default: no-op. Override for input validation/preparation."""
        return {}

    async def post_execute(self, variable_pool: Any, result: NodeResult, context: ExecutionContext | None = None) -> NodeResult:
        """Hook called after execute(). Default: pass-through. Override for output transformation."""
        return result

    def validate_inputs(self, inputs: dict[str, Any]) -> list[str]:
        """Validate inputs against node's input definitions. Returns list of error messages."""
        errors: list[str] = []
        for var_def in self.config.inputs:
            if var_def.required and var_def.name not in inputs:
                errors.append(f"Missing required input: '{var_def.name}' ({var_def.description})")
        return errors

    @property
    def supported_retry_exceptions(self) -> tuple[type[Exception], ...]:
        """Exception types that trigger retry. Override for node-specific retryable exceptions."""
        return (TimeoutError, ConnectionError)


# ──────────────────────────────────────────────
# NodeRegistry (Singleton)
# ──────────────────────────────────────────────


class NodeRegistry:
    """Global singleton registry for all node types.

    Usage:
        registry = NodeRegistry()
        registry.register(MyNode)              # explicit registration
        # OR use @register_node decorator     # decorator registration
        node = registry.create_node("llm", "node_1", {"model": "gpt-4o"})
    """

    _instance: Optional["NodeRegistry"] = None
    _registry: dict[str, type[BaseNode]] = {}

    def __new__(cls) -> "NodeRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def _reset(cls) -> None:
        """Reset singleton — for testing only. Clears all registrations."""
        cls._registry.clear()
        cls._instance = None

    def register(self, node_class: type[BaseNode]) -> type[BaseNode]:
        """Register a node class. Extracts config from the class."""
        config = getattr(node_class, "config", None)
        if config is None:
            raise ValueError(f"Node class '{node_class.__name__}' must define a 'config' class attribute")
        if not isinstance(config, NodeConfig):
            raise TypeError(f"'config' on '{node_class.__name__}' must be a NodeConfig instance")
        self._registry[config.node_type] = node_class
        return node_class

    def unregister(self, node_type: str) -> None:
        """Remove a node type from the registry."""
        self._registry.pop(node_type, None)

    def create_node(self, node_type: str, node_id: str, node_config: dict[str, Any]) -> BaseNode:
        """Factory: instantiate a registered node type."""
        node_class = self._registry.get(node_type)
        if node_class is None:
            available = list(self._registry.keys())
            raise ValueError(f"Unknown node type: '{node_type}'. Available: {available}")
        return node_class(node_id=node_id, node_config=node_config)

    def list_nodes(self, category: NodeCategory | None = None) -> list[NodeConfig]:
        """List all registered node configs, optionally filtered by category."""
        configs = []
        for node_cls in self._registry.values():
            config = getattr(node_cls, "config", None)
            if config and (category is None or config.category == category):
                configs.append(config)
        return configs

    def get_node_config(self, node_type: str) -> NodeConfig | None:
        """Get config for a specific node type."""
        node_class = self._registry.get(node_type)
        if node_class is None:
            return None
        return getattr(node_class, "config", None)

    def has_node(self, node_type: str) -> bool:
        """Check if a node type is registered."""
        return node_type in self._registry

    def __len__(self) -> int:
        return len(self._registry)

    def __contains__(self, node_type: str) -> bool:
        return node_type in self._registry


# Global singleton
node_registry = NodeRegistry()


# ──────────────────────────────────────────────
# @register_node Decorator
# ──────────────────────────────────────────────


def register_node(
    *,
    node_type: str,
    display_name: str,
    category: NodeCategory,
    icon: str = "default",
    description: str = "",
    version: str = "1.0.0",
    author: str = "",
    tags: list[str] | None = None,
    inputs: list[VariableDef] | None = None,
    outputs: list[VariableDef] | None = None,
    config_schema: dict[str, Any] | None = None,
) -> Any:
    """Class decorator that attaches NodeConfig and registers with the global registry.

    Usage:
        @register_node(
            node_type="llm",
            display_name="大模型推理",
            category=NodeCategory.AI,
            icon="brain",
            inputs=[VariableDef(name="prompt", type="string", required=True)],
            outputs=[VariableDef(name="text", type="string")],
        )
        class LLMNode(BaseNode):
            async def execute(self, variable_pool, context=None):
                ...
    """

    def decorator(cls: type[BaseNode]) -> type[BaseNode]:
        cls.config = NodeConfig(
            node_type=node_type,
            display_name=display_name,
            description=description,
            icon=icon,
            category=category,
            inputs=inputs or [],
            outputs=outputs or [],
            config_schema=config_schema or {},
            version=version,
            author=author,
            tags=tags or [],
        )
        node_registry._registry[node_type] = cls
        return cls

    return decorator
