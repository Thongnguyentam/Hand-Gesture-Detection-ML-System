import json
import pytest
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from datetime import datetime, timezone
from bson import ObjectId

# Add the project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from api.services.auth_service import AuthService
from api.database.query.db_auth import DBAuth
from api.schema.user import UserCreate, hash_password, verify_password, create_access_token

class TestAuthService:
    
    @pytest.fixture
    def mock_db_auth(self):
        """Create a mock DBAuth instance"""
        mock_db = MagicMock()
        return DBAuth(mock_db)
    
    @pytest.fixture
    def auth_service(self, mock_db_auth):
        """Create an AuthService instance with mocked database"""
        return AuthService(mock_db_auth)
    
    @pytest.fixture
    def sample_user_create(self):
        """Sample user creation data"""
        return UserCreate(
            first_name="Meo",
            last_name="Nguyen",
            email="meo@gmail.com",
            password="securepassword123",
            role="user"
        )
    
    @pytest.fixture
    def sample_user_db(self):
        """Sample user database record"""
        return {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "first_name": "Meo",
            "last_name": "Nguyen",
            "email": "meo@gmail.com",
            "hashed_password": hash_password("securepassword123"),
            "role": "user",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "last_login": None
        }

    # Test signup functionality
    @pytest.mark.asyncio
    async def test_signup_success(self, auth_service, sample_user_create):
        """Test successful user signup"""
        # Mock database methods
        auth_service.db_auth.check_email_exists = AsyncMock(return_value=False)
        auth_service.db_auth.create_user = AsyncMock(return_value={"id": "123"})
        
        # Execute signup
        response = await auth_service.signup(sample_user_create)
        
        # Assertions
        assert isinstance(response, JSONResponse)
        assert response.status_code == 201
        
        # Verify database methods were called
        auth_service.db_auth.check_email_exists.assert_called_once_with(sample_user_create.email)
        auth_service.db_auth.create_user.assert_called_once()
        
        # Verify the user data structure passed to create_user
        call_args = auth_service.db_auth.create_user.call_args[0][0]
        assert call_args["first_name"] == sample_user_create.first_name
        assert call_args["last_name"] == sample_user_create.last_name
        assert call_args["email"] == sample_user_create.email
        assert call_args["role"] == sample_user_create.role
        assert "hashed_password" in call_args
        assert "created_at" in call_args
        assert "updated_at" in call_args

    @pytest.mark.asyncio
    async def test_signup_email_already_exists(self, auth_service, sample_user_create):
        """Test signup with existing email"""
        # Mock database to return existing user
        auth_service.db_auth.check_email_exists = AsyncMock(return_value=True)
        
        # Execute signup
        response = await auth_service.signup(sample_user_create)
        
        # Assertions
        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        
        # Verify response content
        response_data = response.body.decode()
        assert "USERNAME_TAKEN" in response_data
        assert "Username already exists" in response_data

    @pytest.mark.asyncio
    async def test_signup_database_error(self, auth_service, sample_user_create):
        """Test signup with database error"""
        # Mock database to raise exception
        auth_service.db_auth.check_email_exists = AsyncMock(return_value=False)
        auth_service.db_auth.create_user = AsyncMock(side_effect=Exception("Database error"))
        
        # Execute signup and expect HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await auth_service.signup(sample_user_create)
        
        assert exc_info.value.status_code == 500
        assert "Signup failed" in str(exc_info.value.detail)

    # Test login functionality
    @pytest.mark.asyncio
    async def test_login_success(self, auth_service, sample_user_db):
        """Test successful user login"""
        # Mock database methods
        auth_service.db_auth.find_user_by_email = AsyncMock(return_value=sample_user_db)
        auth_service.db_auth.update_last_login = AsyncMock()
        
        # Execute login
        response = await auth_service.login("meo@gmail.com", "securepassword123")
        
        # Assertions
        assert isinstance(response, JSONResponse)
        assert response.status_code == 200
        
        # Verify database methods were called
        auth_service.db_auth.find_user_by_email.assert_called_once_with("meo@gmail.com")
        auth_service.db_auth.update_last_login.assert_called_once_with(str(sample_user_db["_id"]))
        # Verify response structure
        response_json = json.loads(response.body)
        assert "access_token" in response_json
        assert "user" in response_json
        assert response_json["user"]["userId"] == str(sample_user_db["_id"])
        assert response_json["user"]["username"] == "meo@gmail.com"
        assert response_json["user"]["priviledge"] == "user"

    @pytest.mark.asyncio
    async def test_login_user_not_found(self, auth_service):
        """Test login with non-existent user"""
        # Mock database to return None
        auth_service.db_auth.find_user_by_email = AsyncMock(return_value=None)
        
        # Execute login and expect HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await auth_service.login("nonexistent@example.com", "password")
        
        assert exc_info.value.status_code == 401
        assert "Invalid credentials" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_login_invalid_password(self, auth_service, sample_user_db):
        """Test login with invalid password"""
        # Mock database to return user
        auth_service.db_auth.find_user_by_email = AsyncMock(return_value=sample_user_db)
        
        # Execute login with wrong password
        with pytest.raises(HTTPException) as exc_info:
            await auth_service.login("meo@gmail.com", "wrongpassword")
        
        assert exc_info.value.status_code == 401
        assert "Invalid credentials" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_login_database_error(self, auth_service):
        """Test login with database error"""
        # Mock database to raise exception
        auth_service.db_auth.find_user_by_email = AsyncMock(side_effect=Exception("Database error"))
        
        # Execute login and expect HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await auth_service.login("meo@gmail.com", "password")
        
        assert exc_info.value.status_code == 500
        assert "Login failed" in str(exc_info.value.detail)
        assert "Database error" in str(exc_info.value.detail)

    # Test logout functionality
    @pytest.mark.asyncio
    async def test_logout_success(self, auth_service):
        """Test successful user logout"""
        # Execute logout
        response = await auth_service.logout()
        
        # Assertions
        assert isinstance(response, JSONResponse)
        assert response.status_code == 200
        
        # Verify response content
        response_data = response.body.decode()
        assert "Logged out successfully" in response_data

    # Test helper methods
    def test_serialize_response_with_datetime(self, auth_service):
        """Test serialization of datetime objects"""
        test_data = {
            "created_at": datetime.now(timezone.utc),
            "name": "test"
        }
        
        result = auth_service._serialize_response(test_data)
        
        assert isinstance(result["created_at"], str)
        assert result["name"] == "test"

    def test_serialize_response_with_objectid(self, auth_service):
        """Test serialization of ObjectId objects"""
        test_data = {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "name": "test"
        }
        
        result = auth_service._serialize_response(test_data)
        
        assert isinstance(result["_id"], str)
        assert result["_id"] == "507f1f77bcf86cd799439011"
        assert result["name"] == "test"

    def test_serialize_response_with_nested_dict(self, auth_service):
        """Test serialization of nested dictionaries"""
        test_data = {
            "user": {
                "_id": ObjectId("507f1f77bcf86cd799439011"),
                "created_at": datetime.now(timezone.utc)
            },
            "name": "test"
        }
        
        result = auth_service._serialize_response(test_data)
        
        assert isinstance(result["user"]["_id"], str)
        assert isinstance(result["user"]["created_at"], str)
        assert result["name"] == "test"

