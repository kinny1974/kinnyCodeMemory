"""Shared fixtures for KinnyCode Memory tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


@pytest.fixture
def sample_project_id():
    """Sample valid project ID."""
    return "test-project-123"


@pytest.fixture
def sample_mscore_data():
    """Sample data for M_score calculations."""
    return {
        "similarity": 0.85,
        "days_since_access": 15.0,
        "access_frequency": 3,
        "lambda_days": 30.0,
        "w_freq": 0.5,
    }
