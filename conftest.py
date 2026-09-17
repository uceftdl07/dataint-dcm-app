"""Root pytest configuration for DCM monorepo.

This file ensures proper module resolution across the monorepo structure.
Each package directory is added to sys.path so tests can import their respective modules.
"""

import sys
from pathlib import Path

# Get the packages directory
packages_dir = Path(__file__).parent / "packages"

# Add each package to sys.path for proper imports in tests
if packages_dir.exists():
    for package in sorted(packages_dir.iterdir()):
        if package.is_dir() and (package / "pyproject.toml").exists():
            # Insert at position 0 to prioritize over installed versions
            sys.path.insert(0, str(package))

