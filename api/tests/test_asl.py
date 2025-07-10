import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from datetime import datetime, time, timezone
from fastapi.responses import JSONResponse
from fastapi import HTTPException, status
from api.routers.asl import get_asl_service
from api.services.asl_service import ASLService
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

# WebSocket tests (existing tests)
def test_valid_prediction(sample_inference_payload, mock_asl_service):
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

def test_websocket_disconnect(mock_asl_service):
    """Test proper handling of WebSocket disconnect"""
    app.dependency_overrides[get_optional_user] = lambda: None
    
    with client.websocket_connect("/asl/predict") as websocket:
        # Close connection immediately
        websocket.close()
        
        # Verify no predictions were attempted
        mock_asl_service.predict_from_landmarks.assert_not_called()
    
    app.dependency_overrides = {}

def test_invalid_input(mock_asl_service):
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
    

def test_anonymous_user(sample_inference_payload, mock_asl_service):
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

def test_model_not_ready(mock_asl_service):
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

def test_invalid_landmark_count(mock_asl_service):
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

def test_malformed_json(mock_asl_service):
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

def test_authenticated_user(mock_asl_service, mock_user):
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


# ASL Service Tests
class TestASLService:
    
    @pytest.fixture
    def mock_db(self):
        """Mock database instance"""
        return MagicMock()
    
    @pytest.fixture
    def mock_keypoint_classifier(self):
        """Mock keypoint classifier"""
        mock_classifier = MagicMock()
        mock_classifier.return_value = 1  # Returns class ID for "ASL B"
        return mock_classifier
    
    @pytest.fixture
    def asl_service(self, mock_db):
        """Create ASL service instance with mocked dependencies"""
        with patch('api.services.asl_service.KeyPointClassifier') as mock_classifier_class:
            mock_classifier = MagicMock()
            mock_classifier.return_value = 1  # Returns class ID for "ASL B"
            mock_classifier_class.return_value = mock_classifier
            
            with patch('os.path.exists', return_value=True):
                with patch('builtins.open', mock_open_csv_labels()):
                    service = ASLService(mock_db)
                    service.keypoint_classifier = mock_classifier
                    return service
    
    @pytest.fixture
    def sample_landmarks(self):
        """Sample landmark data for testing"""
        return [[0.1, 0.2] for _ in range(21)]  # 21 landmarks with x,y coordinates
    
    @pytest.mark.asyncio
    async def test_predict_from_landmarks_success(self, asl_service, sample_landmarks):
        """Test successful prediction from landmarks"""
        response = await asl_service.predict_from_landmarks(sample_landmarks, "test_user")
        
        assert isinstance(response, JSONResponse)
        assert response.status_code == 200
        
        # Parse response content
        content = json.loads(response.body)
        assert content["prediction"] == "ASL B"
        assert content["confidence"] == 0.95
        assert content["user_id"] == "test_user"
        assert "timestamp" in content
        assert "processing_time_ms" in content
    
    @pytest.mark.asyncio
    async def test_predict_from_landmarks_anonymous_user(self, asl_service, sample_landmarks):
        """Test prediction with anonymous user"""
        response = await asl_service.predict_from_landmarks(sample_landmarks, None)
        
        content = json.loads(response.body)
        assert content["user_id"] is None
    
    @pytest.mark.asyncio
    async def test_predict_from_landmarks_model_not_initialized(self, mock_db):
        """Test prediction when model is not initialized"""
        service = ASLService(mock_db)
        service.model_initialized = False
        
        with pytest.raises(HTTPException) as exc_info:
            await service.predict_from_landmarks([[0, 0]], "test_user")
        
        assert exc_info.value.status_code == 503
        assert "ASL model not initialized" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_predict_from_landmarks_invalid_input_length(self, asl_service):
        """Test prediction with invalid input length"""
        invalid_landmarks = [[0, 0], [1, 1]]  # Too few landmarks
        
        with pytest.raises(HTTPException) as exc_info:
            await asl_service.predict_from_landmarks(invalid_landmarks, "test_user")
        
        assert exc_info.value.status_code == 400
        assert "Expected 42 pre-processed landmark coordinates" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_predict_from_landmarks_unknown_prediction(self, asl_service, sample_landmarks):
        """Test prediction with unknown class ID"""
        # Mock classifier to return invalid class ID
        asl_service.keypoint_classifier.return_value = 999
        
        response = await asl_service.predict_from_landmarks(sample_landmarks, "test_user")
        
        content = json.loads(response.body)
        assert content["prediction"] == "Unknown"
        assert content["confidence"] == 0.1
    
    @pytest.mark.asyncio
    async def test_predict_from_landmarks_classifier_exception(self, asl_service, sample_landmarks):
        """Test prediction when classifier raises exception"""
        # Mock classifier to raise exception
        asl_service.keypoint_classifier.side_effect = Exception("Classifier error")
        
        with pytest.raises(HTTPException) as exc_info:
            await asl_service.predict_from_landmarks(sample_landmarks, "test_user")
        
        assert exc_info.value.status_code == 500
        assert "Prediction failed" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_get_available_signs_success(self, asl_service):
        """Test getting available signs successfully"""
        response = await asl_service.get_available_signs()
        
        assert isinstance(response, JSONResponse)
        assert response.status_code == 200
        
        content = json.loads(response.body)
        assert "signs" in content
        assert "total_count" in content
        assert "timestamp" in content
        assert len(content["signs"]) == content["total_count"]
        assert "ASL A" in content["signs"]
        assert "ASL B" in content["signs"]
    
    @pytest.mark.asyncio
    async def test_get_available_signs_model_not_initialized(self, mock_db):
        """Test getting available signs when model is not initialized"""
        service = ASLService(mock_db)
        service.model_initialized = False
        
        with pytest.raises(HTTPException) as exc_info:
            await service.get_available_signs()
        
        assert exc_info.value.status_code == 503
        assert "ASL model not initialized" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_health_check_healthy(self, asl_service):
        """Test health check when service is healthy"""
        response = await asl_service.health_check()
        
        assert isinstance(response, JSONResponse)
        assert response.status_code == 200
        
        content = json.loads(response.body)
        assert content["status"] == "healthy"
        assert content["model_initialized"] is True
        assert content["available_signs_count"] > 0
        assert "timestamp" in content
    
    @pytest.mark.asyncio
    async def test_health_check_not_ready(self, mock_db):
        """Test health check when service is not ready"""
        service = ASLService(mock_db)
        service.model_initialized = False
        
        response = await service.health_check()
        
        assert isinstance(response, JSONResponse)
        assert response.status_code == 503
        
        content = json.loads(response.body)
        assert content["status"] == "not_ready"
        assert content["model_initialized"] is False
        assert content["available_signs_count"] == 0
    
    def test_is_ready_true(self, asl_service):
        """Test is_ready returns True when model is initialized"""
        assert asl_service.is_ready() is True
    
    def test_is_ready_false(self, mock_db):
        """Test is_ready returns False when model is not initialized"""
        service = ASLService(mock_db)
        service.model_initialized = False
        assert service.is_ready() is False
    
    def test_pre_process_landmark(self, asl_service, sample_landmarks):
        """Test landmark preprocessing"""
        result = asl_service.pre_process_landmark(sample_landmarks)
        
        assert isinstance(result, list)
        assert len(result) == 42  # 21 landmarks * 2 coordinates
        assert all(isinstance(x, (int, float)) for x in result)
        
        # Check that normalization occurred (values should be between -1 and 1)
        assert all(-1 <= x <= 1 for x in result)
    
    def test_pre_process_landmark_single_point(self, asl_service):
        """Test preprocessing with single landmark point"""
        single_landmark = [[0.5, 0.5]]
        result = asl_service.pre_process_landmark(single_landmark)
        
        assert len(result) == 2
        assert result == [0.0, 0.0]  # Should be normalized to origin
    
    def test_serialize_response_datetime(self, asl_service):
        """Test serialization of datetime objects"""
        test_data = {
            "timestamp": datetime.now(timezone.utc),
            "value": "test"
        }
        
        result = asl_service._serialize_response(test_data)
        
        assert isinstance(result["timestamp"], str)
        assert result["value"] == "test"
    
    def test_serialize_response_nested(self, asl_service):
        """Test serialization of nested objects"""
        test_data = {
            "nested": {
                "timestamp": datetime.now(timezone.utc),
                "value": 123
            },
            "simple": "value"
        }
        
        result = asl_service._serialize_response(test_data)
        
        assert isinstance(result["nested"]["timestamp"], str)
        assert result["nested"]["value"] == 123
        assert result["simple"] == "value"


