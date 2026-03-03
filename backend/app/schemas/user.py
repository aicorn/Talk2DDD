import uuid
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr, field_validator


class UserBase(BaseModel):
    email: EmailStr
    username: str
    full_name: Optional[str] = None


class UserCreate(UserBase):
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    bio: Optional[str] = None
    preferred_language: Optional[str] = None
    theme: Optional[str] = None


class UserResponse(UserBase):
    id: uuid.UUID
    is_active: bool
    is_superuser: bool
    preferred_language: str
    theme: str
    bio: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenData(BaseModel):
    user_id: Optional[uuid.UUID] = None
    email: Optional[str] = None
