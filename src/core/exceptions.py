"""Application-wide exception hierarchy."""

from typing import Any


class WorkflowError(Exception):
    """Base exception for all workflow engine errors."""

    def __init__(self, message: str, code: str = "internal_error", details: dict[str, Any] | None = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(message)


# ── Validation Errors (400) ──


class ValidationError(WorkflowError):
    """Base for all validation failures."""


class DSLValidationError(ValidationError):
    """DSL JSON format/structure validation failed."""

    def __init__(self, message: str, node_id: str | None = None, field: str | None = None):
        super().__init__(message, code="dsl_parse_error")
        self.node_id = node_id
        self.field = field


class GraphValidationError(ValidationError):
    """Graph structure validation failed (cycle, unreachable node, etc.)."""

    def __init__(self, message: str, code: str = "graph_validation_error"):
        super().__init__(message, code=code)


class VariableValidationError(ValidationError):
    """Variable reference/type validation failed."""

    def __init__(self, message: str, variable_path: str | None = None):
        super().__init__(message, code="invalid_variable_ref")
        self.variable_path = variable_path


class InputValidationError(ValidationError):
    """User input parameter validation failed."""


# ── Execution Errors (500) ──


class ExecutionError(WorkflowError):
    """Base for runtime execution failures."""


class NodeExecutionError(ExecutionError):
    """Node execution failed."""

    def __init__(self, message: str, node_id: str, node_type: str, cause: Exception | None = None):
        super().__init__(message, code="node_execution_error")
        self.node_id = node_id
        self.node_type = node_type
        self.cause = cause


class LLMCallError(NodeExecutionError):
    """LLM model call failed."""

    def __init__(self, message: str, node_id: str, model: str, cause: Exception | None = None):
        super().__init__(message, node_id=node_id, node_type="llm", cause=cause)
        self.model = model


class SkillExecutionError(NodeExecutionError):
    """Skill execution failed."""

    def __init__(self, message: str, node_id: str, skill_name: str, cause: Exception | None = None):
        super().__init__(message, node_id=node_id, node_type="skill", cause=cause)
        self.skill_name = skill_name


class CodeExecutionError(NodeExecutionError):
    """Code execution sandbox failed."""


class WorkflowTimeoutError(ExecutionError):
    """Workflow execution exceeded timeout."""


class ResourceExhaustedError(ExecutionError):
    """System resources exhausted (memory, disk, tokens)."""


class ExternalServiceError(ExecutionError):
    """External service (HTTP, API) call failed."""


# ── Auth Errors (401/403) ──


class AuthenticationError(WorkflowError):
    """Authentication failed (invalid/missing credentials)."""

    def __init__(self, message: str = "Authentication required"):
        super().__init__(message, code="unauthorized")


class AuthorizationError(WorkflowError):
    """Authorization failed (insufficient permissions)."""

    def __init__(self, message: str = "Access denied"):
        super().__init__(message, code="access_denied")


class QuotaExceededError(WorkflowError):
    """Resource quota exceeded."""

    def __init__(self, resource: str, limit: int):
        super().__init__(
            f"Quota exceeded for {resource}: limit is {limit}",
            code="quota_exceeded",
        )


# ── Not Found Errors (404) ──


class NotFoundError(WorkflowError):
    """Resource not found."""

    def __init__(self, resource_type: str, resource_id: str):
        super().__init__(
            f"{resource_type} not found: {resource_id}",
            code=f"{resource_type.lower()}_not_found",
        )


# ── Retry / Circuit Breaker ──


class RetryableError(ExecutionError):
    """Error that can be retried."""


class CircuitBreakerOpenError(ExecutionError):
    """Circuit breaker is open, rejecting calls."""

    def __init__(self, message: str = "", details: dict[str, Any] | None = None, name: str = "", recovery_seconds: float = 0):
        if not message and name:
            message = f"Circuit breaker '{name}' is OPEN. Retry after {recovery_seconds:.0f}s"
        super().__init__(
            message or "Circuit breaker is OPEN",
            code="circuit_breaker_open",
            details=details,
        )
