"""SkillNode — workflow engine integration for skills via @register_node."""

from typing import Any

import structlog

from src.engine.abstractions import (
    BaseNode,
    ExecutionContext,
    NodeCategory,
    NodeResult,
    NodeStatus,
    VariableDef,
    register_node,
)
from src.skills_sdk.context import SkillContext
from src.skills_sdk.scheduler import SkillScheduler

logger = structlog.get_logger()


@register_node(
    node_type="skill",
    display_name="技能节点",
    category=NodeCategory.DATA,
    icon="puzzle",
    description="调用 Skills SDK 中注册的技能执行任务",
    inputs=[
        VariableDef(name="skill_name", type="string", required=True, description="技能名称"),
        VariableDef(name="params", type="object", description="技能参数"),
    ],
    outputs=[
        VariableDef(name="result", type="any", description="技能执行结果"),
        VariableDef(name="duration_ms", type="number", description="执行耗时"),
    ],
    config_schema={
        "type": "object",
        "properties": {
            "skill_name": {"type": "string", "description": "要调用的技能名称"},
            "skill_params": {"type": "object", "description": "技能参数模板，支持 {{variable}}"},
            "timeout_override": {"type": "integer", "description": "覆盖技能默认超时"},
        },
        "required": ["skill_name"],
    },
)
class SkillNode(BaseNode):
    """Workflow node that delegates execution to a registered skill."""

    _scheduler: SkillScheduler | None = None

    @classmethod
    def set_scheduler(cls, scheduler: SkillScheduler) -> None:
        """Set the global skill scheduler (called during app initialization)."""
        cls._scheduler = scheduler

    async def execute(self, variable_pool: Any, context: ExecutionContext | None = None) -> NodeResult:
        skill_name = self.node_config.get("skill_name", "")
        skill_params_template = self.node_config.get("skill_params", {})

        if not skill_name:
            return NodeResult(status=NodeStatus.FAILED, error="No skill_name configured")

        # Resolve skill params from variable pool
        params: dict[str, Any] = {}
        for key, value in skill_params_template.items():
            if isinstance(value, str) and "{{" in value:
                params[key] = variable_pool.resolve_template(value)
            else:
                params[key] = value

        # Get scheduler
        scheduler = self._scheduler
        if scheduler is None:
            # Try to create a default scheduler
            from src.config.settings import get_settings
            settings = get_settings()
            scheduler = SkillScheduler(skills_dir=settings.skills_dir)
            scheduler.load_skills()

        # Create execution context
        skill_context = SkillContext(
            execution_id=context.execution_id if context else f"skill_{self.node_id}",
            skill_name=skill_name,
            skill_version="1.0.0",
            user_id=context.user_id if context else "system",
        )

        # Execute skill
        result = await scheduler.execute_skill(skill_name, params, skill_context)

        if result.get("status") == "failed":
            return NodeResult(
                status=NodeStatus.FAILED,
                error=result.get("error", "Skill execution failed"),
            )

        return NodeResult(
            status=NodeStatus.SUCCEEDED,
            outputs={
                "result": result.get("outputs", {}),
                "duration_ms": result.get("duration_ms", 0),
            },
        )
