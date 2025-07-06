from fastapi import APIRouter, Depends, Form
from fastapi.security import OAuth2PasswordRequestForm
from api.schema.user import UserCreate
from api.database.database import get_db
from api.database.query.db_auth import DBAuth
from api.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/signup")
async def signup(user: UserCreate, db=Depends(get_db)):
    db_auth = DBAuth(db)
    auth_service = AuthService(db_auth)
    return await auth_service.signup(user)

@router.post("/login")
async def login(    
    username: str = Form(...),
    password: str = Form(...), 
    db=Depends(get_db)
):
    db_auth = DBAuth(db)
    auth_service = AuthService(db_auth)
    return await auth_service.login(username, password)

@router.post("/logout")
async def logout(db=Depends(get_db)):
    db_auth = DBAuth(db)
    auth_service = AuthService(db_auth)
    return await auth_service.logout()
