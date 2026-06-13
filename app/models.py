from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship
from app.database import Base

def utc_now():
    """Returns the current timezone-naive UTC datetime."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    group_memberships = relationship("GroupMember", back_populates="user", cascade="all, delete-orphan")
    expenses_paid = relationship("Expense", back_populates="paid_by", cascade="all, delete-orphan")
    expense_splits = relationship("ExpenseSplit", back_populates="user", cascade="all, delete-orphan")
    
    settlements_sent = relationship(
        "Settlement",
        foreign_keys="[Settlement.payer_id]",
        back_populates="payer",
        cascade="all, delete-orphan"
    )
    settlements_received = relationship(
        "Settlement",
        foreign_keys="[Settlement.payee_id]",
        back_populates="payee",
        cascade="all, delete-orphan"
    )


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    members = relationship("GroupMember", back_populates="group", cascade="all, delete-orphan")
    expenses = relationship("Expense", back_populates="group", cascade="all, delete-orphan")
    settlements = relationship("Settlement", back_populates="group", cascade="all, delete-orphan")


class GroupMember(Base):
    __tablename__ = "group_members"

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    joined_at = Column(DateTime, default=utc_now, nullable=False)
    left_at = Column(DateTime, nullable=True)  # Track people moving in and out

    # Relationships
    group = relationship("Group", back_populates="members")
    user = relationship("User", back_populates="group_memberships")


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    paid_by_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    description = Column(String(255), nullable=False)
    
    # Financial fields: Numeric handles decimal accuracy for currency
    amount = Column(Numeric(12, 4), nullable=False)
    currency = Column(String(3), default="INR", nullable=False)
    exchange_rate_to_inr = Column(Numeric(18, 8), default=1.0, nullable=False)
    
    created_at = Column(DateTime, default=utc_now, nullable=False)
    date = Column(DateTime, default=utc_now, nullable=False)

    # Relationships
    group = relationship("Group", back_populates="expenses")
    paid_by = relationship("User", back_populates="expenses_paid")
    splits = relationship("ExpenseSplit", back_populates="expense", cascade="all, delete-orphan")


class ExpenseSplit(Base):
    __tablename__ = "expense_splits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    expense_id = Column(Integer, ForeignKey("expenses.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    amount = Column(Numeric(12, 4), nullable=False)

    # Relationships
    expense = relationship("Expense", back_populates="splits")
    user = relationship("User", back_populates="expense_splits")


class Settlement(Base):
    __tablename__ = "settlements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    payer_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    payee_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    amount = Column(Numeric(12, 4), nullable=False)
    currency = Column(String(3), default="INR", nullable=False)
    exchange_rate_to_inr = Column(Numeric(18, 8), default=1.0, nullable=False)
    
    status = Column(String(20), default="pending", nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    # Relationships
    group = relationship("Group", back_populates="settlements")
    payer = relationship("User", foreign_keys=[payer_id], back_populates="settlements_sent")
    payee = relationship("User", foreign_keys=[payee_id], back_populates="settlements_received")


class StagingExpense(Base):
    """
    Staging model for raw CSV inputs. 
    All fields are strings to allow unstructured raw data ingestion, 
    plus status tracking and anomaly flagging.
    """
    __tablename__ = "staging_expenses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    raw_description = Column(String(255), nullable=True)
    raw_amount = Column(String(50), nullable=True)
    raw_currency = Column(String(50), nullable=True)
    raw_date = Column(String(100), nullable=True)
    raw_paid_by = Column(String(100), nullable=True)
    raw_group_name = Column(String(100), nullable=True)
    raw_splits = Column(Text, nullable=True)
    
    status = Column(String(50), default="pending", nullable=False)
    anomaly_flags = Column(JSON, nullable=True)  # Stores JSON validation findings (e.g. invalid decimals, missing users)
    
    created_at = Column(DateTime, default=utc_now, nullable=False)
