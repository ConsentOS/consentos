import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenPayload(BaseModel):
    sub: str  # user ID
    org_id: str  # organisation ID
    role: str  # user role
    exp: datetime
    iat: datetime
    type: str = "access"  # "access" or "refresh"


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class UpdateProfileRequest(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = None


class ProfileResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    organisation_id: uuid.UUID

    model_config = {"from_attributes": True}


class CurrentUser(BaseModel):
    """Represents the authenticated user extracted from a JWT."""

    id: uuid.UUID
    organisation_id: uuid.UUID
    email: str
    role: str

    def has_role(self, *roles: str) -> bool:
        return self.role in roles

    @property
    def is_admin(self) -> bool:
        return self.role in ("owner", "admin")
