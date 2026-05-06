"""Skill management API endpoints."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.api.dependencies import CurrentUser, success_response
from src.skills_sdk.scheduler import SkillScheduler

router = APIRouter(prefix="/skills", tags=["Skills"])

# Module-level singleton — lazily initialised.
_scheduler: SkillScheduler | None = None


def _get_scheduler() -> SkillScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = SkillScheduler(skills_dir=Path("skills"))
        _scheduler.load_skills()
    return _scheduler


# ── Request / Response Schemas ──────────────────────────


class SkillSummary(BaseModel):
    name: str
    version: str
    display_name: str
    description: str
    category: str


class SkillDetail(BaseModel):
    name: str
    version: str
    display_name: str
    description: str
    category: str
    inputs: list[dict[str, Any]]
    outputs: list[dict[str, Any]]


class TestSkillRequest(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)
    environment: str = "development"


class ValidateSkillRequest(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)


class InstallSkillRequest(BaseModel):
    source: str = Field(..., description="Skill name from marketplace or path to archive")


# ── Endpoints ───────────────────────────────────────────


@router.get("")
async def list_skills() -> dict[str, Any]:
    """List all available skills."""
    scheduler = _get_scheduler()
    skills = [
        SkillSummary(
            name=s.name,
            version=s.version,
            display_name=s.display_name,
            description=s.description,
            category=s.category.value,
        ).model_dump()
        for s in scheduler.list_skills()
    ]
    return success_response(skills)


@router.post("/reload")
async def reload_skills(current_user: CurrentUser) -> dict[str, Any]:
    """Reload skills from the skills directory."""
    scheduler = _get_scheduler()
    count = scheduler.reload()
    return success_response({"reloaded": True, "count": count})


@router.get("/{skill_name}")
async def get_skill(skill_name: str) -> dict[str, Any]:
    """Get skill details by name."""
    scheduler = _get_scheduler()
    skill = scheduler.get_skill(skill_name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

    detail = SkillDetail(
        name=skill.name,
        version=skill.version,
        display_name=skill.display_name,
        description=skill.description,
        category=skill.category.value,
        inputs=[{"name": i.name, "type": i.type, "required": i.required, "description": i.description} for i in skill.inputs],
        outputs=[{"name": o.name, "type": o.type, "description": o.description} for o in skill.outputs],
    ).model_dump()
    return success_response(detail)


@router.post("/{skill_name}/test")
async def test_skill(
    skill_name: str,
    request: TestSkillRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Test execute a skill with given inputs."""
    scheduler = _get_scheduler()
    result = await scheduler.execute_skill(skill_name, request.inputs)
    return success_response({
        "skill_name": skill_name,
        "status": result["status"],
        "outputs": result["outputs"],
        "error": result.get("error"),
        "duration_ms": result["duration_ms"],
    })


@router.post("/{skill_name}/validate")
async def validate_skill(
    skill_name: str,
    request: ValidateSkillRequest,
) -> dict[str, Any]:
    """Validate inputs against a skill's input schema."""
    scheduler = _get_scheduler()
    errors = scheduler.validate_inputs(skill_name, request.inputs)
    return success_response({
        "skill_name": skill_name,
        "valid": len(errors) == 0,
        "errors": errors,
    })


@router.post("/{skill_name}/package")
async def package_skill(
    skill_name: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Package a skill for distribution (returns manifest info)."""
    scheduler = _get_scheduler()
    skill = scheduler.get_skill(skill_name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

    return success_response({
        "skill_name": skill_name,
        "version": skill.version,
        "manifest_path": str(skill.manifest_path),
        "skill_dir": str(skill.skill_dir),
        "status": "packaged",
    })


@router.post("/{skill_name}/install")
async def install_skill(
    skill_name: str,
    request: InstallSkillRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Install a skill (reload from disk after marketplace install)."""
    scheduler = _get_scheduler()
    count = scheduler.reload()
    skill = scheduler.get_skill(skill_name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found after install")

    return success_response({
        "skill_name": skill_name,
        "version": skill.version,
        "installed": True,
        "total_skills": count,
    })
