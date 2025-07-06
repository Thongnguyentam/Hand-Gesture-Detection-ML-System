# app/middleware/auth.py

import jwt
import logging
from fastapi import Depends, HTTPException, status, Request, WebSocket
from fastapi.security import OAuth2PasswordBearer
from typing import Optional
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorDatabase
from api.database.database import get_db
from api.database.query.db_auth import DBAuth

# Set up logging
logger = logging.getLogger(__name__)

# Load your JWT secret key from environment variables
from api.constant.config import JWT_SECRET
from api.schema.user import UserProfile

class CookieOrHeaderToken:
    def __init__(self, token_url: str = "login"):
        self.oauth2_scheme = OAuth2PasswordBearer(tokenUrl=token_url, auto_error=False)

    async def __call__(self, request: Request) -> Optional[str]:
        # First try to get token from cookie
        token = request.cookies.get("access_token")
        if not token:
            # If no cookie, try to get from Authorization header
            try:
                token = await self.oauth2_scheme(request)
            except:
                token = None
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return token

# Create token extractor instance
token_extractor = CookieOrHeaderToken()

async def get_current_user(
    token: str = Depends(token_extractor),
    db: AsyncIOMotorDatabase = Depends(get_db)
) -> UserProfile:
    """
    Verify JWT token and return user info.
    Supports both cookie-based and header-based authentication.
    
    Args:
        token: JWT token from cookie or header
        db: Database connection
        
    Returns:
        UserProfile object containing user information
        
    Raises:
        HTTPException: If token is invalid, expired, or user not found
    """
    try:
        # Decode and validate the token
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        
        # Get email from token (used as subject in auth_service.login)
        email = payload.get("sub")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token format: missing user email",
                headers={"WWW-Authenticate": "Bearer"}
            )
            
        # Get user from database using email
        db_auth = DBAuth(db)
        user = await db_auth.find_user_by_email(email)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"}
            )
            
        # Convert to UserProfile model
        user_profile = UserProfile(
            id=str(user["_id"]),
            first_name=user["first_name"],
            last_name=user["last_name"],
            email=user["email"],
            created_at=user["created_at"],
            updated_at=user["updated_at"],
            last_login=user.get("last_login"),
            is_active=user.get("is_active", True),
            role=user.get("role", "user")
        )
        
        return user_profile
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"}
        )

async def get_optional_user(
    websocket: WebSocket,
    db: AsyncIOMotorDatabase = Depends(get_db)
) -> Optional[UserProfile]:
    """
    Get user from WebSocket cookies or query params if available.
    Unlike get_current_user, this doesn't raise an exception if no token is found.
    
    Args:
        websocket: WebSocket connection
        db: Database connection
        
    Returns:
        Optional[UserProfile]: User profile if token is valid, None otherwise
    """
    try:
        # First try to get token from cookies
        cookies = websocket.cookies
        token = cookies.get("access_token")
        
        # If no cookie, try query params as fallback
        if not token:
            token = websocket.query_params.get("token")
            
        if token:
            return await get_current_user(token=token, db=db)
    except Exception as e:
        logger.error(f"WebSocket authentication error: {str(e)}")
    return None
