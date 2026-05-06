"""RBAC + ABAC permission and authorization system.

Implements:
- Role-Based Access Control (RBAC) with predefined and custom roles
- Attribute-Based Access Control (ABAC) with resource attributes
- Permission checking for workflows, executions, nodes, and skills
- Workspace-level isolation
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger()


class Permission(str, Enum):
    """Resource permissions."""
    # Workflow permissions
    WORKFLOW_CREATE = "workflow:create"
    WORKFLOW_READ = "workflow:read"
    WORKFLOW_UPDATE = "workflow:update"
    WORKFLOW_DELETE = "workflow:delete"
    WORKFLOW_PUBLISH = "workflow:publish"
    WORKFLOW_EXECUTE = "workflow:execute"

    # Execution permissions
    EXECUTION_READ = "execution:read"
    EXECUTION_CANCEL = "execution:cancel"
    EXECUTION_RETRY = "execution:retry"

    # Node permissions
    NODE_READ = "node:read"
    NODE_INSTALL = "node:install"
    NODE_UNINSTALL = "node:uninstall"

    # Skill permissions
    SKILL_READ = "skill:read"
    SKILL_EXECUTE = "skill:execute"
    SKILL_MANAGE = "skill:manage"

    # Admin permissions
    USER_MANAGE = "user:manage"
    WORKSPACE_MANAGE = "workspace:manage"
    SYSTEM_ADMIN = "system:admin"


class Role(str, Enum):
    """Predefined roles."""
    VIEWER = "viewer"
    EDITOR = "editor"
    EXECUTOR = "executor"
    ADMIN = "admin"
    OWNER = "owner"


# Role-permission mapping
ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.VIEWER: {
        Permission.WORKFLOW_READ,
        Permission.EXECUTION_READ,
        Permission.NODE_READ,
        Permission.SKILL_READ,
    },
    Role.EDITOR: {
        Permission.WORKFLOW_READ,
        Permission.WORKFLOW_CREATE,
        Permission.WORKFLOW_UPDATE,
        Permission.EXECUTION_READ,
        Permission.NODE_READ,
        Permission.SKILL_READ,
    },
    Role.EXECUTOR: {
        Permission.WORKFLOW_READ,
        Permission.WORKFLOW_EXECUTE,
        Permission.EXECUTION_READ,
        Permission.EXECUTION_CANCEL,
        Permission.EXECUTION_RETRY,
        Permission.NODE_READ,
        Permission.SKILL_READ,
        Permission.SKILL_EXECUTE,
    },
    Role.ADMIN: {
        Permission.WORKFLOW_CREATE,
        Permission.WORKFLOW_READ,
        Permission.WORKFLOW_UPDATE,
        Permission.WORKFLOW_DELETE,
        Permission.WORKFLOW_PUBLISH,
        Permission.WORKFLOW_EXECUTE,
        Permission.EXECUTION_READ,
        Permission.EXECUTION_CANCEL,
        Permission.EXECUTION_RETRY,
        Permission.NODE_READ,
        Permission.NODE_INSTALL,
        Permission.NODE_UNINSTALL,
        Permission.SKILL_READ,
        Permission.SKILL_EXECUTE,
        Permission.SKILL_MANAGE,
        Permission.USER_MANAGE,
        Permission.WORKSPACE_MANAGE,
    },
    Role.OWNER: set(Permission),  # All permissions
}


@dataclass
class ResourceAttributes:
    """Attributes of a resource for ABAC evaluation."""
    resource_type: str  # workflow, execution, node, skill
    resource_id: str
    owner_id: str
    workspace_id: str
    visibility: str = "private"  # private, workspace, public
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SubjectAttributes:
    """Attributes of the requesting subject for ABAC evaluation."""
    user_id: str
    workspace_id: str
    roles: list[str]
    groups: list[str] = field(default_factory=list)
    ip_address: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class RBACService:
    """Role-Based Access Control service with ABAC extensions.

    Usage:
        rbac = RBACService()
        allowed = rbac.check_permission(
            subject=SubjectAttributes(user_id="u1", workspace_id="ws1", roles=["editor"]),
            permission=Permission.WORKFLOW_UPDATE,
            resource=ResourceAttributes(resource_type="workflow", resource_id="wf_1", owner_id="u1", workspace_id="ws1"),
        )
    """

    def __init__(self) -> None:
        self._workspace_members: dict[str, dict[str, Role]] = {}  # workspace_id -> {user_id: role}
        self._custom_roles: dict[str, dict[str, set[Permission]]] = {}  # workspace_id -> {role_name: permissions}

    def add_workspace_member(self, workspace_id: str, user_id: str, role: Role | str) -> None:
        """Add a user to a workspace with a role."""
        if workspace_id not in self._workspace_members:
            self._workspace_members[workspace_id] = {}
        self._workspace_members[workspace_id][user_id] = Role(role) if isinstance(role, str) else role

    def remove_workspace_member(self, workspace_id: str, user_id: str) -> None:
        """Remove a user from a workspace."""
        if workspace_id in self._workspace_members:
            self._workspace_members[workspace_id].pop(user_id, None)

    def get_user_role(self, workspace_id: str, user_id: str) -> Role | None:
        """Get a user's role in a workspace."""
        return self._workspace_members.get(workspace_id, {}).get(user_id)

    def check_permission(
        self,
        subject: SubjectAttributes,
        permission: Permission,
        resource: ResourceAttributes | None = None,
    ) -> bool:
        """Check if a subject has a permission, optionally on a specific resource.

        Evaluates:
        1. RBAC: role-based permissions
        2. ABAC: resource ownership, workspace isolation, visibility
        """
        # Get effective permissions from roles
        effective_permissions: set[Permission] = set()

        for role_str in subject.roles:
            try:
                role = Role(role_str)
                effective_permissions |= ROLE_PERMISSIONS.get(role, set())
            except ValueError:
                # Check custom roles
                custom = self._custom_roles.get(subject.workspace_id, {}).get(role_str, set())
                effective_permissions |= custom

        # Check if permission is granted by role
        if permission not in effective_permissions:
            return False

        # ABAC checks
        if resource:
            return self._check_abac(subject, permission, resource)

        return True

    def _check_abac(
        self,
        subject: SubjectAttributes,
        permission: Permission,
        resource: ResourceAttributes,
    ) -> bool:
        """Attribute-Based Access Control checks."""
        # System admins bypass ABAC
        if Permission.SYSTEM_ADMIN in subject.roles:
            return True

        # Workspace isolation: user can only access resources in their workspace
        if resource.workspace_id != subject.workspace_id:
            # Allow if resource is public
            if resource.visibility != "public":
                return False

        # Owner always has full access to their own resources
        if resource.owner_id == subject.user_id:
            return True

        # Public resources are readable by anyone in the workspace
        if resource.visibility == "public" and permission.value.endswith(":read"):
            return True

        # Workspace-visible resources
        if resource.visibility == "workspace" and resource.workspace_id == subject.workspace_id:
            return True

        return True  # Default allow (RBAC already checked)

    def define_custom_role(
        self,
        workspace_id: str,
        role_name: str,
        permissions: set[Permission],
    ) -> None:
        """Define a custom role within a workspace."""
        if workspace_id not in self._custom_roles:
            self._custom_roles[workspace_id] = {}
        self._custom_roles[workspace_id][role_name] = permissions

    def get_user_permissions(self, subject: SubjectAttributes) -> set[Permission]:
        """Get all effective permissions for a user."""
        permissions: set[Permission] = set()
        for role_str in subject.roles:
            try:
                role = Role(role_str)
                permissions |= ROLE_PERMISSIONS.get(role, set())
            except ValueError:
                custom = self._custom_roles.get(subject.workspace_id, {}).get(role_str, set())
                permissions |= custom
        return permissions

    def list_roles(self, workspace_id: str | None = None) -> list[dict[str, Any]]:
        """List all available roles, including custom roles for a workspace."""
        roles = [
            {"name": role.value, "permissions": [p.value for p in perms]}
            for role, perms in ROLE_PERMISSIONS.items()
        ]

        if workspace_id and workspace_id in self._custom_roles:
            for role_name, perms in self._custom_roles[workspace_id].items():
                roles.append({"name": role_name, "permissions": [p.value for p in perms], "custom": True})

        return roles


# Global singleton
rbac_service = RBACService()
