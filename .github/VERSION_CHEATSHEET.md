# Version Update Cheat Sheet

## TL;DR

```bash
# Bump version (one command does it all)
python3 scripts/update_version.py 0.3.0

# Or with Make
make release VERSION=0.3.0
```

## All Commands

| Task | Command | Result |
|------|---------|--------|
| **Check versions** | `make version-check` | Verify all files match |
| **Update version** | `python3 scripts/update_version.py 0.3.0` | Update all files to 0.3.0 |
| **Update version (Make)** | `make release VERSION=0.3.0` | Same + release checklist |
| **Interactive mode** | `python3 scripts/update_version.py` | Menu-driven |
| **Get help** | `python3 scripts/update_version.py --help` | Show usage |

## Files Updated Automatically

- ✅ `VERSION`
- ✅ `pyproject.toml` 
- ✅ `package.json`
- ✅ `src/speiihosting/__init__.py`
- ✅ `README.md`
- ✅ `USERGUIDE.md`
- ℹ️ `CHANGELOG.md` (verified, not auto-updated)

## Release Process

1. **Update CHANGELOG.md** (manual)
   ```bash
   vim CHANGELOG.md  # Add release notes
   ```

2. **Bump version**
   ```bash
   python3 scripts/update_version.py 0.3.0
   ```

3. **Verify**
   ```bash
   make version-check
   git diff
   ```

4. **Commit & tag**
   ```bash
   git commit -am "Release v0.3.0"
   git tag -a v0.3.0 -m "Release 0.3.0"
   git push origin main --tags
   ```

## Version Rules

- ✅ `0.2.0` (correct)
- ✅ `1.0.0` (correct)
- ❌ `0.2` (missing patch)
- ❌ `v0.2.0` (no 'v' prefix in VERSION file)

## Examples

**Patch release (bug fix):**
```bash
python3 scripts/update_version.py 0.2.1
```

**Minor release (new features):**
```bash
python3 scripts/update_version.py 0.3.0
```

**Major release (breaking changes):**
```bash
python3 scripts/update_version.py 1.0.0
```

## Troubleshooting

**Problem:** "Version mismatch"
**Solution:** Run `python3 scripts/update_version.py` without arguments

**Problem:** "Pattern not found"
**Solution:** Check the file still has the version marker

**Problem:** Script hangs
**Solution:** Use non-interactive mode: `python3 scripts/update_version.py 0.3.0`

---

**Full docs:** [VERSION_MANAGEMENT.md](../../VERSION_MANAGEMENT.md)
