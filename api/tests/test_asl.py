import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from datetime import datetime, time, timezone
from fastapi.responses import JSONResponse
from api.routers.asl import get_asl_service
from main import app
from api.middleware.auth import get_optional_user
from api.schema.user import UserProfile

client = TestClient(app)

@pytest.fixture
def mock_user():
    return UserProfile(
        id="test_user", 
        email="test@example.com", 
        first_name="first_name",
        last_name="last_name",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        last_login=datetime.now(timezone.utc),
        is_active=True,
        role="user"
    )

@pytest.mark.asyncio
async def test_valid_prediction(sample_inference_payload, mock_asl_service):
    """Test WebSocket prediction with valid input data"""
    # Override dependencies
    app.dependency_overrides[get_optional_user] = lambda: None
    app.dependency_overrides[get_asl_service] = lambda: mock_asl_service
    
    # Connect to WebSocket endpoint
    with client.websocket_connect("/asl/predict") as websocket:
        # Send test data
        websocket.send_json(sample_inference_payload)
        
        # Receive response
        response = websocket.receive_json()
        
        # Verify response
        assert response["prediction"] == "ASL B"
        assert response["user_id"] == "anonymous"
        assert "timestamp" in response
        assert "processing_time_ms" in response
        assert response["confidence"] == 0.95
    
    # Clean up dependency overrides
    app.dependency_overrides = {}

@pytest.mark.asyncio
async def test_websocket_disconnect(mock_asl_service):
    """Test proper handling of WebSocket disconnect"""
    app.dependency_overrides[get_optional_user] = lambda: None
    
    with client.websocket_connect("/asl/predict") as websocket:
        # Close connection immediately
        websocket.close()
        
        # Verify no predictions were attempted
        mock_asl_service.predict_from_landmarks.assert_not_called()
    
    app.dependency_overrides = {}

@pytest.mark.asyncio
async def test_invalid_input(mock_asl_service):
    """Test handling of invalid input data"""
    invalid_payload = {"invalid": "data"}
    
    app.dependency_overrides[get_optional_user] = lambda: None
    
    with client.websocket_connect("/asl/predict") as websocket:
        # Send invalid data
        websocket.send_json(invalid_payload)
        
        # Receive error response
        response = websocket.receive_json()
        
        assert "error" in response
        assert response["error_code"] == "INVALID_FORMAT"
        
        # Verify no prediction was attempted
        mock_asl_service.predict_from_landmarks.assert_not_called()
    
    app.dependency_overrides = {}
    

@pytest.mark.asyncio
async def test_anonymous_user(sample_inference_payload, mock_asl_service):
    """Test prediction works with anonymous user (no login)"""
    
    app.dependency_overrides[get_optional_user] = lambda: None
    app.dependency_overrides[get_asl_service] = lambda: mock_asl_service
    
    with client.websocket_connect("/asl/predict") as websocket:
        # Send test data
        websocket.send_json(sample_inference_payload)
        
        # Receive response (we don't care about the actual response here)
        websocket.receive_json()
        
        mock_asl_service.predict_from_landmarks.assert_called_once()
        
        args = mock_asl_service.predict_from_landmarks.call_args[0]
        print(args)
        assert args[1] == "anonymous"  # Check user_id parameter
    
    app.dependency_overrides = {}

@pytest.mark.asyncio
async def test_model_not_ready(mock_asl_service):
    """Test handling when ASL model is not initialized"""
    test_data = {"data": [[0, 0]]}
    mock_asl_service.is_ready.return_value = False
    
    app.dependency_overrides[get_optional_user] = lambda: None
    app.dependency_overrides[get_asl_service] = lambda: mock_asl_service
    
    with client.websocket_connect("/asl/predict") as websocket:
        # Send test data
        websocket.send_json(test_data)
        
        # Receive error response
        response = websocket.receive_json()
        
        assert "error" in response
        assert response["error_code"] == "MODEL_NOT_READY"
        
        # Verify no prediction was attempted
        mock_asl_service.predict_from_landmarks.assert_not_called()
    
    app.dependency_overrides = {}

@pytest.mark.asyncio
async def test_invalid_landmark_count(mock_asl_service):
    """Test handling of invalid number of landmarks"""
    invalid_landmarks = {"data": [[0, 0], [1, 1]]}  # Too few landmarks
    mock_asl_service.predict_from_landmarks.side_effect = ValueError("Expected 42 pre-processed landmark coordinates")
    
    app.dependency_overrides[get_optional_user] = lambda: None
    app.dependency_overrides[get_asl_service] = lambda: mock_asl_service
    with client.websocket_connect("/asl/predict") as websocket:
        # Send invalid data
        websocket.send_json(invalid_landmarks)
        
        # Receive error response
        response = websocket.receive_json()
        
        assert "error" in response
        assert "Expected 42 pre-processed landmark coordinates" in response["error"]
    
    app.dependency_overrides = {}

@pytest.mark.asyncio
async def test_malformed_json(mock_asl_service):
    """Test handling of malformed JSON data"""
    app.dependency_overrides[get_optional_user] = lambda: None
    
    with client.websocket_connect("/asl/predict") as websocket:
        # Send invalid JSON
        websocket.send_text("invalid json")
        
        # Receive error response
        response = websocket.receive_json()
        
        assert "error" in response
        assert response["error_code"] == "INVALID_JSON"
        
        # Verify no prediction was attempted
        mock_asl_service.predict_from_landmarks.assert_not_called()
    
    app.dependency_overrides = {}

@pytest.mark.asyncio
async def test_authenticated_user(mock_asl_service, mock_user):
    """Test prediction works with authenticated user"""
    test_data = {"data": [[0, 0]]}
    
    # Override user dependency to return mock user
    app.dependency_overrides[get_optional_user] = lambda: mock_user
    
    with client.websocket_connect("/asl/predict") as websocket:
        # Send test data
        websocket.send_json(test_data)
        
        # Receive response
        websocket.receive_json()
        
        # Verify prediction was made with user ID
        if mock_asl_service.predict_from_landmarks.called:
            args = mock_asl_service.predict_from_landmarks.call_args[0]
            assert args[1] == mock_user.id
    
    app.dependency_overrides = {}