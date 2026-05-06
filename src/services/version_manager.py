"""Workflow version management — versioning, diffing, rollback, and promotion."""

import copy
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import unified_diff
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class WorkflowVersion:
    """A specific version of a workflow."""
    version_id: str
    workflow_id: str
    version: str  # semver string
    dsl: dict[str, Any]
    changelog: str
    status: str  # draft, published, deprecated
    created_by: str
    created_at: str
    published_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class VersionDiff:
    """Diff between two workflow versions."""
    from_version: str
    to_version: str
    changes: list[dict[str, Any]]
    summary: str


class VersionManager:
    """Manages workflow versions: create, publish, rollback, diff.

    Usage:
        manager = VersionManager()
        v1 = manager.create_version("wf_123", dsl_v1, "Initial version", "user_1")
        manager.publish_version(v1.version_id)
        v2 = manager.create_version("wf_123", dsl_v2, "Added error handling", "user_1")
        diff = manager.diff_versions(v1.version_id, v2.version_id)
    """

    def __init__(self) -> None:
        self._versions: dict[str, WorkflowVersion] = {}  # version_id -> version
        self._workflow_versions: dict[str, list[str]] = {}  # workflow_id -> [version_ids]

    def create_version(
        self,
        workflow_id: str,
        dsl: dict[str, Any],
        changelog: str = "",
        created_by: str = "system",
        version: str | None = None,
    ) -> WorkflowVersion:
        """Create a new version of a workflow.

        If version is not provided, auto-increments from the latest.
        """
        if workflow_id not in self._workflow_versions:
            self._workflow_versions[workflow_id] = []

        # Auto-version if not provided
        if version is None:
            existing = self._workflow_versions[workflow_id]
            if existing:
                latest = self._versions[existing[-1]]
                version = self._increment_version(latest.version)
            else:
                version = "0.1.0"

        version_id = f"ver_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        wf_version = WorkflowVersion(
            version_id=version_id,
            workflow_id=workflow_id,
            version=version,
            dsl=copy.deepcopy(dsl),
            changelog=changelog,
            status="draft",
            created_by=created_by,
            created_at=now,
        )

        self._versions[version_id] = wf_version
        self._workflow_versions[workflow_id].append(version_id)

        logger.info("Version created", version_id=version_id, workflow_id=workflow_id, version=version)
        return wf_version

    def get_version(self, version_id: str) -> WorkflowVersion | None:
        """Get a specific version by ID."""
        return self._versions.get(version_id)

    def get_latest_version(self, workflow_id: str, status: str | None = None) -> WorkflowVersion | None:
        """Get the latest version of a workflow, optionally filtered by status."""
        version_ids = self._workflow_versions.get(workflow_id, [])
        for vid in reversed(version_ids):
            v = self._versions[vid]
            if status is None or v.status == status:
                return v
        return None

    def list_versions(self, workflow_id: str) -> list[WorkflowVersion]:
        """List all versions of a workflow."""
        version_ids = self._workflow_versions.get(workflow_id, [])
        return [self._versions[vid] for vid in version_ids if vid in self._versions]

    def publish_version(self, version_id: str) -> bool:
        """Publish a version (draft -> published). Previous published version becomes deprecated."""
        version = self._versions.get(version_id)
        if not version or version.status != "draft":
            return False

        # Deprecate previous published version
        for vid in self._workflow_versions.get(version.workflow_id, []):
            v = self._versions[vid]
            if v.status == "published":
                v.status = "deprecated"

        version.status = "published"
        version.published_at = datetime.now(timezone.utc).isoformat()

        logger.info("Version published", version_id=version_id, version=version.version)
        return True

    def rollback(self, workflow_id: str, target_version_id: str, created_by: str = "system") -> WorkflowVersion | None:
        """Rollback to a previous version by creating a new version with the old DSL."""
        target = self._versions.get(target_version_id)
        if not target or target.workflow_id != workflow_id:
            return None

        # Create new version with the old DSL
        new_version = self.create_version(
            workflow_id=workflow_id,
            dsl=target.dsl,
            changelog=f"Rollback to version {target.version}",
            created_by=created_by,
        )

        self.publish_version(new_version.version_id)
        logger.info("Rollback completed", workflow_id=workflow_id, target_version=target.version)
        return new_version

    def diff_versions(self, version_id_1: str, version_id_2: str) -> VersionDiff:
        """Compute the diff between two versions."""
        v1 = self._versions.get(version_id_1)
        v2 = self._versions.get(version_id_2)

        if not v1 or not v2:
            return VersionDiff(
                from_version=version_id_1,
                to_version=version_id_2,
                changes=[],
                summary="One or both versions not found",
            )

        # Compare DSL JSON
        dsl1 = json.dumps(v1.dsl, indent=2, sort_keys=True).splitlines(keepends=True)
        dsl2 = json.dumps(v2.dsl, indent=2, sort_keys=True).splitlines(keepends=True)

        diff_lines = list(unified_diff(dsl1, dsl2, fromfile=f"v{v1.version}", tofile=f"v{v2.version}"))

        # Analyze changes
        changes: list[dict[str, Any]] = []
        nodes_v1 = set(v1.dsl.get("workflow", {}).get("nodes", []).__class__([]))
        nodes_v2 = set()

        # Deep comparison of nodes
        v1_nodes = {n.get("id"): n for n in v1.dsl.get("workflow", {}).get("nodes", [])}
        v2_nodes = {n.get("id"): n for n in v2.dsl.get("workflow", {}).get("nodes", [])}

        for nid in set(list(v1_nodes.keys()) + list(v2_nodes.keys())):
            if nid not in v1_nodes:
                changes.append({"type": "node_added", "node_id": nid})
            elif nid not in v2_nodes:
                changes.append({"type": "node_removed", "node_id": nid})
            elif v1_nodes[nid] != v2_nodes[nid]:
                changes.append({"type": "node_modified", "node_id": nid})

        # Compare edges
        v1_edges = set(json.dumps(e, sort_keys=True) for e in v1.dsl.get("workflow", {}).get("edges", []))
        v2_edges = set(json.dumps(e, sort_keys=True) for e in v2.dsl.get("workflow", {}).get("edges", []))

        added_edges = len(v2_edges - v1_edges)
        removed_edges = len(v1_edges - v2_edges)

        if added_edges:
            changes.append({"type": "edges_added", "count": added_edges})
        if removed_edges:
            changes.append({"type": "edges_removed", "count": removed_edges})

        summary_parts = []
        node_changes = [c for c in changes if c["type"].startswith("node_")]
        edge_changes = [c for c in changes if c["type"].startswith("edge")]
        if node_changes:
            summary_parts.append(f"{len(node_changes)} node changes")
        if edge_changes:
            summary_parts.append(f"{len(edge_changes)} edge changes")

        return VersionDiff(
            from_version=v1.version,
            to_version=v2.version,
            changes=changes,
            summary=", ".join(summary_parts) if summary_parts else "No changes",
        )

    def deprecate_version(self, version_id: str) -> bool:
        """Deprecate a version."""
        version = self._versions.get(version_id)
        if not version:
            return False
        version.status = "deprecated"
        return True

    @staticmethod
    def _increment_version(version: str) -> str:
        """Increment the patch version of a semver string."""
        parts = version.split(".")
        if len(parts) != 3:
            return "0.1.0"
        try:
            parts[2] = str(int(parts[2]) + 1)
            return ".".join(parts)
        except ValueError:
            return "0.1.0"
