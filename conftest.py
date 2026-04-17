"""Pytest configuration — ensures project root is on sys.path."""

import sys
from pathlib import Path

# Add project root to sys.path so 'import scripts.xxx' works
project_root = Path(__file__).parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
