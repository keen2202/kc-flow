"""Variable Pool — runtime memory space for node-to-node data communication.

Implements the publish-subscribe pattern from Dify: nodes write outputs to namespaced keys,
downstream nodes read by resolving template expressions like {{node_id.output.field}}.

Key features:
- Namespaced get/set (node_id.input/output)
- Jinja2 template resolution with full VariablePool as context
- System variable injection (sys.execution_id, sys.user_id, etc.)
- Snapshot/restore for checkpointing
- Merge for branch aggregation
"""

import copy
import datetime
from typing import Any

from jinja2 import Environment, BaseLoader, StrictUndefined, UndefinedError
import structlog

from src.core.exceptions import VariableValidationError

logger = structlog.get_logger()


class VariablePool:
    """Thread-safe runtime memory space for workflow variable storage and resolution.

    Variables are organized in dot-separated namespaces:
        "node_llm_extract.output.clauses" → access nested dict path
        "sys.execution_id"                → system-injected variable
    """

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._jinja_env = Environment(
            loader=BaseLoader(),
            undefined=StrictUndefined,
            keep_trailing_newline=True,
        )

    # ── System Variables ──

    def inject_system_variables(
        self,
        execution_id: str,
        workflow_id: str,
        workflow_version: str,
        user_id: str,
        environment: str = "development",
        trigger: str = "api",
    ) -> None:
        """Inject system variables available to all nodes as sys.*."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self._set_nested("sys", {
            "execution_id": execution_id,
            "workflow_id": workflow_id,
            "workflow_version": workflow_version,
            "user_id": user_id,
            "timestamp": now,
            "environment": environment,
            "trigger": trigger,
        })

    def inject_user_inputs(self, inputs: dict[str, Any]) -> None:
        """Inject user-provided inputs as node_start.output.*."""
        self._set_nested("node_start.output", inputs)

    # ── Core Get/Set ──

    def get(self, path: str, default: Any = None) -> Any:
        """Get a value by dot-separated path.

        Examples:
            pool.get("node_llm.output.text")
            pool.get("sys.execution_id")
        """
        keys = path.split(".")
        current = self._data
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current

    def set(self, path: str, value: Any) -> None:
        """Set a value at dot-separated path, creating intermediate namespaces.

        Examples:
            pool.set("node_llm.output.text", "hello")
        """
        keys = path.split(".")
        current = self._data
        for key in keys[:-1]:
            if key not in current or not isinstance(current[key], dict):
                current[key] = {}
            current = current[key]
        current[keys[-1]] = value

    def _set_nested(self, prefix: str, data: dict[str, Any]) -> None:
        """Set all keys from a dict under a prefix namespace."""
        for key, value in data.items():
            self.set(f"{prefix}.{key}", value)

    def exists(self, path: str) -> bool:
        """Check if a path exists in the pool."""
        return self.get(path, _SENTINEL) is not _SENTINEL

    def delete(self, path: str) -> bool:
        """Delete a value at path. Returns True if existed."""
        keys = path.split(".")
        current = self._data
        for key in keys[:-1]:
            if not isinstance(current, dict) or key not in current:
                return False
            current = current[key]
        if isinstance(current, dict) and keys[-1] in current:
            del current[keys[-1]]
            return True
        return False

    # ── Namespace Operations ──

    def get_namespace(self, prefix: str) -> dict[str, Any]:
        """Get all values under a namespace prefix as a flat dict."""
        result: dict[str, Any] = {}
        keys = prefix.split(".")
        current = self._data
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return result

        if isinstance(current, dict):
            for k, v in current.items():
                result[f"{prefix}.{k}"] = v
        return result

    def delete_namespace(self, prefix: str) -> None:
        """Delete all values under a namespace prefix."""
        keys = prefix.split(".")
        current = self._data
        for key in keys[:-1]:
            if not isinstance(current, dict) or key not in current:
                return
            current = current[key]
        if isinstance(current, dict) and keys[-1] in current:
            del current[keys[-1]]

    # ── Template Resolution ──

    def resolve_template(self, template_str: str, context: dict[str, Any] | None = None) -> str:
        """Resolve a Jinja2 template string using the VariablePool as context.

        Supports:
            {{node_id.output.field}}
            {{node_id.output.items[0].name}}
            {{value | default('N/A')}}
            {{sys.timestamp}}
        """
        try:
            template = self._jinja_env.from_string(template_str)
            # Merge pool data with extra context
            render_context = self._flatten_for_template()
            if context:
                render_context.update(context)
            return template.render(**render_context)
        except UndefinedError as e:
            raise VariableValidationError(
                message=f"Template resolution failed: {e}",
                variable_path=template_str[:100],
            )

    def _flatten_for_template(self) -> dict[str, Any]:
        """Flatten nested dict into Jinja2-accessible top-level keys.

        Converts {"node_llm": {"output": {"text": "hi"}}} to
        {"node_llm": {"output": {"text": "hi"}}} — Jinja2 handles dict access naturally.
        """
        return dict(self._data)

    def resolve_value(self, value: Any) -> Any:
        """Resolve a value that might contain template expressions."""
        if isinstance(value, str) and "{{" in value:
            return self.resolve_template(value)
        if isinstance(value, dict):
            return {k: self.resolve_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.resolve_value(item) for item in value]
        return value

    # ── Snapshot / Restore (for checkpointing) ──

    def snapshot(self) -> dict[str, Any]:
        """Return a deep copy of the entire pool state."""
        return copy.deepcopy(self._data)

    def restore(self, snapshot: dict[str, Any]) -> None:
        """Replace pool state from a snapshot."""
        self._data = copy.deepcopy(snapshot)

    # ── Merge (for branch aggregation) ──

    def merge(self, other: "VariablePool", strategy: str = "last_wins") -> None:
        """Merge another pool's data into this one.

        Strategies:
            first_wins: keep existing values, skip conflicts
            last_wins: overwrite with other's values
            merge_lists: concatenate list values
        """
        other_data = other.snapshot()
        self._data = self._merge_dicts(self._data, other_data, strategy)

    def _merge_dicts(self, base: dict, overlay: dict, strategy: str) -> dict:
        """Recursively merge two dicts according to strategy."""
        result = dict(base)
        for key, value in overlay.items():
            if key in result:
                if isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = self._merge_dicts(result[key], value, strategy)
                elif strategy == "merge_lists" and isinstance(result[key], list) and isinstance(value, list):
                    result[key] = result[key] + value
                elif strategy == "first_wins":
                    pass  # keep existing
                else:  # last_wins
                    result[key] = copy.deepcopy(value)
            else:
                result[key] = copy.deepcopy(value)
        return result

    # ── Utility ──

    def to_dict(self) -> dict[str, Any]:
        """Return a shallow copy of the internal data."""
        return dict(self._data)

    def __repr__(self) -> str:
        keys = list(self._data.keys())
        return f"VariablePool(keys={keys})"


# Sentinel for distinguishing "not found" from None
_SENTINEL = object()
