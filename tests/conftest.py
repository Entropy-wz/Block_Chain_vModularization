import pytest
import os
import sys
from pathlib import Path

# Ensure the root project directory is in the PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

@pytest.fixture
def mock_rng():
    import random
    return random.Random(42)
