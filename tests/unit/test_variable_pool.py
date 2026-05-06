"""Unit tests for VariablePool."""

import pytest
from src.engine.variable_pool import VariablePool


class TestVariablePool:
    """Test VariablePool get/set, template resolution, snapshot/restore."""

    def test_set_and_get(self):
        pool = VariablePool()
        pool.set("node_llm.output.text", "hello")
        assert pool.get("node_llm.output.text") == "hello"

    def test_get_default(self):
        pool = VariablePool()
        assert pool.get("missing.key", "default") == "default"

    def test_nested_set(self):
        pool = VariablePool()
        pool.set("a.b.c.d", 42)
        assert pool.get("a.b.c.d") == 42

    def test_inject_system_variables(self):
        pool = VariablePool()
        pool.inject_system_variables(
            execution_id="exec_1",
            workflow_id="wf_1",
            workflow_version="1.0.0",
            user_id="user_1",
        )
        assert pool.get("sys.execution_id") == "exec_1"
        assert pool.get("sys.workflow_id") == "wf_1"
        assert pool.get("sys.user_id") == "user_1"

    def test_inject_user_inputs(self):
        pool = VariablePool()
        pool.inject_user_inputs({"name": "test", "count": 5})
        assert pool.get("node_start.output.name") == "test"
        assert pool.get("node_start.output.count") == 5

    def test_resolve_template(self):
        pool = VariablePool()
        pool.set("node_llm.output.text", "world")
        result = pool.resolve_template("Hello {{node_llm.output.text}}")
        assert result == "Hello world"

    def test_resolve_template_with_filter(self):
        pool = VariablePool()
        pool.set("node_llm.output.name", "test")
        result = pool.resolve_template("{{node_llm.output.name | default('N/A')}}")
        assert result == "test"

    def test_resolve_template_missing_var_raises(self):
        pool = VariablePool()
        with pytest.raises(Exception):
            pool.resolve_template("{{missing.var}}")

    def test_snapshot_and_restore(self):
        pool = VariablePool()
        pool.set("key1", "value1")
        pool.set("key2", {"nested": "value2"})

        snapshot = pool.snapshot()
        pool.set("key1", "modified")

        assert pool.get("key1") == "modified"
        pool.restore(snapshot)
        assert pool.get("key1") == "value1"
        assert pool.get("key2") == {"nested": "value2"}

    def test_merge_last_wins(self):
        pool1 = VariablePool()
        pool1.set("a", 1)
        pool1.set("b", 2)

        pool2 = VariablePool()
        pool2.set("b", 20)
        pool2.set("c", 30)

        pool1.merge(pool2, strategy="last_wins")
        assert pool1.get("a") == 1
        assert pool1.get("b") == 20
        assert pool1.get("c") == 30

    def test_merge_first_wins(self):
        pool1 = VariablePool()
        pool1.set("a", 1)
        pool1.set("b", 2)

        pool2 = VariablePool()
        pool2.set("b", 20)
        pool2.set("c", 30)

        pool1.merge(pool2, strategy="first_wins")
        assert pool1.get("a") == 1
        assert pool1.get("b") == 2
        assert pool1.get("c") == 30

    def test_delete(self):
        pool = VariablePool()
        pool.set("key", "value")
        assert pool.delete("key") is True
        assert pool.get("key") is None
        assert pool.delete("nonexistent") is False

    def test_exists(self):
        pool = VariablePool()
        pool.set("key", "value")
        assert pool.exists("key") is True
        assert pool.exists("missing") is False
