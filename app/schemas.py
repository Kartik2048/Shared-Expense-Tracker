from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, ConfigDict

# --- User Schemas ---
class UserBase(BaseModel):
    name: str
    email: str

class UserCreate(UserBase):
    pass

class UserResponse(UserBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


# --- Group Schemas ---
class GroupBase(BaseModel):
    name: str

class GroupCreate(GroupBase):
    pass

class GroupResponse(GroupBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


# --- Group Member Schemas ---
class GroupMemberBase(BaseModel):
    group_id: int
    user_id: int

class GroupMemberAdd(BaseModel):
    user_id: int
    joined_at: Optional[datetime] = None

class GroupMemberCreate(GroupMemberBase):
    joined_at: Optional[datetime] = None
    left_at: Optional[datetime] = None

class GroupMemberResponse(GroupMemberBase):
    id: int
    joined_at: datetime
    left_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# --- Expense Schemas ---
class ExpenseBase(BaseModel):
    group_id: int
    description: str
    amount: float
    currency: str = "INR"
    exchange_rate_to_inr: float = 1.0
    date: datetime
    paid_by_id: int
    split_type: str
    notes: Optional[str] = None

class ExpenseCreate(ExpenseBase):
    pass

class ExpenseResponse(ExpenseBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


# --- Expense Split Schemas ---
class ExpenseSplitBase(BaseModel):
    expense_id: int
    user_id: int
    amount: float

class ExpenseSplitCreate(ExpenseSplitBase):
    pass

class ExpenseSplitResponse(ExpenseSplitBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


# --- Settlement Schemas ---
class SettlementBase(BaseModel):
    group_id: int
    payer_id: int
    payee_id: int
    amount: float
    currency: str = "INR"
    exchange_rate_to_inr: float = 1.0
    date: datetime

class SettlementCreate(SettlementBase):
    pass

class SettlementResponse(SettlementBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


# --- Staging Expense Schemas ---
class StagingExpenseBase(BaseModel):
    raw_date: Optional[str] = None
    raw_description: Optional[str] = None
    raw_paid_by: Optional[str] = None
    raw_amount: Optional[str] = None
    raw_currency: Optional[str] = None
    raw_split_type: Optional[str] = None
    raw_split_with: Optional[str] = None
    raw_split_details: Optional[str] = None
    raw_notes: Optional[str] = None
    status: str = "pending"
    anomaly_flags: Optional[Dict[str, Any]] = None

class StagingExpenseCreate(StagingExpenseBase):
    pass

class StagingExpenseResponse(StagingExpenseBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
