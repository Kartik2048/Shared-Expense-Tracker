from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

# --- User Schemas ---
class UserBase(BaseModel):
    username: str
    email: str

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Group Schemas ---
class GroupBase(BaseModel):
    name: str
    description: Optional[str] = None

class GroupCreate(GroupBase):
    pass

class GroupResponse(GroupBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Group Member Schemas ---
class GroupMemberAdd(BaseModel):
    user_id: int
    joined_at: Optional[datetime] = None

class GroupMemberResponse(BaseModel):
    id: int
    group_id: int
    user_id: int
    joined_at: datetime
    left_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
