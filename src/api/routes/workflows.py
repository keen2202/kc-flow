"""Workflow management and execution API endpoints."""

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.api.dependencies import CurrentUser, Pagination, paginate, success_response
from src.engine.abstractions import ExecutionContext
from src.engine.graph_parser import GraphParser
from src.engine.scheduler import ExecutionScheduler
from src.engine.abstractions import NodeRegistry

router = APIRouter(prefix="/workflows", tags=["Workflows"])


# ── Request/Response Models ──


class CreateWorkflowRequest(BaseModel):
    """Create workflow request."""
    name: str
    description: str = ""
    dsl: dict[str, Any] = Field(default_factory=dict, description="Workflow DSL JSON")
    tags: list[str] = Field(default_factory=list)


class UpdateWorkflowRequest(BaseModel):
    """Update workflow request."""
    name: str | None = None
    description: str | None = None
    dsl: dict[str, Any] | None = None
    tags: list[str] | None = None


class RunWorkflowRequest(BaseModel):
    """Workflow execution request."""
    inputs: dict[str, Any] = Field(default_factory=dict)
    environment: str = "development"
    trace_enabled: bool = False


# ── In-Memory Store (replace with DB) ──

_workflows: dict[str, dict[str, Any]] = {}
_executions: dict[str, dict[str, Any]] = {}


# ── CRUD Endpoints ──


