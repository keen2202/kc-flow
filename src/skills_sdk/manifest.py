"""Skill manifest parsing and validation — manifest.yaml v2 format."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import structlog
import yaml

logger = structlog.get_logger()


class SkillCategory(str, Enum):
    DOCUMENT = "document"
    ANALYSIS = "analysis"
    INTEGRATION = "integration"
    TRANSFORMATION = "transformation"
    NOTIFICATION = "notification"
    CUSTOM = "custom"


@dataclass
class SkillInput:
    """Skill input parameter definition."""
    name: str
    type: str  # string, number, boolean, object, array, file
    required: bool = False
    default: Any = None
    description: str = ""
    schema: dict[str, Any] | None = None  # JSON Schema for complex types


@dataclass
class SkillOutput:
    """Skill output definition."""
    name: str
    type: str
    description: str = ""


@dataclass
class SkillRuntime:
    """Skill runtime configuration."""
    language: str = "python"
    entry_point: str = "handler.py"
    handler_function: str = "handle"
    timeout_seconds: int = 60
    memory_limit: str = "256MB"
    dependencies: list[str] = field(default_factory=list)


@dataclass
class SkillSandbox:
    """Skill sandbox configuration."""
    enabled: bool = True
    image: str = "python:3.11-slim"
    network: str = "restricted"  # none, restricted, full
    allowed_domains: list[str] = field(default_factory=list)


@dataclass
class SkillDefinition:
    """Complete skill definition parsed from manifest.yaml v2."""
    name: str
    version: str
    display_name: str
    description: str
    author: str
    category: SkillCategory
    tags: list[str]
    inputs: list[SkillInput]
    outputs: list[SkillOutput]
    runtime: SkillRuntime
    sandbox: SkillSandbox
    icon: str = "puzzle"
    license: str = ""
    homepage: str = ""
    manifest_path: str = ""
    skill_dir: str = ""

    @classmethod
    def from_manifest(cls, manifest_path: str | Path) -> "SkillDefinition":
        """Parse a manifest.yaml file into a SkillDefinition."""
        path = Path(manifest_path)
        if not path.exists():
            raise FileNotFoundError(f"Manifest not found: {path}")

        with open(path) as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError(f"Invalid manifest format: {path}")

        return cls._parse(data, str(path.parent), str(path))

    @classmethod
    def from_dict(cls, data: dict[str, Any], skill_dir: str = "") -> "SkillDefinition":
        """Parse a manifest dict into a SkillDefinition."""
        return cls._parse(data, skill_dir, "")

    @classmethod
    def _parse(cls, data: dict[str, Any], skill_dir: str, manifest_path: str) -> "SkillDefinition":
        """Parse manifest data. Missing metadata fields default to empty strings — use validate() to check."""
        metadata = data.get("metadata") or {}

        # Parse inputs
        inputs: list[SkillInput] = []
        for inp in data.get("inputs", []):
            inputs.append(SkillInput(
                name=inp.get("name", ""),
                type=inp.get("type", "string"),
                required=inp.get("required", False),
                default=inp.get("default"),
                description=inp.get("description", ""),
                schema=inp.get("schema"),
            ))

        # Parse outputs
        outputs: list[SkillOutput] = []
        for out in data.get("outputs", []):
            outputs.append(SkillOutput(
                name=out.get("name", ""),
                type=out.get("type", "string"),
                description=out.get("description", ""),
            ))

        # Parse runtime
        runtime_data = data.get("runtime", {})
        runtime = SkillRuntime(
            language=runtime_data.get("language", "python"),
            entry_point=runtime_data.get("entry_point", "handler.py"),
            handler_function=runtime_data.get("handler_function", "handle"),
            timeout_seconds=runtime_data.get("timeout_seconds", 60),
            memory_limit=runtime_data.get("memory_limit", "256MB"),
            dependencies=runtime_data.get("dependencies", []),
        )

        # Parse sandbox
        sandbox_data = data.get("sandbox", {})
        sandbox = SkillSandbox(
            enabled=sandbox_data.get("enabled", True),
            image=sandbox_data.get("image", "python:3.11-slim"),
            network=sandbox_data.get("network", "restricted"),
            allowed_domains=sandbox_data.get("allowed_domains", []),
        )

        name = metadata.get("name", "")
        version = metadata.get("version", "")
        return cls(
            name=name,
            version=version,
            display_name=metadata.get("display_name", name),
            description=metadata.get("description", ""),
            author=metadata.get("author", ""),
            category=SkillCategory(metadata.get("category", "custom")),
            tags=metadata.get("tags", []),
            inputs=inputs,
            outputs=outputs,
            runtime=runtime,
            sandbox=sandbox,
            icon=metadata.get("icon", "puzzle"),
            license=metadata.get("license", ""),
            homepage=metadata.get("homepage", ""),
            manifest_path=manifest_path,
            skill_dir=skill_dir,
        )

    def validate(self) -> list[str]:
        """Validate the skill definition. Returns list of error messages."""
        errors: list[str] = []

        if not self.name:
            errors.append("Skill name is required")
        if not self.version:
            errors.append("Skill version is required")

        # Validate input names are unique
        input_names = [i.name for i in self.inputs]
        if len(input_names) != len(set(input_names)):
            errors.append("Duplicate input names")

        # Validate output names are unique
        output_names = [o.name for o in self.outputs]
        if len(output_names) != len(set(output_names)):
            errors.append("Duplicate output names")

        # Check handler file exists
        if self.skill_dir:
            handler_path = Path(self.skill_dir) / self.runtime.entry_point
            if not handler_path.exists():
                errors.append(f"Handler file not found: {handler_path}")

        return errors

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict (for manifest regeneration)."""
        return {
            "metadata": {
                "name": self.name,
                "version": self.version,
                "display_name": self.display_name,
                "description": self.description,
                "author": self.author,
                "category": self.category.value,
                "tags": self.tags,
                "icon": self.icon,
                "license": self.license,
                "homepage": self.homepage,
            },
            "inputs": [
                {"name": i.name, "type": i.type, "required": i.required, "default": i.default, "description": i.description}
                for i in self.inputs
            ],
            "outputs": [
                {"name": o.name, "type": o.type, "description": o.description}
                for o in self.outputs
            ],
            "runtime": {
                "language": self.runtime.language,
                "entry_point": self.runtime.entry_point,
                "handler_function": self.runtime.handler_function,
                "timeout_seconds": self.runtime.timeout_seconds,
                "memory_limit": self.runtime.memory_limit,
                "dependencies": self.runtime.dependencies,
            },
            "sandbox": {
                "enabled": self.sandbox.enabled,
                "image": self.sandbox.image,
                "network": self.sandbox.network,
                "allowed_domains": self.sandbox.allowed_domains,
            },
        }
