"""Marketplace API routes — search, publish, install, review packages."""

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from src.services.marketplace import registry

router = APIRouter(prefix="/marketplace", tags=["Marketplace"])


# ── Request Models ──

class PublishRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    display_name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=10, max_length=2000)
    type: str = Field(..., pattern=r"^(node|skill|plugin)$")
    category: str = Field(..., min_length=1)
    version: str = Field(default="0.1.0")
    changelog: str = ""
    tags: list[str] = Field(default_factory=list, max_length=10)
    icon: str = ""
    homepage: str = ""
    repository: str = ""
    license: str = "MIT"


class ReviewRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    title: str = Field(default="", max_length=200)
    comment: str = Field(default="", max_length=2000)


# ── Search & Browse ──

@router.get("/search")
async def search_packages(
    q: str = Query(default="", max_length=200),
    type: str = Query(default="", pattern=r"^(node|skill|plugin)?$"),
    category: str = "",
    sort: str = Query(default="downloads", pattern=r"^(downloads|rating|newest|name)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """Search marketplace packages with filters."""
    from src.services.marketplace import PackageType
    pkg_type = PackageType(type) if type else None
    result = registry.search(
        query=q,
        package_type=pkg_type,
        category=category,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return {"code": 0, "message": "success", "data": result}


@router.get("/categories")
async def list_categories() -> dict[str, Any]:
    """List all package categories."""
    cats = registry.get_categories()
    return {"code": 0, "message": "success", "data": cats}


@router.get("/featured")
async def featured_packages(limit: int = Query(default=6, ge=1, le=20)) -> dict[str, Any]:
    """Get featured/top packages."""
    items = registry.get_featured(limit)
    return {"code": 0, "message": "success", "data": items}


# ── Package CRUD ──

@router.get("/package/{name}")
async def get_package(name: str) -> dict[str, Any]:
    """Get package details."""
    pkg = registry.get_package(name)
    if not pkg:
        return {"code": 40401, "message": "Package not found", "data": None}
    data = registry._package_to_dict(pkg)
    data["reviews"] = registry.get_reviews(name)
    return {"code": 0, "message": "success", "data": data}


@router.post("/publish")
async def publish_package(req: PublishRequest) -> dict[str, Any]:
    """Publish a new package or new version."""
    # In production, author_id comes from auth token
    pkg = registry.publish(
        name=req.name,
        display_name=req.display_name,
        description=req.description,
        package_type=req.type,
        author="current-user",
        author_id="user_current",
        category=req.category,
        version=req.version,
        changelog=req.changelog,
        tags=req.tags,
        icon=req.icon,
        homepage=req.homepage,
        repository=req.repository,
        license=req.license,
    )
    return {"code": 0, "message": "Package published successfully", "data": registry._package_to_dict(pkg)}


@router.post("/install/{name}")
async def install_package(name: str) -> dict[str, Any]:
    """Install a package (record download)."""
    result = registry.install(name, user_id="user_current")
    if not result:
        return {"code": 40401, "message": "Package not found or not approved", "data": None}
    return {"code": 0, "message": "Package installed", "data": result}


# ── Reviews ──

@router.get("/package/{name}/reviews")
async def get_reviews(name: str) -> dict[str, Any]:
    """Get reviews for a package."""
    reviews = registry.get_reviews(name)
    return {"code": 0, "message": "success", "data": reviews}


@router.post("/package/{name}/reviews")
async def add_review(name: str, req: ReviewRequest) -> dict[str, Any]:
    """Add or update a review for a package."""
    review = registry.add_review(
        name=name,
        user_id="user_current",
        rating=req.rating,
        title=req.title,
        comment=req.comment,
    )
    if not review:
        return {"code": 40401, "message": "Package not found", "data": None}
    return {"code": 0, "message": "Review submitted", "data": {
        "review_id": review.review_id,
        "rating": review.rating,
        "title": review.title,
        "comment": review.comment,
        "created_at": review.created_at,
    }}
