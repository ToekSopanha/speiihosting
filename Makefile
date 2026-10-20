.PHONY: version-check version-update release help build npm-build full-build clean test lint format

# Get current version from VERSION file
VERSION := $(shell cat VERSION 2>/dev/null || echo "unknown")

help:
	@echo "SpeiiHosting Version Management"
	@echo ""
	@echo "Current version: $(VERSION)"
	@echo ""
	@echo "Available commands:"
	@echo "  make version-check       Check version consistency across files"
	@echo "  make version-update      Update version across all files"
	@echo "  make build               Build Python wheel + sdist  →  dist/"
	@echo "  make npm-build           Build npm launcher          →  dist/speiihos.cjs"
	@echo "  make full-build          Build both Python and npm artefacts"
	@echo "  make release VERSION=X.Y.Z  Release new version"
	@echo ""
	@echo "Examples:"
	@echo "  make version-check"
	@echo "  make full-build"
	@echo "  make release VERSION=0.3.0"

version-check:
	@echo "Checking version consistency..."
	@python3 scripts/update_version.py --check

version-update:
	@echo "Updating version $(VERSION) across all files..."
	@python3 scripts/update_version.py $(VERSION)

release:
	@if [ -z "$(VERSION)" ]; then \
		echo "Error: VERSION not specified"; \
		echo "Usage: make release VERSION=0.3.0"; \
		exit 1; \
	fi
	@echo "Releasing version $(VERSION)..."
	@python3 scripts/update_version.py $(VERSION)
	@echo ""
	@echo "Version updated. Next steps:"
	@echo "  1. Review changes: git diff"
	@echo "  2. Update CHANGELOG.md manually"
	@echo "  3. Commit: git commit -am 'Release v$(VERSION)'"
	@echo "  4. Tag: git tag -a v$(VERSION) -m 'Release $(VERSION)'"
	@echo "  5. Push: git push origin main --tags"

test:
	@uv run --locked python -m pytest -q
	@npm test

lint:
	@uv run --locked ruff check src tests

format:
	@uv run --locked ruff format src tests

# Build Python wheel + sdist into dist/
build:
	@uv run --locked python -m build

# Build npm launcher into dist/speiihos.cjs
npm-build:
	@node scripts/build.cjs

# Build everything: Python artefacts + npm launcher
full-build: build npm-build

clean:
	@rm -rf dist/ build/ *.egg-info
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete

.DEFAULT_GOAL := help
