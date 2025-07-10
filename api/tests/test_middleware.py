import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import HTTPException, Request, WebSocket, status
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse
from datetime import datetime, timezone
from bson import ObjectId
import jwt

from api.middleware.auth import (
    get_current_user, 
    get_optional_user, 
    CookieOrHeaderToken
)
from api.middleware.log import APIGatewayMiddleware
from api.schema.user import UserProfile


class TestAuthMiddleware:
    """Test authentication middleware components"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database connection"""
        return MagicMock()
    
    @pytest.fixture
    def mock_db_auth(self):
        """Mock database auth instance"""
        mock_db_auth = MagicMock()
        mock_db_auth.find_user_by_email = AsyncMock()
        return mock_db_auth
    
    @pytest.fixture
    def sample_user_data(self):
        """Sample user data from database"""
        return {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "first_name": "Meo",
            "last_name": "Meo",
            "email": "meomeo@gmail.com",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "last_login": datetime.now(timezone.utc),
            "is_active": True,
            "role": "user"
        }
    
    @pytest.fixture
    def valid_jwt_token(self):
        """Generate a valid JWT token for testing"""
        from api.constant.config import JWT_SECRET
        payload = {
            "sub": "meomeo@gmail.com",
            "exp": datetime.now(timezone.utc).timestamp() + 3600  # 1 hour from now
        }
        return jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    
    @pytest.fixture
    def expired_jwt_token(self):
        """Generate an expired JWT token for testing"""
        from api.constant.config import JWT_SECRET
        payload = {
            "sub": "meomeo@gmail.com",
            "exp": datetime.now(timezone.utc).timestamp() - 3600  # 1 hour ago
        }
        return jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    
    @pytest.fixture
    def invalid_jwt_token(self):
        """Generate an invalid JWT token for testing"""
        return "invalid.jwt.token"
    
    @pytest.mark.asyncio
    async def test_get_current_user_success_with_cookie(self, mock_db, mock_db_auth, sample_user_data, valid_jwt_token):
        """Test successful authentication with cookie token"""
        # Mock database response
        mock_db_auth.find_user_by_email.return_value = sample_user_data
        
        with patch('api.middleware.auth.DBAuth', return_value=mock_db_auth):
            user = await get_current_user(token=valid_jwt_token, db=mock_db)
            
            assert isinstance(user, UserProfile)
            assert user.email == "meomeo@gmail.com"
            assert user.first_name == "Meo"
            assert user.last_name == "Meo"
            assert user.is_active is True
            assert user.role == "user"
            assert user.id == str(sample_user_data["_id"])
            
            # Verify database was called
            mock_db_auth.find_user_by_email.assert_called_once_with("meomeo@gmail.com")
    
    @pytest.mark.asyncio
    async def test_get_current_user_expired_token(self, mock_db, expired_jwt_token):
        """Test authentication with expired token"""
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token=expired_jwt_token, db=mock_db)
        
        assert exc_info.value.status_code == 401
        assert "Token has expired" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self, mock_db, invalid_jwt_token):
        """Test authentication with invalid token"""
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token=invalid_jwt_token, db=mock_db)
        
        assert exc_info.value.status_code == 401
        assert "Invalid token" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_get_current_user_missing_email_in_token(self, mock_db):
        """Test authentication with token missing email"""
        from api.constant.config import JWT_SECRET
        payload = {
            "user_id": "123",  # Missing 'sub' field
            "exp": datetime.now(timezone.utc).timestamp() + 3600
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
        
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token=token, db=mock_db)
        
        assert exc_info.value.status_code == 401
        assert "Invalid token format: missing user email" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_get_current_user_user_not_found(self, mock_db, mock_db_auth, valid_jwt_token):
        """Test authentication when user is not found in database"""
        # Mock database to return None
        mock_db_auth.find_user_by_email.return_value = None
        
        with patch('api.middleware.auth.DBAuth', return_value=mock_db_auth):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(token=valid_jwt_token, db=mock_db)
            
            assert exc_info.value.status_code == 401
            assert "User not found" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_get_current_user_database_error(self, mock_db, mock_db_auth, valid_jwt_token):
        """Test authentication when database raises error"""
        # Mock database to raise exception
        mock_db_auth.find_user_by_email.side_effect = Exception("Database connection error")
        
        with patch('api.middleware.auth.DBAuth', return_value=mock_db_auth):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(token=valid_jwt_token, db=mock_db)
            
            assert exc_info.value.status_code == 401
            assert "Could not validate credentials" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_get_optional_user_success_with_cookie(
        self, 
        mock_db, 
        mock_db_auth, 
        sample_user_data, 
        valid_jwt_token
    ):
        """Test optional user authentication with cookie"""
        # Mock WebSocket with cookies
        mock_websocket = MagicMock(spec=WebSocket)
        mock_websocket.cookies = {"access_token": valid_jwt_token}
        mock_websocket.query_params = {}
        
        # Mock database response
        mock_db_auth.find_user_by_email.return_value = sample_user_data
        
        with patch('api.middleware.auth.DBAuth', return_value=mock_db_auth):
            with patch('api.middleware.auth.get_current_user') as mock_get_current_user:
                mock_get_current_user.return_value = UserProfile(
                    id=str(sample_user_data["_id"]),
                    email=sample_user_data["email"],
                    first_name=sample_user_data["first_name"],
                    last_name=sample_user_data["last_name"],
                    created_at=sample_user_data["created_at"],
                    updated_at=sample_user_data["updated_at"],
                    last_login=sample_user_data["last_login"],
                    is_active=sample_user_data["is_active"],
                    role=sample_user_data["role"]
                )
                
                user = await get_optional_user(websocket=mock_websocket, db=mock_db)
                
                assert isinstance(user, UserProfile)
                assert user.email == "meomeo@gmail.com"
                mock_get_current_user.assert_called_once_with(token=valid_jwt_token, db=mock_db)
    
    @pytest.mark.asyncio
    async def test_get_optional_user_success_with_query_param(self, mock_db, mock_db_auth, sample_user_data, valid_jwt_token):
        """Test optional user authentication with query parameter"""
        # Mock WebSocket with query params
        mock_websocket = MagicMock(spec=WebSocket)
        mock_websocket.cookies = {}
        mock_websocket.query_params = {"token": valid_jwt_token}
        
        # Mock database response
        mock_db_auth.find_user_by_email.return_value = sample_user_data
        
        with patch('api.middleware.auth.DBAuth', return_value=mock_db_auth):
            with patch('api.middleware.auth.get_current_user') as mock_get_current_user:
                mock_get_current_user.return_value = UserProfile(
                    id=str(sample_user_data["_id"]),
                    email=sample_user_data["email"],
                    first_name=sample_user_data["first_name"],
                    last_name=sample_user_data["last_name"],
                    created_at=sample_user_data["created_at"],
                    updated_at=sample_user_data["updated_at"],
                    last_login=sample_user_data["last_login"],
                    is_active=sample_user_data["is_active"],
                    role=sample_user_data["role"]
                )
                
                user = await get_optional_user(websocket=mock_websocket, db=mock_db)
                
                assert isinstance(user, UserProfile)
                assert user.email == "meomeo@gmail.com"
                mock_get_current_user.assert_called_once_with(token=valid_jwt_token, db=mock_db)
    
    @pytest.mark.asyncio
    async def test_get_optional_user_no_token(self, mock_db):
        """Test optional user authentication with no token"""
        # Mock WebSocket with no token
        mock_websocket = MagicMock(spec=WebSocket)
        mock_websocket.cookies = {}
        mock_websocket.query_params = {}
        
        user = await get_optional_user(websocket=mock_websocket, db=mock_db)
        
        assert user is None
    
    @pytest.mark.asyncio
    async def test_get_optional_user_invalid_token(self, mock_db, invalid_jwt_token):
        """Test optional user authentication with invalid token"""
        # Mock WebSocket with invalid token
        mock_websocket = MagicMock(spec=WebSocket)
        mock_websocket.cookies = {"access_token": invalid_jwt_token}
        mock_websocket.query_params = {}
        
        with patch('api.middleware.auth.get_current_user') as mock_get_current_user:
            mock_get_current_user.side_effect = HTTPException(status_code=401, detail="Invalid token")
            
            user = await get_optional_user(websocket=mock_websocket, db=mock_db)
            
            assert user is None
    
    @pytest.mark.asyncio
    async def test_cookie_or_header_token_from_cookie(self):
        """Test token extraction from cookie"""
        mock_request = MagicMock(spec=Request)
        mock_request.cookies = {"access_token": "test_token"}
        
        token_extractor = CookieOrHeaderToken()
        token = await token_extractor(mock_request)
        
        assert token == "test_token"
    
    @pytest.mark.asyncio
    async def test_cookie_or_header_token_from_header(self):
        """Test token extraction from Authorization header"""
        mock_request = MagicMock(spec=Request)
        mock_request.cookies = {}
        
        token_extractor = CookieOrHeaderToken()
        
        # Mock the oauth2_scheme to return a token using AsyncMock
        token_extractor.oauth2_scheme = AsyncMock(return_value="header_token")
        
        token = await token_extractor(mock_request)
        
        assert token == "header_token"
    
    @pytest.mark.asyncio
    async def test_cookie_or_header_token_no_token(self):
        """Test token extraction when no token is available"""
        mock_request = MagicMock(spec=Request)
        mock_request.cookies = {}
        
        token_extractor = CookieOrHeaderToken()
        
        # Mock OAuth2PasswordBearer to return None
        with patch.object(token_extractor.oauth2_scheme, '__call__', return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await token_extractor(mock_request)
            
            assert exc_info.value.status_code == 401
            assert "Not authenticated" in str(exc_info.value.detail)


class TestLogMiddleware:
    """Test logging middleware components"""
    
    @pytest.fixture
    def log_middleware(self):
        """Create log middleware instance"""
        return APIGatewayMiddleware(app=MagicMock())
    
    @pytest.fixture
    def mock_request(self):
        """Mock FastAPI request object"""
        mock_request = MagicMock(spec=Request)
        mock_request.method = "GET"
        mock_request.url.path = "/test/endpoint"
        mock_request.path_params = {}
        mock_request.query_params = {}
        mock_request.headers = {"Content-Type": "application/json"}
        mock_request.client.host = "127.0.0.1"
        return mock_request
    
    @pytest.fixture
    def mock_call_next(self):
        """Mock call_next function"""
        async def mock_call_next(request):
            response = MagicMock()
            response.status_code = 200
            response.body = b'{"message": "success"}'
            response.media_type = "application/json"
            response.headers = {}
            return response
        return mock_call_next
    
    def test_get_ip_from_x_forwarded_for(self, log_middleware, mock_request):
        """Test IP extraction from X-Forwarded-For header"""
        mock_request.headers = {"X-Forwarded-For": "203.0.113.1, 198.51.100.1"}
        
        ip = log_middleware.get_ip(mock_request)
        
        assert ip == "203.0.113.1"
    
    def test_get_ip_from_x_real_ip(self, log_middleware, mock_request):
        """Test IP extraction from X-Real-IP header"""
        mock_request.headers = {"X-Real-IP": "203.0.113.1"}
        
        ip = log_middleware.get_ip(mock_request)
        
        assert ip == "203.0.113.1"
    
    def test_get_ip_fallback_to_client_host(self, log_middleware, mock_request):
        """Test IP fallback to client host"""
        mock_request.headers = {}
        mock_request.client.host = "127.0.0.1"
        
        ip = log_middleware.get_ip(mock_request)
        
        assert ip == "127.0.0.1"
    
    def test_print_log_request(self, log_middleware, mock_request):
        """Test request logging functionality"""
        start_time = datetime.now().timestamp()
        
        # This should not raise any exceptions
        log_middleware.print_log_request(
            request=mock_request,
            request_body='{"test": "data"}',
            original_path="/test/endpoint",
            start_time=start_time
        )
    
    def test_print_log_response(self, log_middleware):
        """Test response logging functionality"""
        # This should not raise any exceptions
        log_middleware.print_log_response(
            status_code=200,
            response='{"message": "success"}',
            error_message=None
        )
    
    @pytest.mark.asyncio
    async def test_write_log(self, log_middleware, mock_request):
        """Test log writing functionality"""
        with patch('api.middleware.log.write_log') as mock_write_log:
            log_middleware.write_log(
                request=mock_request,
                request_body='{"test": "data"}',
                original_path="/test/endpoint",
                status_code=200,
                body_str='{"message": "success"}',
                process_time=0.1,
                error_message=None
            )
            
            # Verify write_log was called
            mock_write_log.assert_called_once()
            
            # Verify log entry structure
            log_entry = mock_write_log.call_args[1]["request"]
            assert log_entry.method == "GET"
            assert log_entry.path_name == "/test/endpoint"
            assert log_entry.status_response == 200
            assert log_entry.duration == 0.1
    
    @pytest.mark.asyncio
    async def test_dispatch_successful_request(self, log_middleware, mock_request):
        """Test successful request processing"""
        async def mock_call_next(request):
            # Mock request body reading
            request.body = AsyncMock(return_value=b'{"test": "data"}')
            
            response = MagicMock()
            response.status_code = 200
            response.body = b'{"message": "success"}'
            response.media_type = "application/json"
            response.headers = {}
            return response
        
        mock_request.body = AsyncMock(return_value=b'{"test": "data"}')
        mock_request.headers = {"Content-Type": "application/json"}
        
        with patch('api.middleware.log.write_log'):
            response = await log_middleware.dispatch(mock_request, mock_call_next)
            
            assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_dispatch_invalid_json_request(self, log_middleware, mock_request):
        """Test request with invalid JSON"""
        mock_request.body = AsyncMock(return_value=b'invalid json')
        mock_request.headers = {"Content-Type": "application/json"}
        
        with patch('api.middleware.log.write_log'):
            response = await log_middleware.dispatch(mock_request, lambda x: None)
            
            assert response.status_code == 400
            response_data = json.loads(response.body)
            assert response_data["detail"] == "Invalid JSON format"
    
    @pytest.mark.asyncio
    async def test_dispatch_http_exception(self, log_middleware, mock_request):
        """Test request that raises HTTPException"""
        async def mock_call_next_with_exception(request):
            request.body = AsyncMock(return_value=b'{"test": "data"}')
            raise HTTPException(status_code=404, detail="Not found")
        
        mock_request.body = AsyncMock(return_value=b'{"test": "data"}')
        mock_request.headers = {"Content-Type": "application/json"}
        
        with patch('api.middleware.log.write_log'):
            response = await log_middleware.dispatch(mock_request, mock_call_next_with_exception)
            
            assert response.status_code == 404
            response_data = json.loads(response.body)
            assert response_data["detail"] == "Not found"
    
    @pytest.mark.asyncio
    async def test_dispatch_general_exception(self, log_middleware, mock_request):
        """Test request that raises general exception"""
        async def mock_call_next_with_exception(request):
            request.body = AsyncMock(return_value=b'{"test": "data"}')
            raise Exception("Internal server error")
        
        mock_request.body = AsyncMock(return_value=b'{"test": "data"}')
        mock_request.headers = {"Content-Type": "application/json"}
        
        with patch('api.middleware.log.write_log'):
            response = await log_middleware.dispatch(mock_request, mock_call_next_with_exception)
            
            assert response.status_code == 500
            response_data = json.loads(response.body)
            assert response_data["detail"] == "Internal server error"
    
    @pytest.mark.asyncio
    async def test_dispatch_non_json_request(self, log_middleware, mock_request):
        """Test request with non-JSON content type"""
        async def mock_call_next(request):
            request.body = AsyncMock(return_value=b'plain text data')
            
            response = MagicMock()
            response.status_code = 200
            response.body = b'{"message": "success"}'
            response.media_type = "application/json"
            response.headers = {}
            return response
        
        mock_request.body = AsyncMock(return_value=b'plain text data')
        mock_request.headers = {"Content-Type": "text/plain"}
        
        with patch('api.middleware.log.write_log'):
            response = await log_middleware.dispatch(mock_request, mock_call_next)
            
            assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_handle_log_integration(self, log_middleware, mock_request):
        """Test complete log handling integration"""
        start_time = datetime.now().timestamp()
        
        with patch('api.middleware.log.write_log') as mock_write_log:
            with patch.object(log_middleware, 'print_log_request') as mock_print_request:
                with patch.object(log_middleware, 'print_log_response') as mock_print_response:
                    await log_middleware.handle_log(
                        request=mock_request,
                        request_body='{"test": "data"}',
                        status_code=200,
                        error_message=None,
                        original_path="/test/endpoint",
                        start_time=start_time,
                        process_time=0.1,
                        body_str='{"message": "success"}'
                    )
                    
                    # Verify all logging methods were called
                    mock_print_request.assert_called_once()
                    mock_print_response.assert_called_once()
                    mock_write_log.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_dispatch_streaming_response(self, log_middleware, mock_request):
        """Test handling of streaming responses"""
        async def mock_call_next(request):
            request.body = AsyncMock(return_value=b'{"test": "data"}')
            
            response = MagicMock()
            response.status_code = 200
            response.media_type = "application/json"
            response.headers = {}
            
            # Mock streaming response
            async def mock_body_iterator():
                yield b'{"message": "'
                yield b'streaming'
                yield b'"}'
            
            response.body_iterator = mock_body_iterator()
            return response
        
        mock_request.body = AsyncMock(return_value=b'{"test": "data"}')
        mock_request.headers = {"Content-Type": "application/json"}
        
        with patch('api.middleware.log.write_log'):
            response = await log_middleware.dispatch(mock_request, mock_call_next)
            
            assert response.status_code == 200
            # Response should be reconstructed from streamed chunks
            assert b'streaming' in response.body
    
    @pytest.mark.asyncio
    async def test_dispatch_binary_response(self, log_middleware, mock_request):
        """Test handling of binary responses"""
        async def mock_call_next(request):
            request.body = AsyncMock(return_value=b'{"test": "data"}')
            
            response = MagicMock()
            response.status_code = 200
            response.body = b'\x89PNG\r\n\x1a\n'  # Binary PNG header
            response.media_type = "image/png"
            response.headers = {}
            return response
        
        mock_request.body = AsyncMock(return_value=b'{"test": "data"}')
        mock_request.headers = {"Content-Type": "application/json"}
        
        with patch('api.middleware.log.write_log'):
            response = await log_middleware.dispatch(mock_request, mock_call_next)
            
            assert response.status_code == 200
