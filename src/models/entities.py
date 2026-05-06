"""SQLAlchemy ORM models — all database entities."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Boolean,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import relationship

from src.models.database import Base


# ──────────────────────────────────────────────
# Helper
# ──────────────────────────────────────────────


def gen_uuid() -> uuid.UUID:
    return uuid.uuid4()


# ──────────────────────────────────────────────
# User & Workspace
# ──────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    role = Column(String(20), default="user")  # user / admin / super_admin
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    name = Column(String(255), nullable=False)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    plan = Column(String(20), default="free")  # free / pro / enterprise
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    role = Column(String(20), nullable=False)  # owner / developer / viewer
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    key_hash = Column(String(255), nullable=False)
    key_prefix = Column(String(20), nullable=False)  # first 8 chars for display
    name = Column(String(255))
    permissions = Column(JSONB, default=dict)
    rate_limit = Column(Integer)
    expires_at = Column(DateTime(timezone=True))
    last_used_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)


# ──────────────────────────────────────────────
# Workflow
# ──────────────────────────────────────────────


class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    current_version_id = Column(UUID(as_uuid=True), nullable=True)
    status = Column(String(20), default="draft")  # draft / active / archived
    tags = Column(ARRAY(String), default=list)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    versions = relationship("WorkflowVersion", back_populates="workflow", cascade="all, delete-orphan")
    executions = relationship("WorkflowExecution", back_populates="workflow", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_workflows_workspace", "workspace_id", "status", "updated_at",
              postgresql_where="deleted_at IS NULL"),
    )


class WorkflowVersion(Base):
    __tablename__ = "workflow_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    version = Column(String(20), nullable=False)
    status = Column(String(20), default="draft")  # draft / published / deprecated / archived
    dsl_definition = Column(JSONB, nullable=False)
    dsl_hash = Column(String(64))
    changelog = Column(Text, default="")
    environment = Column(String(20), default="development")  # development / staging / production
    published_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    workflow = relationship("Workflow", back_populates="versions")

    __table_args__ = (
        Index("idx_workflow_versions_workflow", "workflow_id", "version"),
        Index("idx_workflow_versions_env", "workflow_id", "environment"),
    )


class WorkflowVersionDiff(Base):
    __tablename__ = "workflow_version_diffs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    from_version_id = Column(UUID(as_uuid=True), ForeignKey("workflow_versions.id"), nullable=False)
    to_version_id = Column(UUID(as_uuid=True), ForeignKey("workflow_versions.id"), nullable=False)
    diff_type = Column(String(20), nullable=False)
    diff_detail = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ──────────────────────────────────────────────
# Execution
# ──────────────────────────────────────────────


class WorkflowExecution(Base):
    __tablename__ = "workflow_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    workflow_version_id = Column(UUID(as_uuid=True), ForeignKey("workflow_versions.id"), nullable=False)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(20), nullable=False, default="queued")
    trigger_type = Column(String(20), default="api")  # api / schedule / webhook / manual
    inputs = Column(JSONB)
    outputs = Column(JSONB)
    node_executions = Column(JSONB)
    variable_pool_snapshot = Column(JSONB)
    error_message = Column(Text)
    error_node_id = Column(String(100))
    total_tokens = Column(Integer, default=0)
    total_api_calls = Column(Integer, default=0)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    duration_ms = Column(Integer)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    workflow = relationship("Workflow", back_populates="executions")
    node_executions_detail = relationship("NodeExecution", back_populates="execution", cascade="all, delete-orphan")
    checkpoints = relationship("WorkflowCheckpoint", back_populates="execution", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_workflow_executions_workflow", "workflow_id", "created_at"),
        Index("idx_workflow_executions_status", "status",
              postgresql_where="status IN ('running', 'queued')"),
    )


class NodeExecution(Base):
    __tablename__ = "node_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    execution_id = Column(UUID(as_uuid=True), ForeignKey("workflow_executions.id", ondelete="CASCADE"), nullable=False)
    node_id = Column(String(100), nullable=False)
    node_type = Column(String(100), nullable=False)
    status = Column(String(20), nullable=False)
    inputs = Column(JSONB)
    outputs = Column(JSONB)
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    duration_ms = Column(Integer)
    token_count = Column(Integer, default=0)
    model_name = Column(String(100))
    prompt_text = Column(Text)
    response_text = Column(Text)

    execution = relationship("WorkflowExecution", back_populates="node_executions_detail")

    __table_args__ = (
        Index("idx_node_executions_execution", "execution_id", "node_id"),
    )


class WorkflowCheckpoint(Base):
    __tablename__ = "workflow_checkpoints"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    execution_id = Column(UUID(as_uuid=True), ForeignKey("workflow_executions.id", ondelete="CASCADE"), nullable=False)
    sequence_number = Column(Integer, nullable=False)
    graph_state = Column(JSONB, nullable=False)
    variable_pool_snapshot = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    execution = relationship("WorkflowExecution", back_populates="checkpoints")

    __table_args__ = (
        Index("idx_workflow_checkpoints_execution", "execution_id", "sequence_number"),
    )


# ──────────────────────────────────────────────
# Nodes, Plugins, Skills
# ──────────────────────────────────────────────


class NodeDefinition(Base):
    __tablename__ = "node_definitions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    node_type = Column(String(100), unique=True, nullable=False)
    display_name = Column(String(255))
    category = Column(String(50))
    is_builtin = Column(Boolean, default=True)
    plugin_id = Column(UUID(as_uuid=True), nullable=True)
    input_schema = Column(JSONB)
    output_schema = Column(JSONB)
    config_schema = Column(JSONB)
    version = Column(String(20))


class Plugin(Base):
    __tablename__ = "plugins"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    name = Column(String(255), nullable=False)
    version = Column(String(20))
    node_type = Column(String(100))
    entry_point = Column(String(255))
    runtime = Column(String(50), default="python")
    dependencies = Column(JSONB, default=dict)
    config = Column(JSONB, default=dict)
    status = Column(String(20), default="active")
    installed_at = Column(DateTime(timezone=True), server_default=func.now())


class SkillRegistry(Base):
    __tablename__ = "skill_registry"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    name = Column(String(255), unique=True, nullable=False)
    version = Column(String(20))
    display_name = Column(String(255))
    category = Column(String(100))
    manifest_path = Column(String(500))
    input_schema = Column(JSONB)
    output_schema = Column(JSONB)
    status = Column(String(20), default="active")
    last_loaded_at = Column(DateTime(timezone=True))


# ──────────────────────────────────────────────
# Audit
# ──────────────────────────────────────────────


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"))
    action = Column(String(50), nullable=False)
    resource_type = Column(String(50), nullable=False)
    resource_id = Column(String(100))
    details = Column(JSONB, default=dict)
    ip_address = Column(String(45))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_audit_logs_user", "user_id", "created_at"),
        Index("idx_audit_logs_workspace", "workspace_id", "created_at"),
    )
