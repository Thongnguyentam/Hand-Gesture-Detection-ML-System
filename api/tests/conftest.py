import os
import sys
from unittest.mock import AsyncMock, MagicMock
from fastapi.responses import JSONResponse
import pytest
from datetime import datetime, timezone

# Add the project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

# Setup test data
@pytest.fixture
def sample_inference_payload():
    return {"data": [[0.1, 0.2] for _ in range(21)]}  # 21 landmarks with x,y coordinates

@pytest.fixture
def mock_asl_service():
    mock_service = MagicMock()
    mock_service.is_ready.return_value = True
    
    mock_service.predict_from_landmarks = AsyncMock()
    current_time = datetime.now(timezone.utc)
    mock_service.predict_from_landmarks.return_value = JSONResponse(content={
        "prediction": "ASL B",
        "confidence": 0.95,
        "timestamp": current_time.isoformat(),
        "processing_time_ms": 10.5,
        "user_id": "anonymous"
    })
    return mock_service

# Ensure tracing is disabled during tests
@pytest.fixture(scope="session", autouse=True)
def disable_tracing():
    """Disable tracing for all tests to avoid connection errors."""
    os.environ["ENABLE_TRACING"] = "false"
    yield
    # Cleanup is not needed as the environment variable will be reset after tests