"""Node & Skill Marketplace — discover, publish, install packages."""

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()


class PackageType(str, Enum):
    NODE = "node"
    SKILL = "skill"
    PLUGIN = "plugin"


class PackageStatus(str, Enum):
    PENDING = "pending"  # awaiting review
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"


@dataclass
class PackageVersion:
    version: str
    changelog: str = ""
    checksum: str = ""
    published_at: str = ""
    downloads: int = 0
    api_version_min: str = "0.1.0"
    api_version_max: str = ""


@dataclass
class PackageReview:
    review_id: str
    user_id: str
    rating: int  # 1-5
    title: str = ""
    comment: str = ""
    created_at: str = ""


@dataclass
class PackageEntry:
    """A marketplace package (node, skill, or plugin)."""
    package_id: str
    name: str
    display_name: str
    description: str
    package_type: PackageType
    author: str
    author_id: str
    category: str
    tags: list[str] = field(default_factory=list)
    icon: str = ""
    homepage: str = ""
    repository: str = ""
    license: str = "MIT"
    status: PackageStatus = PackageStatus.APPROVED
    current_version: str = "0.1.0"
    versions: list[PackageVersion] = field(default_factory=list)
    reviews: list[PackageReview] = field(default_factory=list)
    total_downloads: int = 0
    avg_rating: float = 0.0
    verified: bool = False
    created_at: str = ""
    updated_at: str = ""


