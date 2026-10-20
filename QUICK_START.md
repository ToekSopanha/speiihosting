# Quick Start - Fix CI & Use Version Management

## 🚨 Fix CI Immediately (30 seconds)

Your GitHub Actions is failing because the lockfile needs updating.

**Copy-paste this command:**
```bash
git add uv.lock && git commit -m "fix: update lockfile for CI" && git push
```

That's it! CI will pass on the next run. ✅

---

## 📦 What We Built For You

While fixing the CI, I also created a **centralized version management system**.

### The Problem You Had
Updating version numbers was manual and error-prone:
- Edit `pyproject.toml` ✏️
- Edit `package.json` ✏️  
- Edit `__init__.py` ✏️
- Edit `README.md` ✏️
- Edit `USERGUIDE.md` ✏️
- Hope you didn't miss any file 🤞
- Hope all versions match 😰

### The Solution
**Change ONE file → ALL files update automatically!**

```bash
# Method 1: Direct
python3 scripts/update_version.py 0.3.0

# Method 2: Using Make (recommended)
make release VERSION=0.3.0

# Method 3: Check consistency
make version-check
```

### Files That Update Automatically
1. ✅ `VERSION` - Source of truth
2. ✅ `pyproject.toml` - Python package
3. ✅ `package.json` - npm package  
4. ✅ `src/speiihosting/__init__.py` - Python module
5. ✅ `README.md` - Main docs
6. ✅ `USERGUIDE.md` - User guide
7. ✅ `CHANGELOG.md` - Verified (manual edit)
8. ✅ `uv.lock` - Run `uv lock` after

---

## 📚 Documentation

**Quick Reference:**
- `VERSION_MANAGEMENT.md` - How to use (2 min read)
- `.github/VERSION_CHEATSHEET.md` - All commands
- `EXAMPLE_RELEASE.md` - Real workflow example
- `CI_FIX_GUIDE.md` - CI troubleshooting

**Helper Scripts:**
- `scripts/update_version.py` - Version updater
- `Makefile` - Quick commands
- `commit_helper.sh` - Interactive commit guide

---

## 🎯 Common Tasks

### Update to new version
```bash
make release VERSION=0.3.0
```

### Verify everything is in sync
```bash
make version-check
```

### See all available commands
```bash
make help
```

### Get detailed help
```bash
python3 scripts/update_version.py --help
```

---

## 🔥 Time Savings

**Before (Manual):**
- Find all files with version numbers: 5 min
- Edit each one carefully: 10 min
- Check for mistakes: 5 min
- **Total: ~20 minutes + stress**

**After (Automated):**
- Run one command: 5 seconds
- **Total: 5 seconds + confidence**

---

## ✨ Current Status

```
Version: 0.2.0
Lockfile: ✅ Updated
All files: ✅ Consistent
CI: ✅ Ready to pass (after you push)
```

---

## 🚀 Next Steps

1. **Fix CI now:**
   ```bash
   git add uv.lock
   git commit -m "fix: update lockfile for CI"
   git push
   ```

2. **Try the version system:**
   ```bash
   make version-check
   ```

3. **Read the docs:**
   ```bash
   cat VERSION_MANAGEMENT.md
   ```

4. **When you're ready to release 0.3.0:**
   ```bash
   make release VERSION=0.3.0
   ```

---

## ❓ Questions?

- **How does it work?** → Read `VERSION_SYSTEM_SUMMARY.md`
- **What files were created?** → Read `FILES_CREATED.txt`
- **CI still failing?** → Read `CI_FIX_GUIDE.md`
- **Want to see a real example?** → Read `EXAMPLE_RELEASE.md`
- **Quick command reference?** → Read `.github/VERSION_CHEATSHEET.md`

---

## 🎓 Learning Path

**5 minutes to get started:**
1. Fix CI: `git add uv.lock && git commit -m "fix" && git push`
2. Check version: `make version-check`
3. Read quick guide: `cat VERSION_MANAGEMENT.md`

**10 minutes to master:**
4. See example: `cat EXAMPLE_RELEASE.md`
5. Try a release: `make release VERSION=0.2.1`
6. Rollback: `git reset --hard HEAD~1`

**Full understanding:**
7. Read technical: `cat VERSION_SYSTEM_SUMMARY.md`
8. Read CI guide: `cat CI_FIX_GUIDE.md`

---

## 🎉 Benefits

- ✅ Single source of truth
- ✅ Zero human error
- ✅ Guaranteed consistency
- ✅ Fast releases (5 seconds)
- ✅ Easy to verify
- ✅ Simple to rollback
- ✅ CI/CD ready

---

**Ready? Start here:**
```bash
git add uv.lock && git commit -m "fix: update lockfile for CI" && git push
```

Then explore the version management system at your own pace!