@router.post("")
async def create_workflow(request: CreateWorkflowRequest, current_user: CurrentUser):
    """Create a new workflow."""
    workflow_id = f"wf_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()

    workflow = {
        "id": workflow_id,
        "name": request.name,
        "description": request.description,
        "dsl": request.dsl,
        "tags": request.tags,
        "version": "0.1.0",
        "status": "draft",
        "user_id": current_user.user_id,
        "workspace_id": current_user.workspace_id,
        "created_at": now,
        "updated_at": now,
    }

    _workflows[workflow_id] = workflow
    return success_response(workflow)


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: str, current_user: CurrentUser):
    """Get workflow details."""
    workflow = _workflows.get(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return success_response(workflow)


@router.put("/{workflow_id}")
async def update_workflow(workflow_id: str, request: UpdateWorkflowRequest, current_user: CurrentUser):
    """Update workflow definition."""
    workflow = _workflows.get(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    if request.name is not None:
        workflow["name"] = request.name
    if request.description is not None:
        workflow["description"] = request.description
    if request.dsl is not None:
        workflow["dsl"] = request.dsl
    if request.tags is not None:
        workflow["tags"] = request.tags
    workflow["updated_at"] = datetime.now(timezone.utc).isoformat()

    return success_response(workflow)


@router.delete("/{workflow_id}")
async def delete_workflow(workflow_id: str, current_user: CurrentUser):
    """Delete a workflow (soft delete)."""
    workflow = _workflows.get(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    workflow["status"] = "deleted"
    workflow["updated_at"] = datetime.now(timezone.utc).isoformat()
    return success_response({"id": workflow_id, "deleted": True})


@router.get("")
async def list_workflows(current_user: CurrentUser, pagination: Pagination):
    """List all workflows."""
    user_workflows = [
        w for w in _workflows.values()
        if w.get("user_id") == current_user.user_id and w.get("status") != "deleted"
    ]
    total = len(user_workflows)
    start = pagination.offset
    end = start + pagination.limit
    items = user_workflows[start:end]
    return success_response(paginate(items, total, pagination))


# ── Version Management ──


@router.post("/{workflow_id}/publish")
async def publish_workflow(workflow_id: str, current_user: CurrentUser):
    """Publish a workflow version."""
    workflow = _workflows.get(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    workflow["status"] = "published"
    workflow["updated_at"] = datetime.now(timezone.utc).isoformat()
    return success_response({"id": workflow_id, "version": workflow["version"], "status": "published"})


@router.post("/{workflow_id}/rollback")
async def rollback_workflow(workflow_id: str, version: str, current_user: CurrentUser):
    """Rollback to a previous version."""
    workflow = _workflows.get(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    workflow["version"] = version
    workflow["updated_at"] = datetime.now(timezone.utc).isoformat()
    return success_response({"id": workflow_id, "version": version, "status": "rolled_back"})


@router.post("/{workflow_id}/clone")
async def clone_workflow(workflow_id: str, current_user: CurrentUser):
    """Clone a workflow."""
    workflow = _workflows.get(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    new_id = f"wf_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()

    cloned = {**workflow, "id": new_id, "name": f"{workflow['name']} (copy)", "status": "draft", "created_at": now, "updated_at": now}
    _workflows[new_id] = cloned
    return success_response(cloned)


# ── Execution Endpoints ──


@router.post("/{workflow_id}/run")
async def run_workflow(workflow_id: str, request: RunWorkflowRequest, current_user: CurrentUser):
    """Execute a workflow synchronously."""
    workflow = _workflows.get(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    dsl = workflow.get("dsl", {})
    if not dsl:
        raise HTTPException(status_code=400, detail="Workflow has no DSL definition")

    # Parse DSL
    parser = GraphParser()
    try:
        graph = parser.parse(dsl)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"DSL validation failed: {e}")

    # Create execution context
    execution_id = f"exec_{uuid.uuid4().hex[:12]}"
    context = ExecutionContext(
        execution_id=execution_id,
        workflow_id=workflow_id,
        workflow_version=workflow["version"],
        user_id=current_user.user_id,
        environment=request.environment,
        trace_enabled=request.trace_enabled,
    )

    # Execute with event broadcasting
    from src.api.routes.streaming import connection_manager

    scheduler = ExecutionScheduler(node_registry=NodeRegistry())
    scheduler.event_emitter.subscribe(lambda event: connection_manager.broadcast(execution_id, event))
    result = await scheduler.execute(graph, request.inputs, context)

    # Store execution record
    _executions[execution_id] = {
        "execution_id": execution_id,
        "workflow_id": workflow_id,
        "status": result.status,
        "outputs": result.outputs,
        "total_duration_ms": result.total_duration_ms,
        "total_tokens": result.total_tokens,
        "started_at": result.started_at,
        "completed_at": result.completed_at,
    }

    return success_response({
        "execution_id": execution_id,
        "status": result.status,
        "outputs": result.outputs,
        "duration_ms": result.total_duration_ms,
        "total_tokens": result.total_tokens,
    })


@router.post("/{workflow_id}/run-async")
async def run_workflow_async(workflow_id: str, request: RunWorkflowRequest, current_user: CurrentUser):
    """Execute a workflow asynchronously. Returns execution_id for polling."""
    workflow = _workflows.get(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    execution_id = f"exec_{uuid.uuid4().hex[:12]}"

    _executions[execution_id] = {
        "execution_id": execution_id,
        "workflow_id": workflow_id,
        "status": "queued",
        "inputs": request.inputs,
        "environment": request.environment,
        "user_id": current_user.user_id,
    }

    # TODO: enqueue to Celery for actual async execution
    return success_response({"execution_id": execution_id, "status": "queued"})


@router.post("/{workflow_id}/run-stream")
async def run_workflow_stream(workflow_id: str, request: RunWorkflowRequest, current_user: CurrentUser):
    """Execute a workflow with SSE streaming. Returns event stream URL."""
    execution_id = f"exec_{uuid.uuid4().hex[:12]}"

    _executions[execution_id] = {
        "execution_id": execution_id,
        "workflow_id": workflow_id,
        "status": "streaming",
        "user_id": current_user.user_id,
    }

    # TODO: implement actual SSE streaming
    return success_response({
        "execution_id": execution_id,
        "stream_url": f"/api/v1/workflows/{workflow_id}/executions/{execution_id}/stream",
    })


@router.get("/{workflow_id}/executions/{execution_id}")
async def get_execution(workflow_id: str, execution_id: str, current_user: CurrentUser):
    """Get execution status and results."""
    execution = _executions.get(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    return success_response(execution)


@router.get("/{workflow_id}/executions")
async def list_executions(workflow_id: str, current_user: CurrentUser, pagination: Pagination):
    """List executions for a workflow."""
    executions = [e for e in _executions.values() if e.get("workflow_id") == workflow_id]
    total = len(executions)
    items = executions[pagination.offset:pagination.offset + pagination.limit]
    return success_response(paginate(items, total, pagination))


@router.post("/{workflow_id}/executions/{execution_id}/cancel")
async def cancel_execution(workflow_id: str, execution_id: str, current_user: CurrentUser):
    """Cancel a running execution."""
    execution = _executions.get(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    execution["status"] = "cancelled"
    return success_response({"execution_id": execution_id, "status": "cancelled"})
