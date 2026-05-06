"""Plugin management system — install, activate, deactivate, and manage node plugins."""

import json
import tarfile
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import structlog
import yaml

logger = structlog.get_logger()


class PluginStatus(str, Enum):
    INSTALLED = "installed"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"


@dataclass
class PluginInfo:
    """Plugin metadata."""
    plugin_id: str
    name: str
    version: str
    description: str
    author: str
    status: PluginStatus
    nodes: list[str]  # node types provided
    installed_at: str
    updated_at: str
    config: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class PluginManifest:
    """Plugin manifest.yaml structure."""
    name: str
    version: str
    description: str
    author: str
    nodes: list[dict[str, Any]]
    tools: list[dict[str, Any]] = field(default_factory=list)
    runtime: dict[str, Any] = field(default_factory=dict)
    permissions: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)


class PluginManager:
    """Manages the full plugin lifecycle: install, activate, deactivate, update, uninstall.

    Usage:
        manager = PluginManager(plugins_dir=Path("plugins"))
        info = manager.install(Path("my-plugin.tar.gz"))
        manager.activate(info.plugin_id)
    """

    def __init__(self, plugins_dir: Path | str = "plugins") -> None:
        self._plugins_dir = Path(plugins_dir)
        self._plugins_dir.mkdir(parents=True, exist_ok=True)
        self._plugins: dict[str, PluginInfo] = {}
        self._manifests: dict[str, PluginManifest] = {}

        # Load existing plugins
        self._load_installed_plugins()

    def _load_installed_plugins(self) -> None:
        """Load previously installed plugins from disk."""
        for plugin_dir in self._plugins_dir.iterdir():
            if not plugin_dir.is_dir():
                continue
            manifest_path = plugin_dir / "manifest.yaml"
            if manifest_path.exists():
                try:
                    manifest = self._parse_manifest(manifest_path)
                    plugin_id = plugin_dir.name
                    self._manifests[plugin_id] = manifest
                    self._plugins[plugin_id] = PluginInfo(
                        plugin_id=plugin_id,
                        name=manifest.name,
                        version=manifest.version,
                        description=manifest.description,
                        author=manifest.author,
                        status=PluginStatus.ACTIVE,
                        nodes=[n.get("type", "") for n in manifest.nodes],
                        installed_at=datetime.now(timezone.utc).isoformat(),
                        updated_at=datetime.now(timezone.utc).isoformat(),
                    )
                except Exception as e:
                    logger.error("Failed to load plugin", path=str(plugin_dir), error=str(e))

    def install(self, archive_path: Path) -> PluginInfo:
        """Install a plugin from a .plugin (tar.gz) archive.

        Args:
            archive_path: Path to the .plugin archive

        Returns:
            PluginInfo with installation details
        """
        if not archive_path.exists():
            raise FileNotFoundError(f"Plugin archive not found: {archive_path}")

        # Extract to temp dir first for validation
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(tmp_path)

            # Find manifest
            manifest_path = self._find_manifest(tmp_path)
            if manifest_path is None:
                raise ValueError("Plugin archive does not contain manifest.yaml")

            manifest = self._parse_manifest(manifest_path)

            # Validate
            errors = self._validate_manifest(manifest)
            if errors:
                raise ValueError(f"Invalid plugin manifest: {'; '.join(errors)}")

            # Copy to plugins directory
            plugin_id = f"plugin_{manifest.name}_{uuid.uuid4().hex[:8]}"
            plugin_dir = self._plugins_dir / plugin_id

            if plugin_dir.exists():
                import shutil
                shutil.rmtree(plugin_dir)

            import shutil
            shutil.copytree(tmp_path, plugin_dir, dirs_exist_ok=True)

            # Register
            now = datetime.now(timezone.utc).isoformat()
            self._manifests[plugin_id] = manifest
            self._plugins[plugin_id] = PluginInfo(
                plugin_id=plugin_id,
                name=manifest.name,
                version=manifest.version,
                description=manifest.description,
                author=manifest.author,
                status=PluginStatus.INSTALLED,
                nodes=[n.get("type", "") for n in manifest.nodes],
                installed_at=now,
                updated_at=now,
            )

            logger.info("Plugin installed", plugin_id=plugin_id, name=manifest.name)
            return self._plugins[plugin_id]

    def activate(self, plugin_id: str) -> bool:
        """Activate a plugin, registering its nodes with the global registry."""
        plugin = self._plugins.get(plugin_id)
        if not plugin:
            return False

        if plugin.status == PluginStatus.ACTIVE:
            return True

        manifest = self._manifests.get(plugin_id)
        if not manifest:
            return False

        try:
            # Register nodes from the plugin
            plugin_dir = self._plugins_dir / plugin_id
            self._register_plugin_nodes(plugin_id, manifest, plugin_dir)

            plugin.status = PluginStatus.ACTIVE
            plugin.updated_at = datetime.now(timezone.utc).isoformat()
            plugin.error = None
            logger.info("Plugin activated", plugin_id=plugin_id)
            return True
        except Exception as e:
            plugin.status = PluginStatus.ERROR
            plugin.error = str(e)
            logger.error("Plugin activation failed", plugin_id=plugin_id, error=str(e))
            return False

    def deactivate(self, plugin_id: str) -> bool:
        """Deactivate a plugin, unregistering its nodes."""
        plugin = self._plugins.get(plugin_id)
        if not plugin:
            return False

        manifest = self._manifests.get(plugin_id)
        if manifest:
            from src.engine.abstractions import node_registry
            for node_def in manifest.nodes:
                node_type = node_def.get("type", "")
                if node_type:
                    node_registry.unregister(node_type)

        plugin.status = PluginStatus.INACTIVE
        plugin.updated_at = datetime.now(timezone.utc).isoformat()
        logger.info("Plugin deactivated", plugin_id=plugin_id)
        return True

    def uninstall(self, plugin_id: str) -> bool:
        """Uninstall a plugin completely."""
        plugin = self._plugins.get(plugin_id)
        if not plugin:
            return False

        # Deactivate first
        if plugin.status == PluginStatus.ACTIVE:
            self.deactivate(plugin_id)

        # Remove from disk
        plugin_dir = self._plugins_dir / plugin_id
        if plugin_dir.exists():
            import shutil
            shutil.rmtree(plugin_dir)

        # Remove from registry
        del self._plugins[plugin_id]
        self._manifests.pop(plugin_id, None)

        logger.info("Plugin uninstalled", plugin_id=plugin_id)
        return True

    def get_plugin(self, plugin_id: str) -> PluginInfo | None:
        """Get plugin info by ID."""
        return self._plugins.get(plugin_id)

    def list_plugins(self) -> list[PluginInfo]:
        """List all installed plugins."""
        return list(self._plugins.values())

    def update(self, plugin_id: str, archive_path: Path) -> PluginInfo | None:
        """Update a plugin with a new archive."""
        if plugin_id not in self._plugins:
            return None

        # Uninstall old version
        self.uninstall(plugin_id)

        # Install new version
        return self.install(archive_path)

    def _find_manifest(self, directory: Path) -> Path | None:
        """Find manifest.yaml in a directory tree."""
        for path in directory.rglob("manifest.yaml"):
            return path
        return None

    def _parse_manifest(self, path: Path) -> PluginManifest:
        """Parse a manifest.yaml file."""
        with open(path) as f:
            data = yaml.safe_load(f)

        return PluginManifest(
            name=data.get("name", ""),
            version=data.get("version", ""),
            description=data.get("description", ""),
            author=data.get("author", ""),
            nodes=data.get("nodes", []),
            tools=data.get("tools", []),
            runtime=data.get("runtime", {}),
            permissions=data.get("permissions", {}),
            dependencies=data.get("dependencies", []),
        )

    def _validate_manifest(self, manifest: PluginManifest) -> list[str]:
        """Validate a plugin manifest."""
        errors: list[str] = []
        if not manifest.name:
            errors.append("Plugin name is required")
        if not manifest.version:
            errors.append("Plugin version is required")
        if not manifest.nodes:
            errors.append("Plugin must define at least one node")
        for node in manifest.nodes:
            if not node.get("type"):
                errors.append("Each node must have a 'type' field")
        return errors

    def _register_plugin_nodes(
        self, plugin_id: str, manifest: PluginManifest, plugin_dir: Path
    ) -> None:
        """Dynamically register plugin nodes with the global registry."""
        import importlib.util
        import sys

        for node_def in manifest.nodes:
            node_type = node_def.get("type", "")
            handler_file = node_def.get("handler", "nodes.py")
            handler_class = node_def.get("class", "")

            if not node_type or not handler_class:
                continue

            handler_path = plugin_dir / handler_file
            if not handler_path.exists():
                logger.warning("Node handler not found", path=str(handler_path))
                continue

            # Load module and find class
            spec = importlib.util.spec_from_file_location(
                f"plugin_{plugin_id}_{node_type}", str(handler_path)
            )
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)

                node_cls = getattr(module, handler_class, None)
                if node_cls:
                    from src.engine.abstractions import node_registry
                    node_registry.register(node_cls)
                    logger.info("Plugin node registered", node_type=node_type, plugin=plugin_id)
