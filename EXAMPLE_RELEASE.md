# Example: Complete Release Workflow

This document shows a real-world example of releasing version 0.3.0.

## Before: Manual Process (Error-Prone)

```bash
# Old way: Update 6+ files manually
vim pyproject.toml        # Change version = "0.2.0" to "0.3.0"
vim package.json          # Change "version": "0.2.0" to "0.3.0"
vim src/speiihosting/__init__.py  # Change __version__ = "0.2.0" to "0.3.0"
vim README.md             # Find and update version
vim USERGUIDE.md          # Find and update version
vim CHANGELOG.md          # Add release section

# Easy to forget a file!
# Easy to make typos!
# Time consuming!
```

## After: Automated Process (One Command)

### Step 1: Update CHANGELOG.md

```bash
vim CHANGELOG.md
```

Add this section at the top:

```markdown
## [0.3.0] - 2026-11-15

### Added
- New container isolation mode with Podman
- Health check retry logic
- Automatic recovery from network failures

### Changed
- Improved logging format with timestamps
- Updated dependency versions

### Fixed
- Windows path handling in deployment
- Race condition in health monitoring
```

Save and exit.

### Step 2: Run Version Update

```bash
# Option A: Direct command
python3 scripts/update_version.py 0.3.0

# Option B: Using Make
make release VERSION=0.3.0
```

**Output:**
```
📝 Updating version to 0.3.0

  ✓ Updated pyproject.toml
  ✓ Updated src/speiihosting/__init__.py
  ✓ Updated package.json
  ✓ Updated README.md
  ✓ Updated USERGUIDE.md
  ✓ CHANGELOG.md: 0.3.0
✓ Updated VERSION file: 0.3.0

============================================================
✅ All files updated successfully (6/6)
```

### Step 3: Verify Changes

```bash
# Check version consistency
make version-check
```

**Output:**
```
🔍 Checking versions (expected: 0.3.0)

  ✓ pyproject.toml: 0.3.0
  ✓ src/speiihosting/__init__.py: 0.3.0
  ✓ package.json: 0.3.0
  ✓ README.md: 0.3.0
  ✓ USERGUIDE.md: 0.3.0
  ✓ CHANGELOG.md: 0.3.0

✅ All versions are consistent!
```

### Step 4: Review Git Changes

```bash
git diff
```

**Output shows:**
```diff
diff --git a/VERSION b/VERSION
-0.2.0
+0.3.0

diff --git a/pyproject.toml b/pyproject.toml
-version = "0.2.0"
+version = "0.3.0"

diff --git a/package.json b/package.json
-  "version": "0.2.0",
+  "version": "0.3.0",

diff --git a/src/speiihosting/__init__.py b/src/speiihosting/__init__.py
-__version__ = "0.2.0"
+__version__ = "0.3.0"

... (README.md, USERGUIDE.md changes)
```

### Step 5: Commit and Tag

```bash
# Stage all version changes
git add VERSION pyproject.toml package.json src/ README.md USERGUIDE.md CHANGELOG.md

# Commit
git commit -m "Release v0.3.0

- Added container isolation with Podman
- Improved health checks
- Fixed Windows deployment issues
"

# Create annotated tag
git tag -a v0.3.0 -m "Release version 0.3.0"

# Push to remote
git push origin main
git push origin v0.3.0
```

### Step 6: Build and Publish (When Ready)

```bash
# Build Python package
python -m build

# Build npm package
npm pack

# Test installation
pip install dist/speiihosting-0.3.0-*.whl
# OR
npm install -g speiihosting-0.3.0.tgz

# Publish (when ready)
# twine upload dist/*
# npm publish
```

## Time Saved

| Task | Manual | Automated | Savings |
|------|--------|-----------|---------|
| Edit files | 5 min | 0 sec | 5 min |
| Find all version refs | 3 min | 0 sec | 3 min |
| Fix typos/mistakes | 2 min | 0 sec | 2 min |
| Verify consistency | 5 min | 5 sec | ~5 min |
| **Total** | **15 min** | **5 sec** | **~15 min** |

Plus: **Zero errors**, **guaranteed consistency**, **repeatable process**.

## Rollback Example

If you need to revert:

```bash
# Revert to previous version
echo "0.2.0" > VERSION
python3 scripts/update_version.py 0.2.0

# Or use git
git revert HEAD
```

## Real-World Workflow

### Developer's Daily Usage

```bash
# Monday: Start new feature branch
git checkout -b feature/new-feature

# ... develop feature ...

# Friday: Ready to merge
git checkout main
git pull
git merge feature/new-feature

# Prepare release
vim CHANGELOG.md  # Add notes
make release VERSION=0.3.0
git push origin main --tags
```

### Release Manager's Checklist

- [ ] All tests passing: `make test`
- [ ] Linting clean: `make lint`
- [ ] CHANGELOG updated with all changes
- [ ] Version bumped: `make release VERSION=X.Y.Z`
- [ ] Version consistency verified: `make version-check`
- [ ] Changes reviewed: `git diff`
- [ ] Committed and tagged
- [ ] Pushed to remote
- [ ] GitHub release created
- [ ] PyPI/npm published
- [ ] Documentation deployed

## Edge Cases Handled

### Patch Release (0.2.1)

```bash
make release VERSION=0.2.1
```

Updates all files from 0.2.0 → 0.2.1

### Major Release (1.0.0)

```bash
make release VERSION=1.0.0
```

Updates all files from 0.x.x → 1.0.0

### Beta/RC Releases

For pre-releases, use git tags only:

```bash
# Don't change VERSION file
# Just tag the commit
git tag v0.3.0-beta.1
git push origin v0.3.0-beta.1
```

## Conclusion

**Before:** Error-prone, time-consuming, easy to forget files  
**After:** One command, guaranteed consistency, fast and reliable

```bash
# That's literally all you need:
make release VERSION=0.3.0
```

---

**Time saved per release:** ~15 minutes  
**Errors prevented:** Infinite  
**Developer happiness:** 📈📈📈
