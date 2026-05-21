"""Shared pytest fixtures + marker gating."""

from __future__ import annotations

import os

import pytest


def _has_integration() -> bool:
    return os.environ.get("EM_INTEGRATION") == "1"


def _has_e2e() -> bool:
    return os.environ.get("EM_E2E") == "1" and os.environ.get("EM_ALLOW_COMMIT") == "1"


def pytest_collection_modifyitems(config, items):
    skip_integration = pytest.mark.skip(reason="set EM_INTEGRATION=1 to run")
    skip_e2e = pytest.mark.skip(reason="set EM_E2E=1 + EM_ALLOW_COMMIT=1 to run")
    for item in items:
        if "integration" in item.keywords and not _has_integration():
            item.add_marker(skip_integration)
        if "e2e" in item.keywords and not _has_e2e():
            item.add_marker(skip_e2e)