# Tests for auth router
class TestAuthRouter:
    
    @pytest.fixture
    def mock_auth_service(self):
        """Create a mock auth service"""
        return AsyncMock()

    def test_signup_endpoint_success(self, mock_auth_service):
        """Test signup endpoint with valid data"""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from api.routers.auth import router
        from api.database.database import get_db
        
        # Create a test app with just the auth router
        test_app = FastAPI()
        test_app.include_router(router)
        
        # Mock the database dependency
        def override_get_db():
            return MagicMock()
        
        test_app.dependency_overrides[get_db] = override_get_db
        
        # Mock the auth service
        with patch('api.routers.auth.AuthService') as mock_auth_service_class:
            mock_auth_service.signup.return_value = JSONResponse(
                content={"message": "User created successfully"},
                status_code=201
            )
            mock_auth_service_class.return_value = mock_auth_service
            
            # Create test client
            client = TestClient(test_app)
            
            # Test data
            user_data = {
                "first_name": "Meo",
                "last_name": "Nguyen",
                "email": "meo@gmail.com",
                "password": "securepassword123",
                "role": "user"
            }
            
            # Make request
            response = client.post("/auth/signup", json=user_data)
            
            # Assertions
            assert response.status_code == 201
            assert response.json() == {"message": "User created successfully"}
            
            # Verify the auth service was called
            mock_auth_service.signup.assert_called_once()

    def test_login_endpoint_success(self, mock_auth_service):
        """Test login endpoint with valid credentials"""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from api.routers.auth import router
        from api.database.database import get_db
        
        # Create a test app with just the auth router
        test_app = FastAPI()
        test_app.include_router(router)
        
        # Mock the database dependency
        def override_get_db():
            return MagicMock()
        
        test_app.dependency_overrides[get_db] = override_get_db
        
        # Mock the auth service
        with patch('api.routers.auth.AuthService') as mock_auth_service_class:
            mock_auth_service.login.return_value = JSONResponse(
                content={
                    "access_token": "test_token",
                    "user": {
                        "userId": "123",
                        "username": "meo@gmail.com",
                        "priviledge": "user"
                    }
                },
                status_code=200
            )
            mock_auth_service_class.return_value = mock_auth_service
            
            # Create test client
            client = TestClient(test_app)
            
            # Test data (form data for login)
            login_data = {
                "username": "meo@gmail.com",
                "password": "securepassword123"
            }
            
            # Make request
            response = client.post("/auth/login", data=login_data)
            
            # Assertions
            assert response.status_code == 200
            response_json = response.json()
            assert "access_token" in response_json
            assert response_json["user"]["username"] == "meo@gmail.com"
            assert response_json["user"]["priviledge"] == "user"
            
            # Verify the auth service was called
            mock_auth_service.login.assert_called_once()

    def test_logout_endpoint_success(self, mock_auth_service):
        """Test logout endpoint"""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from api.routers.auth import router
        from api.database.database import get_db
        
        # Create a test app with just the auth router
        test_app = FastAPI()
        test_app.include_router(router)
        
        # Mock the database dependency
        def override_get_db():
            return MagicMock()
        
        test_app.dependency_overrides[get_db] = override_get_db
        
        # Mock the auth service
        with patch('api.routers.auth.AuthService') as mock_auth_service_class:
            mock_auth_service.logout.return_value = JSONResponse(
                content={"message": "Logged out successfully"},
                status_code=200
            )
            mock_auth_service_class.return_value = mock_auth_service
            
            # Create test client
            client = TestClient(test_app)
            
            # Make request
            response = client.post("/auth/logout")
            
            # Assertions
            assert response.status_code == 200
            assert response.json() == {"message": "Logged out successfully"}
            
            # Verify the auth service was called
            mock_auth_service.logout.assert_called_once()
