from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel
from app import models
from app.database import get_db
from app.dependencies import get_current_user

router = APIRouter()

class ExpenseDetail(BaseModel):
    expense_id: int
    description: str
    amount: float
    currency: str
    exchange_rate: float
    amount_inr: float

class BalanceResponse(BaseModel):
    user_id: int
    user_name: str
    total_paid_inr: float
    total_owed_inr: float
    net_balance_inr: float
    paid_details: List[ExpenseDetail]
    owed_details: List[ExpenseDetail]

@router.get("/balances", response_model=BalanceResponse, status_code=status.HTTP_200_OK)
def get_user_balances(target_user_id: Optional[int] = None, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """
    Calculate and return a user's total Paid, Owed, and Net Balance in INR,
    along with detailed breakdown logs of the underlying expenses.
    """
    user_id = target_user_id if target_user_id is not None else current_user.id
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found."
        )

    # 1. Fetch all expenses paid by the user
    expenses_paid = db.query(models.Expense).filter(models.Expense.paid_by_id == user_id).all()
    
    paid_details = []
    total_paid_inr = Decimal("0.0")
    for exp in expenses_paid:
        amt_inr = exp.amount * exp.exchange_rate_to_inr
        total_paid_inr += amt_inr
        paid_details.append(ExpenseDetail(
            expense_id=exp.id,
            description=exp.description,
            amount=float(exp.amount),
            currency=exp.currency,
            exchange_rate=float(exp.exchange_rate_to_inr),
            amount_inr=float(amt_inr)
        ))

    # 2. Fetch all splits where the user owes money
    splits_owed = db.query(models.ExpenseSplit).filter(models.ExpenseSplit.user_id == user_id).all()
    
    owed_details = []
    total_owed_inr = Decimal("0.0")
    for split in splits_owed:
        # Load associated production Expense
        exp = split.expense
        if not exp:
            continue
        amt_inr = split.amount * exp.exchange_rate_to_inr
        total_owed_inr += amt_inr
        owed_details.append(ExpenseDetail(
            expense_id=exp.id,
            description=exp.description,
            amount=float(split.amount),
            currency=exp.currency,
            exchange_rate=float(exp.exchange_rate_to_inr),
            amount_inr=float(amt_inr)
        ))

    net_balance_inr = total_paid_inr - total_owed_inr

    return BalanceResponse(
        user_id=user.id,
        user_name=user.name,
        total_paid_inr=float(total_paid_inr),
        total_owed_inr=float(total_owed_inr),
        net_balance_inr=float(net_balance_inr),
        paid_details=paid_details,
        owed_details=owed_details
    )
