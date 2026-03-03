from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.schemas.user import UserCreate, UserResponse, UserLogin, Token, UserUpdate
from app.crud.user import UserCRUD
from app.core.security import create_access_token
from app.core.exceptions import ConflictException, UnauthorizedException, NotFoundException
from app.core.dependencies import get_current_user
from app.models.user import User
from app.config import settings

router = APIRouter()
user_crud = UserCRUD()


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(
    user_in: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    existing_email = await user_crud.get_by_email(db, user_in.email)
    if existing_email:
        raise ConflictException("Email already registered")

    existing_username = await user_crud.get_by_username(db, user_in.username)
    if existing_username:
        raise ConflictException("Username already taken")

    user = await user_crud.create(db, user_in)
    return user


@router.post("/login", response_model=Token)
async def login(
    credentials: UserLogin,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user = await user_crud.authenticate(db, credentials.email, credentials.password)
    if not user:
        raise UnauthorizedException("Invalid email or password")
    if not user.is_active:
        raise UnauthorizedException("Account is inactive")

    access_token = create_access_token(
        subject=user.id,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: Annotated[User, Depends(get_current_user)],
):
    return current_user


@router.put("/me", response_model=UserResponse)
async def update_current_user(
    user_in: UserUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    updated_user = await user_crud.update(db, current_user, user_in)
    return updated_user
