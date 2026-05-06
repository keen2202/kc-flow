"""SkillScheduler — skill lifecycle management, loading, validation, and execution."""

import asyncio
import importlib.util
import sys
import time
from pathlib import Path
from typing import Any

import structlog

from src.skills_sdk.context import SkillContext
from src.skills_sdk.manifest import SkillDefinition

logger = structlog.get_logger()


class SkillScheduler:
    """Manages skill loading, validation, and execution.

    Usage:
        scheduler = SkillScheduler(skills_dir=Path("skills"))
        scheduler.load_skills()
        result = await scheduler.execute_skill("document_processor", {"file": "test.pdf"}, context)
    """

    def __init__(self, skills_dir: Path | str = "skills") -> None:
        self._skills_dir = Path(skills_dir)
        self._skills: dict[str, SkillDefinition] = {}  # name -> definition
        self._modules: dict[str, Any] = {}  # name -> loaded module

    def load_skills(self) -> int:
        """Scan skills directory and load all valid skill definitions.

        Returns count of successfully loaded skills.
        """
        if not self._skills_dir.exists():
            logger.warning("Skills directory not found", path=str(self._skills_dir))
            return 0

        loaded = 0
        for skill_dir in self._skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            manifest_path = skill_dir / "manifest.yaml"
            if not manifest_path.exists():
                continue

            try:
                definition = SkillDefinition.from_manifest(manifest_path)
                errors = definition.validate()
                if errors:
                    logger.warning("Skill validation failed", skill=definition.name, errors=errors)
                    continue

                self._skills[definition.name] = definition
                loaded += 1
                logger.info("Skill loaded", name=definition.name, version=definition.version)
            except Exception as e:
                logger.error("Failed to load skill", path=str(manifest_path), error=str(e))

        logger.info("Skills loaded", count=loaded, directory=str(self._skills_dir))
        return loaded

    def reload(self) -> int:
        """Reload all skills from disk."""
        self._skills.clear()
        self._modules.clear()
        return self.load_skills()

    def get_skill(self, name: str) -> SkillDefinition | None:
        """Get a skill definition by name."""
        return self._skills.get(name)

    def list_skills(self) -> list[SkillDefinition]:
        """List all loaded skill definitions."""
        return list(self._skills.values())

    def validate_inputs(self, name: str, inputs: dict[str, Any]) -> list[str]:
        """Validate inputs against a skill's input definitions.

        Returns list of error messages.
        """
        definition = self._skills.get(name)
        if not definition:
            return [f"Skill '{name}' not found"]

        errors: list[str] = []
        for input_def in definition.inputs:
            if input_def.required and input_def.name not in inputs:
                errors.append(f"Missing required input: '{input_def.name}' ({input_def.description})")

        return errors

    async def execute_skill(
        self,
        name: str,
        inputs: dict[str, Any],
        context: SkillContext | None = None,
    ) -> dict[str, Any]:
        """Execute a skill by name.

        Args:
            name: Skill name
            inputs: Input parameters
            context: Optional skill context (created if not provided)

        Returns:
            Dict with 'status', 'outputs', 'error', 'duration_ms'
        """
        definition = self._skills.get(name)
        if not definition:
            return {"status": "failed", "outputs": {}, "error": f"Skill '{name}' not found", "duration_ms": 0}

        # Validate inputs
        validation_errors = self.validate_inputs(name, inputs)
        if validation_errors:
            return {
                "status": "failed",
                "outputs": {},
                "error": f"Input validation failed: {'; '.join(validation_errors)}",
                "duration_ms": 0,
            }

        # Create context if not provided
        if context is None:
            context = SkillContext(
                execution_id=f"skill_{int(time.time())}",
                skill_name=name,
                skill_version=definition.version,
                user_id="system",
                working_dir=definition.skill_dir,
            )

        # Load handler module
        module = self._load_module(definition)
        if module is None:
            return {"status": "failed", "outputs": {}, "error": f"Failed to load handler for '{name}'", "duration_ms": 0}

        # Get handler function
        handler_name = definition.runtime.handler_function
        handler = getattr(module, handler_name, None)
        if handler is None:
            return {
                "status": "failed",
                "outputs": {},
                "error": f"Handler function '{handler_name}' not found in {definition.runtime.entry_point}",
                "duration_ms": 0,
            }

        # Execute
        start_time = time.monotonic()
        try:
            # Call handler
            if asyncio.iscoroutinefunction(handler):
                result = await handler(inputs, context)
            else:
                result = handler(inputs, context)

            duration_ms = int((time.monotonic() - start_time) * 1000)

            if isinstance(result, dict):
                return {
                    "status": result.get("status", "succeeded"),
                    "outputs": result.get("outputs", result),
                    "error": result.get("error"),
                    "duration_ms": duration_ms,
                }

            return {"status": "succeeded", "outputs": {"result": result}, "error": None, "duration_ms": duration_ms}

        except Exception as e:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            logger.error("Skill execution failed", skill=name, error=str(e))
            return {"status": "failed", "outputs": {}, "error": str(e), "duration_ms": duration_ms}

    def _load_module(self, definition: SkillDefinition) -> Any:
        """Load a skill's handler module."""
        if definition.name in self._modules:
            return self._modules[definition.name]

        handler_path = Path(definition.skill_dir) / definition.runtime.entry_point
        if not handler_path.exists():
            logger.error("Handler file not found", path=str(handler_path))
            return None

        try:
            spec = importlib.util.spec_from_file_location(
                f"skill_{definition.name}",
                str(handler_path),
            )
            if spec is None or spec.loader is None:
                return None

            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)

            self._modules[definition.name] = module
            return module
        except Exception as e:
            logger.error("Failed to load skill module", skill=definition.name, error=str(e))
            return None

    def generate_global_manifest(self) -> dict[str, Any]:
        """Generate a combined manifest of all loaded skills."""
        return {
            "version": "2.0",
            "skills": [
                {
                    "name": s.name,
                    "version": s.version,
                    "display_name": s.display_name,
                    "description": s.description,
                    "category": s.category.value,
                    "inputs": [{"name": i.name, "type": i.type, "required": i.required} for i in s.inputs],
                    "outputs": [{"name": o.name, "type": o.type} for o in s.outputs],
                }
                for s in self._skills.values()
            ],
        }
