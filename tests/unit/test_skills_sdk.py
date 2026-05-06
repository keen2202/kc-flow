"""Unit tests for Skills SDK manifest parsing and context."""

import pytest
import tempfile
from pathlib import Path

from src.skills_sdk.manifest import SkillDefinition, SkillCategory
from src.skills_sdk.context import SkillContext


class TestSkillManifest:
    """Test manifest.yaml parsing and validation."""

    def test_parse_manifest_dict(self):
        data = {
            "metadata": {
                "name": "test_skill",
                "version": "1.0.0",
                "display_name": "Test Skill",
                "description": "A test skill",
                "category": "custom",
            },
            "inputs": [
                {"name": "query", "type": "string", "required": True},
            ],
            "outputs": [
                {"name": "result", "type": "string"},
            ],
            "runtime": {
                "language": "python",
                "entry_point": "handler.py",
            },
        }

        skill = SkillDefinition.from_dict(data, skill_dir="/tmp/test")
        assert skill.name == "test_skill"
        assert skill.version == "1.0.0"
        assert skill.category == SkillCategory.CUSTOM
        assert len(skill.inputs) == 1
        assert skill.inputs[0].required is True
        assert len(skill.outputs) == 1

    def test_parse_manifest_file(self):
        manifest_content = """
metadata:
  name: file_skill
  version: "2.0.0"
  display_name: File Skill
  description: From file
  category: analysis
inputs:
  - name: text
    type: string
    required: true
  - name: max_length
    type: number
    default: 100
outputs:
  - name: summary
    type: string
runtime:
  language: python
  entry_point: main.py
  handler_function: run
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(manifest_content)
            f.flush()

            skill = SkillDefinition.from_manifest(f.name)
            assert skill.name == "file_skill"
            assert skill.version == "2.0.0"
            assert skill.category == SkillCategory.ANALYSIS
            assert len(skill.inputs) == 2
            assert skill.runtime.handler_function == "run"

    def test_validate_missing_name(self):
        skill = SkillDefinition.from_dict({
            "metadata": {"version": "1.0.0"},
        })
        errors = skill.validate()
        assert any("name" in e.lower() for e in errors)

    def test_validate_missing_version(self):
        skill = SkillDefinition.from_dict({
            "metadata": {"name": "test"},
        })
        errors = skill.validate()
        assert any("version" in e.lower() for e in errors)

    def test_to_dict_roundtrip(self):
        data = {
            "metadata": {
                "name": "roundtrip",
                "version": "1.0.0",
                "display_name": "Roundtrip",
                "category": "custom",
            },
            "inputs": [{"name": "x", "type": "string"}],
            "outputs": [{"name": "y", "type": "string"}],
        }
        skill = SkillDefinition.from_dict(data)
        exported = skill.to_dict()
        assert exported["metadata"]["name"] == "roundtrip"
        assert len(exported["inputs"]) == 1


class TestSkillContext:
    """Test SkillContext runtime API."""

    def test_context_creation(self):
        ctx = SkillContext(
            execution_id="exec_1",
            skill_name="test",
            skill_version="1.0.0",
            user_id="user_1",
        )
        assert ctx.execution_id == "exec_1"
        assert ctx.skill_name == "test"

    def test_cache_set_and_get(self):
        ctx = SkillContext(
            execution_id="exec_1",
            skill_name="test",
            skill_version="1.0.0",
            user_id="user_1",
        )
        ctx.cache_set("key1", "value1", ttl=60)
        assert ctx.cache_get("key1") == "value1"
        assert ctx.cache_get("nonexistent") is None

    def test_render_template(self):
        ctx = SkillContext(
            execution_id="exec_1",
            skill_name="test",
            skill_version="1.0.0",
            user_id="user_1",
        )
        result = ctx.render_template("Hello {{name}}", name="World")
        assert result == "Hello World"

    def test_record_metric(self):
        ctx = SkillContext(
            execution_id="exec_1",
            skill_name="test",
            skill_version="1.0.0",
            user_id="user_1",
        )
        ctx.record_metric("latency", 150, {"endpoint": "/api"})
        metrics = ctx.get_metrics()
        assert len(metrics) == 1
        assert metrics[0]["name"] == "latency"
        assert metrics[0]["value"] == 150

    def test_elapsed_ms(self):
        ctx = SkillContext(
            execution_id="exec_1",
            skill_name="test",
            skill_version="1.0.0",
            user_id="user_1",
        )
        assert ctx.elapsed_ms >= 0
