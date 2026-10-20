#!/bin/bash

echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║                   COMMIT HELPER FOR CI FIX                           ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo ""

echo "📋 Current changes to be committed:"
echo ""
git status --short
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Choose commit strategy:"
echo ""
echo "1) Quick fix - Just commit uv.lock to fix CI (recommended)"
echo "2) Single commit - All changes together"
echo "3) Separate commits - Clean history"
echo "4) Manual - Show me the commands"
echo "5) Cancel"
echo ""
read -p "Enter choice [1-5]: " choice

case $choice in
    1)
        echo ""
        echo "🚀 Quick fix - Committing uv.lock to fix CI..."
        git add uv.lock
        git commit -m "fix: update uv.lock to fix CI"
        echo ""
        echo "✅ Done! Now push:"
        echo "   git push"
        ;;
    2)
        echo ""
        echo "🚀 Single commit - All changes..."
        git add .
        git commit -m "feat: add version management system and fix CI lockfile"
        echo ""
        echo "✅ Done! Now push:"
        echo "   git push"
        ;;
    3)
        echo ""
        echo "🚀 Separate commits..."
        echo ""
        echo "Commit 1: Version management system"
        git add VERSION Makefile scripts/update_version.py VERSION_MANAGEMENT.md VERSION_SYSTEM_SUMMARY.md EXAMPLE_RELEASE.md .github/VERSION_CHEATSHEET.md CHANGELOG.md FILES_CREATED.txt CI_FIX_GUIDE.md
        git commit -m "feat: add centralized version management system"
        echo ""
        echo "Commit 2: Documentation updates"
        git add README.md USERGUIDE.md
        git commit -m "docs: add version management documentation"
        echo ""
        echo "Commit 3: Lockfile and version fields"
        git add uv.lock pyproject.toml package.json src/speiihosting/__init__.py
        git commit -m "fix: update lockfile and version for CI compatibility"
        echo ""
        echo "✅ Done! Now push:"
        echo "   git push"
        ;;
    4)
        echo ""
        echo "📝 Manual commands:"
        echo ""
        echo "Quick fix:"
        echo "  git add uv.lock"
        echo "  git commit -m \"fix: update uv.lock to fix CI\""
        echo "  git push"
        echo ""
        echo "Or all at once:"
        echo "  git add ."
        echo "  git commit -m \"feat: add version management and fix CI\""
        echo "  git push"
        ;;
    5)
        echo ""
        echo "❌ Cancelled"
        exit 0
        ;;
    *)
        echo ""
        echo "❌ Invalid choice"
        exit 1
        ;;
esac