class PackageRegistry:
    """In-memory marketplace registry.

    In production this would use PostgreSQL + S3/MinIO for storage.
    """

    def __init__(self) -> None:
        self._packages: dict[str, PackageEntry] = {}
        self._seed_demo_packages()

    # ── Search & Browse ──

    def search(
        self,
        query: str = "",
        package_type: PackageType | None = None,
        category: str = "",
        sort: str = "downloads",  # downloads | rating | newest | name
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """Search packages with filters."""
        results = list(self._packages.values())

        # Filter by type
        if package_type:
            results = [p for p in results if p.package_type == package_type]

        # Filter by category
        if category:
            results = [p for p in results if p.category == category]

        # Filter by status
        results = [p for p in results if p.status == PackageStatus.APPROVED]

        # Text search
        if query:
            q = query.lower()
            results = [
                p for p in results
                if q in p.name.lower()
                or q in p.display_name.lower()
                or q in p.description.lower()
                or any(q in t.lower() for t in p.tags)
            ]

        # Sort
        sorters = {
            "downloads": lambda p: -p.total_downloads,
            "rating": lambda p: -p.avg_rating,
            "newest": lambda p: p.created_at,
            "name": lambda p: p.name.lower(),
        }
        results.sort(key=sorters.get(sort, sorters["downloads"]))  # type: ignore[operator]

        # Paginate
        total = len(results)
        start = (page - 1) * page_size
        items = results[start : start + page_size]

        return {
            "items": [self._package_to_dict(p) for p in items],
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size,
        }

    def get_package(self, name: str) -> PackageEntry | None:
        """Get a package by name."""
        return self._packages.get(name)

    def get_categories(self) -> list[dict[str, Any]]:
        """Get all categories with counts."""
        cats: dict[str, int] = {}
        for p in self._packages.values():
            if p.status == PackageStatus.APPROVED:
                cats[p.category] = cats.get(p.category, 0) + 1
        return [{"name": k, "count": v} for k, v in sorted(cats.items())]

    def get_featured(self, limit: int = 6) -> list[dict[str, Any]]:
        """Get featured/top packages."""
        approved = [p for p in self._packages.values() if p.status == PackageStatus.APPROVED]
        approved.sort(key=lambda p: (-p.avg_rating, -p.total_downloads))
        return [self._package_to_dict(p) for p in approved[:limit]]

    # ── Publish ──

    def publish(
        self,
        name: str,
        display_name: str,
        description: str,
        package_type: str,
        author: str,
        author_id: str,
        category: str,
        version: str = "0.1.0",
        changelog: str = "",
        tags: list[str] | None = None,
        icon: str = "",
        homepage: str = "",
        repository: str = "",
        license: str = "MIT",
    ) -> PackageEntry:
        """Publish a new package or new version."""
        now = datetime.now(timezone.utc).isoformat()

        if name in self._packages:
            # Update existing package — add new version
            pkg = self._packages[name]
            pkg.current_version = version
            pkg.versions.append(PackageVersion(
                version=version,
                changelog=changelog,
                published_at=now,
                checksum=hashlib.sha256(f"{name}:{version}".encode()).hexdigest()[:16],
            ))
            pkg.updated_at = now
            logger.info("Package version published", name=name, version=version)
            return pkg

        # New package
        pkg = PackageEntry(
            package_id=f"pkg_{uuid.uuid4().hex[:12]}",
            name=name,
            display_name=display_name,
            description=description,
            package_type=PackageType(package_type),
            author=author,
            author_id=author_id,
            category=category,
            tags=tags or [],
            icon=icon,
            homepage=homepage,
            repository=repository,
            license=license,
            status=PackageStatus.APPROVED,  # auto-approve for demo
            current_version=version,
            versions=[PackageVersion(
                version=version,
                changelog=changelog or "Initial release",
                published_at=now,
                checksum=hashlib.sha256(f"{name}:{version}".encode()).hexdigest()[:16],
            )],
            total_downloads=0,
            avg_rating=0.0,
            created_at=now,
            updated_at=now,
        )
        self._packages[name] = pkg
        logger.info("Package published", name=name, type=package_type)
        return pkg

    # ── Install ──

    def install(self, name: str, user_id: str) -> dict[str, Any] | None:
        """Record a package install (download)."""
        pkg = self._packages.get(name)
        if not pkg or pkg.status != PackageStatus.APPROVED:
            return None

        pkg.total_downloads += 1
        if pkg.versions:
            pkg.versions[-1].downloads += 1

        logger.info("Package installed", name=name, user_id=user_id)
        return {
            "package": self._package_to_dict(pkg),
            "install_path": f"skills/{name}" if pkg.package_type == PackageType.SKILL else f"plugins/{name}",
            "instructions": f"Package '{name}' v{pkg.current_version} installed successfully.",
        }

    # ── Reviews ──

    def add_review(
        self,
        name: str,
        user_id: str,
        rating: int,
        title: str = "",
        comment: str = "",
    ) -> PackageReview | None:
        """Add or update a review for a package."""
        pkg = self._packages.get(name)
        if not pkg:
            return None

        # Clamp rating
        rating = max(1, min(5, rating))

        now = datetime.now(timezone.utc).isoformat()
        review = PackageReview(
            review_id=f"rev_{uuid.uuid4().hex[:8]}",
            user_id=user_id,
            rating=rating,
            title=title,
            comment=comment,
            created_at=now,
        )

        # Replace existing review from same user
        pkg.reviews = [r for r in pkg.reviews if r.user_id != user_id]
        pkg.reviews.append(review)

        # Recalculate average
        if pkg.reviews:
            pkg.avg_rating = round(sum(r.rating for r in pkg.reviews) / len(pkg.reviews), 1)

        logger.info("Review added", package=name, rating=rating, user=user_id)
        return review

    def get_reviews(self, name: str) -> list[dict[str, Any]]:
        """Get all reviews for a package."""
        pkg = self._packages.get(name)
        if not pkg:
            return []
        return [
            {
                "review_id": r.review_id,
                "user_id": r.user_id,
                "rating": r.rating,
                "title": r.title,
                "comment": r.comment,
                "created_at": r.created_at,
            }
            for r in pkg.reviews
        ]

    # ── Helpers ──

    def _package_to_dict(self, pkg: PackageEntry) -> dict[str, Any]:
        return {
            "package_id": pkg.package_id,
            "name": pkg.name,
            "display_name": pkg.display_name,
            "description": pkg.description,
            "type": pkg.package_type.value,
            "author": pkg.author,
            "category": pkg.category,
            "tags": pkg.tags,
            "icon": pkg.icon,
            "homepage": pkg.homepage,
            "repository": pkg.repository,
            "license": pkg.license,
            "status": pkg.status.value,
            "current_version": pkg.current_version,
            "versions": [
                {"version": v.version, "changelog": v.changelog, "published_at": v.published_at, "downloads": v.downloads}
                for v in pkg.versions
            ],
            "total_downloads": pkg.total_downloads,
            "avg_rating": pkg.avg_rating,
            "review_count": len(pkg.reviews),
            "verified": pkg.verified,
            "created_at": pkg.created_at,
            "updated_at": pkg.updated_at,
        }

    def _seed_demo_packages(self) -> None:
        """Seed the registry with demo packages for development."""
        now = datetime.now(timezone.utc).isoformat()

        demo_packages = [
            {
                "name": "sentiment-analyzer",
                "display_name": "Sentiment Analyzer",
                "description": "LLM-based sentiment analysis with structured output. Supports positive/negative/neutral classification with confidence scores.",
                "package_type": "skill",
                "author": "workflow-team",
                "author_id": "user_team",
                "category": "AI & NLP",
                "tags": ["sentiment", "nlp", "llm", "text-analysis"],
                "avg_rating": 4.7,
                "total_downloads": 1250,
            },
            {
                "name": "document-processor",
                "display_name": "Document Processor",
                "description": "Parse and extract text from PDF, Word, Excel, and CSV documents. Supports metadata extraction and table detection.",
                "package_type": "skill",
                "author": "workflow-team",
                "author_id": "user_team",
                "category": "Document Processing",
                "tags": ["pdf", "docx", "xlsx", "parser"],
                "avg_rating": 4.5,
                "total_downloads": 980,
            },
            {
                "name": "risk-analyzer",
                "display_name": "Risk Analyzer",
                "description": "LLM-powered document risk analysis with structured output. Identifies potential risks, compliance issues, and provides severity ratings.",
                "package_type": "skill",
                "author": "workflow-team",
                "author_id": "user_team",
                "category": "AI & NLP",
                "tags": ["risk", "compliance", "analysis", "llm"],
                "avg_rating": 4.3,
                "total_downloads": 670,
            },
            {
                "name": "data-transformer",
                "display_name": "Data Transformer",
                "description": "Convert between JSON, XML, and CSV formats with jq-style field mapping. Supports schema validation and data enrichment.",
                "package_type": "skill",
                "author": "workflow-team",
                "author_id": "user_team",
                "category": "Data Processing",
                "tags": ["json", "xml", "csv", "transform", "etl"],
                "avg_rating": 4.6,
                "total_downloads": 1100,
            },
            {
                "name": "notification-sender",
                "display_name": "Notification Sender",
                "description": "Send notifications via email, Slack, and WeChat. Supports templated messages and delivery tracking.",
                "package_type": "skill",
                "author": "workflow-team",
                "author_id": "user_team",
                "category": "Integration",
                "tags": ["email", "slack", "wechat", "notification"],
                "avg_rating": 4.2,
                "total_downloads": 850,
            },
            {
                "name": "compliance-checker",
                "display_name": "Compliance Checker",
                "description": "Rule engine + LLM compliance checking for GDPR, HIPAA, and custom rule sets. Generates compliance reports with remediation suggestions.",
                "package_type": "skill",
                "author": "workflow-team",
                "author_id": "user_team",
                "category": "AI & NLP",
                "tags": ["compliance", "gdpr", "hipaa", "audit"],
                "avg_rating": 4.4,
                "total_downloads": 520,
            },
            {
                "name": "custom-api-connector",
                "display_name": "Custom API Connector",
                "description": "Generic REST API connector node with OAuth2, API key, and basic auth support. Configurable request/response mapping.",
                "package_type": "node",
                "author": "community",
                "author_id": "user_community",
                "category": "Integration",
                "tags": ["api", "rest", "oauth", "connector"],
                "avg_rating": 4.1,
                "total_downloads": 430,
            },
            {
                "name": "vector-search-node",
                "display_name": "Vector Search Node",
                "description": "Dedicated vector similarity search node supporting Milvus, Pinecone, and Weaviate backends with configurable top-k and filtering.",
                "package_type": "node",
                "author": "community",
                "author_id": "user_community",
                "category": "AI & NLP",
                "tags": ["vector", "search", "embedding", "rag"],
                "avg_rating": 4.0,
                "total_downloads": 310,
            },
            {
                "name": "scheduler-plugin",
                "display_name": "Workflow Scheduler",
                "description": "Cron-based workflow scheduling plugin. Supports recurring runs, timezone configuration, and calendar-based triggers.",
                "package_type": "plugin",
                "author": "community",
                "author_id": "user_community",
                "category": "Automation",
                "tags": ["cron", "schedule", "automation", "trigger"],
                "avg_rating": 4.8,
                "total_downloads": 720,
            },
            {
                "name": "language-translator",
                "display_name": "Language Translator",
                "description": "Multi-language translation skill using LLM or dedicated translation APIs. Supports batch translation and language detection.",
                "package_type": "skill",
                "author": "community",
                "author_id": "user_community",
                "category": "AI & NLP",
                "tags": ["translation", "i18n", "language", "llm"],
                "avg_rating": 4.3,
                "total_downloads": 590,
            },
            {
                "name": "database-query-node",
                "display_name": "Database Query Node",
                "description": "Execute SQL queries against PostgreSQL, MySQL, and SQLite databases. Supports parameterized queries and result formatting.",
                "package_type": "node",
                "author": "community",
                "author_id": "user_community",
                "category": "Data Processing",
                "tags": ["sql", "database", "query", "postgresql"],
                "avg_rating": 4.5,
                "total_downloads": 880,
            },
            {
                "name": "image-describer",
                "display_name": "Image Describer",
                "description": "Generate detailed descriptions of images using multimodal LLMs. Supports OCR, object detection, and scene understanding.",
                "package_type": "skill",
                "author": "community",
                "author_id": "user_community",
                "category": "AI & NLP",
                "tags": ["image", "vision", "ocr", "multimodal"],
                "avg_rating": 4.1,
                "total_downloads": 340,
            },
        ]

        for pkg_data in demo_packages:
            name = pkg_data["name"]
            self._packages[name] = PackageEntry(
                package_id=f"pkg_{uuid.uuid4().hex[:12]}",
                name=name,
                display_name=pkg_data["display_name"],  # type: ignore[arg-type]
                description=pkg_data["description"],  # type: ignore[arg-type]
                package_type=PackageType(pkg_data["package_type"]),  # type: ignore[arg-type]
                author=pkg_data["author"],  # type: ignore[arg-type]
                author_id=pkg_data["author_id"],  # type: ignore[arg-type]
                category=pkg_data["category"],  # type: ignore[arg-type]
                tags=pkg_data.get("tags", []),  # type: ignore[arg-type]
                status=PackageStatus.APPROVED,
                current_version="1.0.0",
                versions=[PackageVersion(version="1.0.0", published_at=now, changelog="Initial release")],
                total_downloads=pkg_data.get("total_downloads", 0),  # type: ignore[arg-type]
                avg_rating=pkg_data.get("avg_rating", 0.0),  # type: ignore[arg-type]
                verified=pkg_data["author"] == "workflow-team",
                created_at=now,
                updated_at=now,
            )


# Singleton instance
registry = PackageRegistry()
