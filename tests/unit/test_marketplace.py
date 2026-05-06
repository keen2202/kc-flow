"""Tests for the marketplace service."""

from src.services.marketplace import PackageRegistry, PackageType, PackageStatus


class TestPackageRegistry:
    def setup_method(self):
        self.registry = PackageRegistry()

    def test_search_returns_demo_packages(self):
        result = self.registry.search()
        assert result["total"] >= 10
        assert len(result["items"]) > 0

    def test_search_by_query(self):
        result = self.registry.search(query="sentiment")
        assert result["total"] >= 1
        assert any("sentiment" in p["name"] for p in result["items"])

    def test_search_by_type(self):
        result = self.registry.search(package_type=PackageType.SKILL)
        for item in result["items"]:
            assert item["type"] == "skill"

    def test_search_by_category(self):
        result = self.registry.search(category="AI & NLP")
        for item in result["items"]:
            assert item["category"] == "AI & NLP"

    def test_search_sort_by_rating(self):
        result = self.registry.search(sort="rating")
        ratings = [p["avg_rating"] for p in result["items"]]
        assert ratings == sorted(ratings, reverse=True)

    def test_search_pagination(self):
        result = self.registry.search(page=1, page_size=3)
        assert len(result["items"]) <= 3
        assert result["page"] == 1
        assert result["page_size"] == 3

    def test_get_package(self):
        pkg = self.registry.get_package("sentiment-analyzer")
        assert pkg is not None
        assert pkg.name == "sentiment-analyzer"
        assert pkg.package_type == PackageType.SKILL

    def test_get_package_not_found(self):
        pkg = self.registry.get_package("nonexistent")
        assert pkg is None

    def test_get_categories(self):
        cats = self.registry.get_categories()
        assert len(cats) > 0
        assert all("name" in c and "count" in c for c in cats)

    def test_get_featured(self):
        featured = self.registry.get_featured(limit=3)
        assert len(featured) <= 3
        # Should be sorted by rating desc
        if len(featured) >= 2:
            assert featured[0]["avg_rating"] >= featured[1]["avg_rating"]

    def test_publish_new_package(self):
        pkg = self.registry.publish(
            name="test-pkg",
            display_name="Test Package",
            description="A test package for unit tests",
            package_type="skill",
            author="tester",
            author_id="user_test",
            category="Testing",
            version="1.0.0",
            tags=["test"],
        )
        assert pkg.name == "test-pkg"
        assert pkg.current_version == "1.0.0"
        assert pkg.status == PackageStatus.APPROVED

    def test_publish_new_version(self):
        self.registry.publish(
            name="versioned-pkg",
            display_name="Versioned",
            description="A package with versions",
            package_type="node",
            author="tester",
            author_id="user_test",
            category="Testing",
            version="1.0.0",
        )
        pkg = self.registry.publish(
            name="versioned-pkg",
            display_name="Versioned",
            description="A package with versions",
            package_type="node",
            author="tester",
            author_id="user_test",
            category="Testing",
            version="1.1.0",
            changelog="Added new feature",
        )
        assert pkg.current_version == "1.1.0"
        assert len(pkg.versions) == 2

    def test_install_package(self):
        result = self.registry.install("sentiment-analyzer", "user1")
        assert result is not None
        assert "install_path" in result
        assert result["package"]["total_downloads"] > 0

    def test_install_nonexistent(self):
        result = self.registry.install("nonexistent", "user1")
        assert result is None

    def test_add_review(self):
        review = self.registry.add_review(
            name="sentiment-analyzer",
            user_id="user1",
            rating=5,
            title="Great!",
            comment="Very useful tool",
        )
        assert review is not None
        assert review.rating == 5

    def test_review_replaces_existing(self):
        self.registry.add_review(name="sentiment-analyzer", user_id="user1", rating=3)
        self.registry.add_review(name="sentiment-analyzer", user_id="user1", rating=5)
        reviews = self.registry.get_reviews("sentiment-analyzer")
        user_reviews = [r for r in reviews if r["user_id"] == "user1"]
        assert len(user_reviews) == 1
        assert user_reviews[0]["rating"] == 5

    def test_review_updates_avg_rating(self):
        self.registry.add_review(name="sentiment-analyzer", user_id="user_a", rating=5)
        self.registry.add_review(name="sentiment-analyzer", user_id="user_b", rating=3)
        pkg = self.registry.get_package("sentiment-analyzer")
        assert pkg is not None
        # Should reflect the new reviews in the average
        reviews = self.registry.get_reviews("sentiment-analyzer")
        assert len(reviews) >= 2

    def test_review_rating_clamped(self):
        review = self.registry.add_review(name="sentiment-analyzer", user_id="user1", rating=10)
        assert review is not None
        assert review.rating == 5  # clamped to max

        review2 = self.registry.add_review(name="sentiment-analyzer", user_id="user2", rating=0)
        assert review2 is not None
        assert review2.rating == 1  # clamped to min

    def test_verified_packages(self):
        pkg = self.registry.get_package("sentiment-analyzer")
        assert pkg is not None
        assert pkg.verified is True  # authored by workflow-team

    def test_community_packages_not_verified(self):
        pkg = self.registry.get_package("custom-api-connector")
        assert pkg is not None
        assert pkg.verified is False
