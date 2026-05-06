"""Skills SDK — standalone skill development and execution framework.

Provides:
- SkillDefinition: manifest.yaml v2 parsing and validation
- SkillContext: runtime API for skills (LLM, HTTP, templates, caching)
- SkillScheduler: skill lifecycle management and execution
- SkillNode: integration with the workflow engine via @register_node
"""

from src.skills_sdk.manifest import SkillDefinition, SkillInput, SkillOutput
from src.skills_sdk.context import SkillContext
from src.skills_sdk.scheduler import SkillScheduler

__all__ = [
    "SkillDefinition",
    "SkillInput",
    "SkillOutput",
    "SkillContext",
    "SkillScheduler",
]
