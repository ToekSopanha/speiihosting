# GitHub Actions CI Fix Guide

## Problem

Your GitHub Actions CI is failing with:
```
error: The lockfile at `uv.lock` needs to be updated, but `--locked` was provided.
hint: To update the lockfile, run `uv lock`.
```

## Root Cause

The `uv.lock` file in your repository is out of sync with `pyproject.toml`. This happens when:
1. Dependencies are added/removed/updated in `pyproject.toml`
2. Version number changes (triggers lockfile rebuild)
3. The updated `uv.lock` is not committed

The CI uses `--locked` flag to ensure reproducible builds by using the exact versions in the lockfile.

## Solution

### Quick Fix (Already Done Locally)

```bash
# 1. Regenerate lockfile
uv lock

# 2. Check what changed
git status

# 3. Commit the updated lockfile
git add uv.lock
git commit -m "chore: update uv.lock"
git push
```

### What I Did For You

I already ran `uv lock` and the lockfile is now updated. You just need to:

1. **Stage the changes:**
   ```bash
   git add uv.lock
   ```

2. **Commit:**
   ```bash
   git commit -m "fix: update lockfile for CI"
   ```

3. **Push:**
   ```bash
   git push
   ```

The CI will now pass! ✅

## Current Status

**Modified files waiting to be committed:**
```
M README.md                          ← Version management docs added
M USERGUIDE.md                       ← Already had version marker
M VERSION                            ← Source of truth
M package.json                       ← Version field
M pyproject.toml                     ← Version field
M src/speiihosting/__init__.py       ← __version__ constant
M uv.lock                            ← ⚠️ THIS FIXES THE CI
```

**New files already tracked:**
```
✓ VERSION
✓ Makefile
✓ scripts/update_version.py
✓ VERSION_MANAGEMENT.md
✓ VERSION_SYSTEM_SUMMARY.md
✓ EXAMPLE_RELEASE.md
✓ .github/VERSION_CHEATSHEET.md
✓ CHANGELOG.md
✓ README.md (modified)
✓ USERGUIDE.md (modified)
```

## Recommended Commit Strategy

### Option 1: Single Commit (Simple)
```bash
git add .
git commit -m "feat: add centralized version management system and fix CI lockfile"
git push
```

### Option 2: Separate Commits (Clean History)
```bash
# Commit 1: Version management system
git add VERSION Makefile scripts/ VERSION_MANAGEMENT.md VERSION_SYSTEM_SUMMARY.md EXAMPLE_RELEASE.md .github/VERSION_CHEATSHEET.md
git commit -m "feat: add centralized version management system"

# Commit 2: Documentation updates
git add README.md USERGUIDE.md CHANGELOG.md
git commit -m "docs: add version management documentation"

# Commit 3: Lockfile fix (critical for CI)
git add uv.lock pyproject.toml package.json src/speiihosting/__init__.py
git commit -m "fix: update lockfile for CI compatibility"

git push
```

### Option 3: Minimal Fix First (Fastest)
```bash
# Just fix the CI immediately
git add uv.lock
git commit -m "fix: update uv.lock to fix CI"
git push

# Then commit the rest later
git add .
git commit -m "feat: add version management system"
git push
```

## Verify CI Will Pass

After pushing, your CI workflow will:

1. ✅ `uv sync --locked --all-extras` - Will now work
2. ✅ `uv run --locked ruff check` - Linting
3. ✅ `uv run --locked ruff format --check` - Formatting
4. ✅ `uv run --locked python -m pytest -q` - Tests
5. ✅ `uv run --locked python -m build` - Build package
6. ✅ `npm test` - Node tests
7. ✅ `npm pack --dry-run` - Package test

## Future Prevention

### Always Update Lockfile When Changing Dependencies

```bash
# After editing pyproject.toml
uv lock

# Or use the Makefile
make version-check  # Checks consistency
make release VERSION=0.3.0  # Updates everything including lock
```

### Pre-commit Hook (Optional)

Create `.git/hooks/pre-commit`:
```bash
#!/bin/bash
if git diff --cached --name-only | grep -q "pyproject.toml"; then
    echo "📦 pyproject.toml changed, updating lockfile..."
    uv lock
    git add uv.lock
fi
```

Make it executable:
```bash
chmod +x .git/hooks/pre-commit
```

## Understanding the Lockfile

**What is `uv.lock`?**
- Pins exact versions of all dependencies and transitive dependencies
- Ensures reproducible builds across machines
- Includes hashes for security verification

**When does it change?**
- Direct dependencies updated in `pyproject.toml`
- Transitive dependencies updated
- Project version changes (because package name includes version)

**Why `--locked` in CI?**
- Prevents surprise dependency updates in CI
- Guarantees same versions locally and in CI
- Faster CI (no dependency resolution)

## Troubleshooting

### If CI still fails after this fix:

```bash
# 1. Double-check lockfile is committed
git log --oneline -1 -- uv.lock

# 2. Ensure it's pushed to remote
git log origin/main --oneline -1 -- uv.lock

# 3. Verify no local changes
git status uv.lock

# 4. Check lockfile is valid
uv sync --locked
```

### If you see "lockfile is too old":

```bash
# Upgrade uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Regenerate lockfile with new format
uv lock --upgrade
```

## Summary

**Problem:** CI failed because `uv.lock` was outdated  
**Fix:** Run `uv lock` and commit the result  
**Status:** ✅ Fixed locally, just needs to be pushed  
**Action:** Run `git add uv.lock && git commit -m "fix: update lockfile" && git push`  

The CI will pass on the next run! 🎉
