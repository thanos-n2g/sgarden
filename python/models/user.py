"""Pydantic models for user request/response schemas."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class UserInDB(BaseModel):
    """Internal user representation as stored in MongoDB."""

    id: Optional[str] = Field(None, alias="_id")
    username: str
    email: str
    password: str
    role: str = "user"
    last_active_at: datetime = Field(default_factory=datetime.utcnow)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class RegisterRequest(BaseModel):
    """Payload for registering a new user."""

    username: str = Field(..., min_length=3, max_length=30)
    email: EmailStr
    password: str = Field(..., min_length=8)


class LoginRequest(BaseModel):
    """Payload for authenticating a user."""

    username: str
    password: str


class AuthResponse(BaseModel):
    """Response returned after successful register or login."""

    token: str
    username: str
    role: str
