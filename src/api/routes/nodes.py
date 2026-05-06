"""Node management API endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.api.dependencies import CurrentUser, success_response
from src.engine.abstractions import NodeCategory, node_registry

router = APIRouter(prefix="/nodes", tags=["Nodes"])


@router.get("")
async def list_nodes(category: str | None = None):
    """List all registered node types, optionally filtered by category."""
    cat = NodeCategory(category) if category else None
    configs = node_registry.list_nodes(category=cat)

    return success_response([
        {
            "node_type": c.node_type,
            "display_name": c.display_name,
            "description": c.description,
            "category": c.category.value,
            "icon": c.icon,
            "version": c.version,
            "inputs": [v.model_dump() for v in c.inputs],
            "outputs": [v.model_dump() for v in c.outputs],
        }
        for c in configs
    ])


@router.get("/categories")
async def list_categories():
    """List all node categories."""
    return success_response([
        {"name": cat.value, "display_name": cat.name.title()}
        for cat in NodeCategory
    ])


@router.get("/{node_type}")
async def get_node(node_type: str):
    """Get detailed node type information including config schema."""
    config = node_registry.get_node_config(node_type)
    if not config:
        raise HTTPException(status_code=404, detail=f"Node type '{node_type}' not found")

    return success_response({
        "node_type": config.node_type,
        "display_name": config.display_name,
        "description": config.description,
        "category": config.category.value,
        "icon": config.icon,
        "version": config.version,
        "author": config.author,
        "tags": config.tags,
        "inputs": [v.model_dump() for v in config.inputs],
        "outputs": [v.model_dump() for v in config.outputs],
        "config_schema": config.config_schema,
    })


class InstallPluginRequest(BaseModel):
    """Plugin installation request."""
    plugin_url: str | None = None
    plugin_file: str | None = None


@router.post("/plugins")
async def install_plugin(request: InstallPluginRequest, current_user: CurrentUser):
    """Install a node plugin."""
    # TODO: implement plugin installation
    return success_response({"message": "Plugin installation not yet implemented"})


@router.delete("/plugins/{plugin_id}")
async def uninstall_plugin(plugin_id: str, current_user: CurrentUser):
    """Uninstall a node plugin."""
    # TODO: implement plugin uninstallation
    return success_response({"message": "Plugin uninstallation not yet implemented"})
