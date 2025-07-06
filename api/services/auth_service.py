from datetime import datetime, timezone
from typing import Dict, Optional
from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from api.database.query.db_auth import DBAuth
from api.schema.user import UserCreate, UserDB, create_access_token, hash_password, verify_password
from bson import ObjectId

class AuthService:
    def __init__(self, db_auth: DBAuth):
        self.db_auth = db_auth

    def _serialize_response(self, obj: Dict) -> Dict:
        """Convert datetime and ObjectId objects to strings"""
        serialized = {}
        for key, value in obj.items():
            if isinstance(value, datetime):
                serialized[key] = value.isoformat()
            elif isinstance(value, ObjectId):
                serialized[key] = str(value)
            elif isinstance(value, dict):
                serialized[key] = self._serialize_response(value)
            else:
                serialized[key] = value
        return serialized

    async def signup(self, user: UserCreate) -> JSONResponse:
        """Handle user signup"""
        try:
            # Check if email exists
            if await self.db_auth.check_email_exists(user.email):
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={
                        "statusCode": 400,
                        "message": "Username already exists",
                        "errorCode": "USERNAME_TAKEN",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                )
            
            # Prepare user data
            hashed_password = hash_password(user.password)
            db_user = {
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "hashed_password": hashed_password,
                "role": user.role,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc)
            }
            
            # Create user in database
            created_user = await self.db_auth.create_user(db_user)
            
            # Serialize response before returning
            serialized_user = self._serialize_response(db_user)
            
            return JSONResponse(
                content=serialized_user,
                status_code=status.HTTP_201_CREATED
            )
        except HTTPException as e:
            # Re-raise HTTP exceptions as they are already properly formatted
            raise e
        except Exception as e:
            # Handle any other exceptions
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Signup failed: {str(e)}"
            )

    async def login(self, username: str, password: str) -> JSONResponse:
        """Handle user login"""
        try:
            # Find user by email
            user = await self.db_auth.find_user_by_email(username)
            if not user or not verify_password(password, user["hashed_password"]):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid credentials"
                )
            # Update last login
            await self.db_auth.update_last_login(str(user["_id"]))
            # Create access token
            access_token = create_access_token(data={"sub": user["email"]})
            # Prepare response
            response_data = {
                "access_token": access_token,
                "user": {
                    "userId": str(user["_id"]),
                    "username": user["email"],
                    "priviledge": user.get("role", "user")
                }
            }
            # Create response with cookie
            response = JSONResponse(content=response_data)
            response.set_cookie(
                key="access_token",
                value=access_token,
                httponly=True,
                secure=True,
                samesite="Strict"
            )
            print(response)
            return response
        except HTTPException as e:
            raise e
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Login failed: {str(e)}"
            )

    async def logout(self) -> JSONResponse:
        """Handle user logout"""
        try:
            response = JSONResponse(content={"message": "Logged out successfully"})
            response.delete_cookie("access_token")
            return response
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Logout failed: {str(e)}"
            )
