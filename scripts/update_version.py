#!/usr/bin/env python3
"""
Centralized Version Management Script

Updates version across all project files from a single VERSION file.

Usage:
    python scripts/update_version.py           # Read from VERSION file
    python scripts/update_version.py 0.3.0     # Set new version
    python scripts/update_version.py --check   # Verify all versions match
"""

import re
import sys
from pathlib import Path
from datetime import date
from typing import List, Tuple


class VersionManager:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.version_file = project_root / "VERSION"
        
        # Define all files that need version updates
        self.version_locations = [
            # Python package
            {
                "file": "pyproject.toml",
                "pattern": r'version = "([^"]+)"',
                "replacement": r'version = "{version}"',
            },
            {
                "file": "src/speiihosting/__init__.py",
                "pattern": r'__version__ = "([^"]+)"',
                "replacement": r'__version__ = "{version}"',
            },
            {
                "file": "package.json",
                "pattern": r'"version": "([^"]+)"',
                "replacement": r'"version": "{version}"',
            },
            # Documentation files
            {
                "file": "README.md",
                "pattern": r'<!-- version:(\d+\.\d+\.\d+) -->',
                "replacement": r'<!-- version:{version} -->',
            },
            {
                "file": "USERGUIDE.md",
                "pattern": r'Version (\d+\.\d+\.\d+)',
                "replacement": r'Version {version}',
            },
            {
                "file": "CHANGELOG.md",
                "pattern": r'## \[(\d+\.\d+\.\d+)\]',
                "replacement": r'## [{version}]',
                "check_only": True,  # Just verify, don't auto-update
            },
        ]

    def read_version_file(self) -> str:
        """Read version from VERSION file."""
        if not self.version_file.exists():
            raise FileNotFoundError(f"VERSION file not found at {self.version_file}")
        
        version = self.version_file.read_text().strip()
        if not re.match(r'^\d+\.\d+\.\d+$', version):
            raise ValueError(f"Invalid version format: {version}. Expected: X.Y.Z")
        
        return version

    def write_version_file(self, version: str):
        """Write version to VERSION file."""
        if not re.match(r'^\d+\.\d+\.\d+$', version):
            raise ValueError(f"Invalid version format: {version}. Expected: X.Y.Z")
        
        self.version_file.write_text(version + "\n")
        print(f"✓ Updated VERSION file: {version}")

    def update_file(self, location: dict, new_version: str) -> Tuple[bool, str]:
        """Update version in a single file."""
        file_path = self.project_root / location["file"]

        if not file_path.exists():
            if location.get("optional"):
                return True, f"⊘ Skipped {location['file']} (optional, not found)"
            return False, f"✗ File not found: {location['file']}"

        content = file_path.read_text()
        pattern = location["pattern"]

        # Check-only mode (just verify version exists)
        if location.get("check_only"):
            if re.search(pattern, content):
                match = re.search(pattern, content)
                found_version = match.group(1) if match.groups() else None
                if found_version == new_version:
                    return True, f"✓ {location['file']}: {found_version}"
                else:
                    return False, f"✗ {location['file']}: {found_version or 'not found'} (expected: {new_version})"
            return False, f"✗ Pattern not found in {location['file']}"

        # Check if version already exists (for changelog)
        if location.get("skip_if_exists"):
            if new_version in content:
                return True, f"⊘ Skipped {location['file']} (version already exists)"

        # Prepare replacement
        replacement = location["replacement"].format(
            version=new_version,
            date=date.today().isoformat()
        )

        # Check if pattern exists
        if not re.search(pattern, content):
            return False, f"✗ Pattern not found in {location['file']}: {pattern}"

        # Replace version
        new_content = re.sub(pattern, replacement, content, count=1)

        if new_content == content:
            return True, f"⊘ No change needed in {location['file']}"

        file_path.write_text(new_content)
        return True, f"✓ Updated {location['file']}"

    def update_all(self, new_version: str) -> bool:
        """Update version in all files."""
        print(f"\n📝 Updating version to {new_version}\n")
        
        results: List[Tuple[bool, str]] = []
        
        for location in self.version_locations:
            success, message = self.update_file(location, new_version)
            results.append((success, message))
            print(f"  {message}")
        
        # Update VERSION file last
        self.write_version_file(new_version)
        
        # Summary
        print("\n" + "=" * 60)
        success_count = sum(1 for s, _ in results if s)
        total_count = len(results)
        
        if all(s for s, _ in results):
            print(f"✅ All files updated successfully ({success_count}/{total_count})")
            return True
        else:
            print(f"⚠️  Some files failed ({success_count}/{total_count})")
            return False

    def check_versions(self) -> bool:
        """Check if all versions match the VERSION file."""
        expected_version = self.read_version_file()
        print(f"\n🔍 Checking versions (expected: {expected_version})\n")
        
        mismatches = []
        
        for location in self.version_locations:
            file_path = self.project_root / location["file"]
            
            if not file_path.exists():
                if location.get("optional"):
                    print(f"  ⊘ Skipped {location['file']} (optional, not found)")
                    continue
                else:
                    print(f"  ✗ File not found: {location['file']}")
                    mismatches.append(location["file"])
                    continue
            
            content = file_path.read_text()
            pattern = location["pattern"]
            match = re.search(pattern, content)
            
            if not match:
                print(f"  ⚠️  Pattern not found in {location['file']}")
                continue
            
            # Extract version from match
            if match.groups():
                found_version = match.group(1)
            else:
                found_version = match.group(0)
            
            # Check if it contains the expected version
            if expected_version in found_version:
                print(f"  ✓ {location['file']}: {found_version}")
            else:
                print(f"  ✗ {location['file']}: {found_version} (expected: {expected_version})")
                mismatches.append(location["file"])
        
        print("\n" + "=" * 60)
        if not mismatches:
            print("✅ All versions are consistent!")
            return True
        else:
            print(f"❌ Version mismatches found in {len(mismatches)} file(s):")
            for file in mismatches:
                print(f"   - {file}")
            print("\nRun: python scripts/update_version.py")
            return False


def main():
    project_root = Path(__file__).parent.parent.resolve()
    manager = VersionManager(project_root)
    
    # Parse arguments
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        
        if arg in ["--check", "-c"]:
            # Check mode
            success = manager.check_versions()
            sys.exit(0 if success else 1)
        
        elif arg in ["--help", "-h"]:
            print(__doc__)
            sys.exit(0)
        
        else:
            # Set new version
            new_version = arg
            success = manager.update_all(new_version)
            sys.exit(0 if success else 1)
    
    else:
        # Update from VERSION file
        current_version = manager.read_version_file()
        print(f"Current version in VERSION file: {current_version}")
        print("\nOptions:")
        print("  1. Update all files from VERSION file")
        print("  2. Set new version")
        print("  3. Check version consistency")
        print("  4. Exit")
        
        choice = input("\nEnter choice [1-4]: ").strip()
        
        if choice == "1":
            success = manager.update_all(current_version)
            sys.exit(0 if success else 1)
        
        elif choice == "2":
            new_version = input("Enter new version (X.Y.Z): ").strip()
            success = manager.update_all(new_version)
            sys.exit(0 if success else 1)
        
        elif choice == "3":
            success = manager.check_versions()
            sys.exit(0 if success else 1)
        
        else:
            print("Cancelled.")
            sys.exit(0)


if __name__ == "__main__":
    main()
