# =============================================================================
# tests/conftest.py — Test Configuration
# =============================================================================
# Adds the project root directory to sys.path so that test files can import
# application modules (app, database, auth, config) using bare module names,
# even when tests are run from the tests/ subdirectory.
# =============================================================================

import sys
import os

# Add the project root (parent of this tests/ directory) to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
