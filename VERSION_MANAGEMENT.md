# Version Management Guide

This project uses a centralized version management system. You only need to change the version in **ONE place** and all files update automatically.

## Quick Start

### Option 1: Update Version (Recommended)

```bash
# Change version to 0.3.0
python3 scripts/update_version.py 0.3.0
```

This will automatically update:
- ✅ `VERSION` file
- ✅ `pyproject.toml`
- ✅ `package.json`
- ✅ `src/speiihosting/__init__.py`
- ✅ `README.md`
- ✅ `USERGUIDE.md`
- ✅ `CHANGELOG.md` (verification only)

### Option 2: Interactive Mode

```bash
python3 scripts/update_version.py
```

Then choose:
1. Update all files from VERSION file
2. Set new version
3. Check version consistency
4. Exit

### Option 3: Check Version Consistency

```bash
# Verify all files have matching versions
python3 scripts/update_version.py --check
```

---

## How It Works

### The VERSION File (Single Source of Truth)

```
VERSION
```

Contains only: `0.2.0`

This is the **only file you need to edit manually**.

### Files That Get Updated Automatically

| File | What Gets Updated |
|------|-------------------|
| `VERSION` | The version number itself |
| `pyproject.toml` | `version = "0.2.0"` |
| `package.json` | `"version": "0.2.0"` |
| `src/speiihosting/__init__.py` | `__version__ = "0.2.0"` |
| `README.md` | Hidden marker comment |
| `USERGUIDE.md` | `Version 0.2.0` |
| `CHANGELOG.md` | Version check only |

---

## Complete Release Workflow

### Step 1: Update CHANGELOG First (Manual)

Edit `CHANGELOG.md` and add your release notes.

### Step 2: Run Version Update Script

```bash
python3 scripts/update_version.py 0.3.0
```

### Step 3: Verify Changes

```bash
python3 scripts/update_version.py --check
```

### Step 4: Commit and Tag

```bash
git add -A
git commit -m "Release v0.3.0"
git tag -a v0.3.0 -m "Release version 0.3.0"
git push origin main --tags
```

---

## Version Format

Always use **Semantic Versioning**: `MAJOR.MINOR.PATCH`

Examples:
- ✅ `0.2.0`
- ✅ `1.0.0`
- ❌ `0.2` (missing patch)
- ❌ `v0.2.0` (no v prefix)

---

## Summary

**Only change the VERSION file, then run the script!**

```bash
echo "0.3.0" > VERSION
python3 scripts/update_version.py
python3 scripts/update_version.py --check
```