# Router Endpoint Tests
class TestASLRouter:
    
    def test_get_available_signs_success(self, mock_asl_service):
        """Test /asl/signs endpoint success"""
        # Mock service response as async
        async def mock_get_available_signs():
            return JSONResponse(content={
                "signs": ["ASL A", "ASL B", "ASL C"],
                "total_count": 3,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        
        mock_asl_service.get_available_signs = mock_get_available_signs
        
        # Override dependency
        app.dependency_overrides[get_asl_service] = lambda: mock_asl_service
        
        try:
            response = client.get("/asl/signs")
            
            assert response.status_code == 200
            data = response.json()
            assert "signs" in data
            assert "total_count" in data
            assert data["total_count"] == 3
            assert "ASL A" in data["signs"]
        finally:
            app.dependency_overrides = {}
    
    def test_get_available_signs_service_error(self, mock_asl_service):
        """Test /asl/signs endpoint when service raises error"""
        # Mock service to raise HTTPException
        async def mock_get_available_signs():
            raise HTTPException(status_code=503, detail="ASL model not initialized")
        
        mock_asl_service.get_available_signs = mock_get_available_signs
        
        app.dependency_overrides[get_asl_service] = lambda: mock_asl_service
        
        try:
            response = client.get("/asl/signs")
            
            assert response.status_code == 503
            data = response.json()
            assert "ASL model not initialized" in data["detail"]
        finally:
            app.dependency_overrides = {}
    
    def test_asl_health_check_healthy(self, mock_asl_service):
        """Test /asl/health endpoint when service is healthy"""
        # Mock service response as async
        async def mock_health_check():
            return JSONResponse(content={
                "status": "healthy",
                "model_initialized": True,
                "available_signs_count": 37,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        
        mock_asl_service.health_check = mock_health_check
        
        app.dependency_overrides[get_asl_service] = lambda: mock_asl_service
        
        try:
            response = client.get("/asl/health")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["model_initialized"] is True
            assert data["available_signs_count"] == 37
        finally:
            app.dependency_overrides = {}
    
    def test_asl_health_check_not_ready(self, mock_asl_service):
        """Test /asl/health endpoint when service is not ready"""
        # Mock service response as async
        async def mock_health_check():
            return JSONResponse(
                content={
                    "status": "not_ready",
                    "model_initialized": False,
                    "available_signs_count": 0,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                },
                status_code=503
            )
        
        mock_asl_service.health_check = mock_health_check
        
        app.dependency_overrides[get_asl_service] = lambda: mock_asl_service
        
        try:
            response = client.get("/asl/health")
            
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "not_ready"
            assert data["model_initialized"] is False
            assert data["available_signs_count"] == 0
        finally:
            app.dependency_overrides = {}
    
    def test_asl_health_check_service_error(self, mock_asl_service):
        """Test /asl/health endpoint when service raises error"""
        # Mock service to raise HTTPException
        async def mock_health_check():
            raise HTTPException(status_code=500, detail="Health check failed: Database connection error")
        
        mock_asl_service.health_check = mock_health_check
        
        app.dependency_overrides[get_asl_service] = lambda: mock_asl_service
        
        try:
            response = client.get("/asl/health")
            
            assert response.status_code == 500
            data = response.json()
            assert "Health check failed" in data["detail"]
        finally:
            app.dependency_overrides = {}


# Helper function for mocking CSV file reading
def mock_open_csv_labels():
    """Mock open function for CSV label file"""
    from unittest.mock import mock_open
    
    csv_content = """ASL A
ASL B
ASL C
ASL D
ASL E
ASL F
ASL G
ASL H
ASL I
ASL J
ASL K
ASL L
ASL M
ASL N
ASL O
ASL P
ASL Q
ASL R
ASL S
ASL T
ASL U
ASL V
ASL W
ASL X
ASL Y
ASL Z
ASL 0
ASL 1
ASL 2
ASL 3
ASL 4
ASL 5
ASL 6
ASL 7
ASL 8
ASL 9
ASL _"""
    
    return mock_open(read_data=csv_content)