import re
from decimal import Decimal, InvalidOperation
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db
from app.services import validation

router = APIRouter()

@router.get("/staging", status_code=status.HTTP_200_OK)
def get_staging_status(db: Session = Depends(get_db)):
    """
    Get all staging records with their current validation status and metrics.
    """
    records = db.query(models.StagingExpense).all()
    valid_count = sum(1 for r in records if r.status == "valid")
    flagged_count = sum(1 for r in records if r.status == "flagged")
    return {
        "summary": {
            "total_ingested": len(records),
            "valid_count": valid_count,
            "flagged_count": flagged_count
        },
        "data": [
            {
                "id": r.id,
                "raw_date": r.raw_date,
                "raw_description": r.raw_description,
                "raw_paid_by": r.raw_paid_by,
                "raw_amount": r.raw_amount,
                "raw_currency": r.raw_currency,
                "raw_split_type": r.raw_split_type,
                "raw_split_with": r.raw_split_with,
                "raw_split_details": r.raw_split_details,
                "raw_notes": r.raw_notes,
                "status": r.status,
                "anomaly_flags": r.anomaly_flags
            }
            for r in records
        ]
    }


# Helper function to parse dates using the same formats as validation
def parse_date(date_str: str) -> datetime:
    if not date_str or not date_str.strip():
        raise ValueError("Date is empty")
    clean_date_str = date_str.strip()
    for fmt in (
        "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y", 
        "%Y/%m/%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S", 
        "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S%z"
    ):
        try:
            if "T" in clean_date_str and (clean_date_str.endswith("Z") or "+" in clean_date_str):
                clean_date_str = clean_date_str.replace("Z", "").split("+")[0]
            return datetime.strptime(clean_date_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Invalid date format: '{date_str}'")


@router.delete("/staging/{row_id}", status_code=status.HTTP_200_OK)
def discard_staging_expense(row_id: int, db: Session = Depends(get_db)):
    """
    Discard (delete) the staging expense with the given ID.
    """
    staging = db.query(models.StagingExpense).filter(models.StagingExpense.id == row_id).first()
    if not staging:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Staging expense ID {row_id} not found."
        )
    
    db.delete(staging)
    db.commit()
    return {"message": f"Successfully discarded staging expense ID {row_id}."}


@router.put("/staging/{row_id}", response_model=schemas.StagingExpenseResponse, status_code=status.HTTP_200_OK)
def modify_staging_expense(row_id: int, payload: schemas.StagingExpenseUpdate, db: Session = Depends(get_db)):
    """
    Modify (update) raw staging fields, set status to pending, and re-run validation.
    """
    staging = db.query(models.StagingExpense).filter(models.StagingExpense.id == row_id).first()
    if not staging:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Staging expense ID {row_id} not found."
        )
        
    # Apply updates for any provided fields
    update_data = payload.model_dump(exclude_unset=True)
    for key, val in update_data.items():
        setattr(staging, key, val)
        
    # Reset status to pending so it gets re-validated
    staging.status = "pending"
    staging.anomaly_flags = None
    db.commit()
    
    # Trigger validation on the updated record
    validation.validate_pending_expenses(db)
    
    db.refresh(staging)
    return staging


@router.post("/staging/{row_id}/approve", status_code=status.HTTP_201_CREATED)
def approve_staging_expense(row_id: int, db: Session = Depends(get_db)):
    """
    Approve a staging record and promote it to the production Expense and ExpenseSplit tables.
    """
    staging = db.query(models.StagingExpense).filter(models.StagingExpense.id == row_id).first()
    if not staging:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Staging expense ID {row_id} not found."
        )

    # 1. Parse amount
    if not staging.raw_amount or not staging.raw_amount.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Staging record is missing amount. Cannot approve."
        )
    try:
        clean_amount = re.sub(r"[^\d.-]", "", staging.raw_amount.strip())
        amount_val = Decimal(clean_amount)
    except (InvalidOperation, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Staging record has invalid amount format: '{staging.raw_amount}'"
        )
        
    # 2. Parse date
    try:
        date_val = parse_date(staging.raw_date)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    # 3. Resolve Payer user ID
    if not staging.raw_paid_by or not staging.raw_paid_by.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Staging record is missing payer. Cannot approve."
        )
    payer_name = staging.raw_paid_by.strip().lower()
    payer_user = db.query(models.User).filter(
        (models.User.name.ilike(payer_name)) | (models.User.email.ilike(payer_name))
    ).first()
    if not payer_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Payer user '{staging.raw_paid_by}' not found in database."
        )

    # 4. Resolve Split recipient user IDs
    if not staging.raw_split_with or not staging.raw_split_with.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Staging record is missing split participants. Cannot approve."
        )
    split_delimiter = ";" if ";" in staging.raw_split_with else ","
    split_names = [s.strip().lower() for s in staging.raw_split_with.split(split_delimiter) if s.strip()]
    
    split_users = []
    for name_or_email in split_names:
        u = db.query(models.User).filter(
            (models.User.name.ilike(name_or_email)) | (models.User.email.ilike(name_or_email))
        ).first()
        if not u:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Split user '{name_or_email}' not found in database."
            )
        split_users.append(u)

    # 5. Resolve Group ID (find a shared group containing the payer and all split recipients)
    payer_group_ids = {m.group_id for m in db.query(models.GroupMember).filter(models.GroupMember.user_id == payer_user.id).all()}
    shared_group_id = None
    for g_id in payer_group_ids:
        members_in_group = {m.user_id for m in db.query(models.GroupMember).filter(models.GroupMember.group_id == g_id).all()}
        if all(s.id in members_in_group for s in split_users):
            shared_group_id = g_id
            break

    if not shared_group_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No shared group found containing payer ({payer_user.name}) and all split recipients."
        )

    # 6. Apply multi-currency rules
    raw_currency = staging.raw_currency.strip().upper() if staging.raw_currency else "INR"
    if raw_currency == "INR":
        exchange_rate = Decimal("1.0")
    elif raw_currency == "USD":
        exchange_rate = Decimal("83.5")
    else:
        exchange_rate = Decimal("1.0")  # Default fallback

    # 7. Helper to parse split details key-value pairs
    def parse_details_to_dict():
        splits_dict = {}
        if staging.raw_split_details and staging.raw_split_details.strip():
            delimiter = ";" if ";" in staging.raw_split_details else ","
            parts = [p.strip() for p in staging.raw_split_details.split(delimiter) if p.strip()]
            for part in parts:
                part = part.strip()
                if ":" in part:
                    name_part, val_part = part.split(":", 1)
                else:
                    # Robust separation of name and value using right-side split on whitespace
                    split_parts = part.rsplit(None, 1)
                    if len(split_parts) == 2:
                        name_part, val_part = split_parts
                    else:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Invalid split details format: '{part}'"
                        )
                
                name_key = name_part.strip().lower()
                # Remove trailing % symbols if present
                val_str = val_part.strip().rstrip("%").strip()
                try:
                    splits_dict[name_key] = Decimal(val_str)
                except (InvalidOperation, ValueError):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Could not parse split details amount: '{part}'"
                    )
        return splits_dict

    # 8. Calculate splits using penny-rounding error handling
    split_allocations = []  # List of tuples: (User, Decimal amount)
    split_type = staging.raw_split_type.strip().lower() if staging.raw_split_type else "equal"

    if split_type == "equal":
        # Divide amount equally among the split recipients
        n = len(split_users)
        if n == 0:
            raise HTTPException(status_code=400, detail="No split users identified.")
        
        raw_share = amount_val / Decimal(str(n))
        rounded_share = raw_share.quantize(Decimal("0.01"))
        
        shares = [rounded_share] * n
        sum_shares = sum(shares)
        difference = amount_val - sum_shares
        
        # Apply rounding error adjustment to the first user
        shares[0] += difference
        
        for idx, user in enumerate(split_users):
            split_allocations.append((user, shares[idx]))

    elif split_type == "percentage":
        details = parse_details_to_dict()
        if not details:
            raise HTTPException(status_code=400, detail="Percentage split type requires split details.")
        
        # Verify percentages sum to 100
        sum_percent = sum(details.values())
        if sum_percent != Decimal("100"):
            raise HTTPException(status_code=400, detail=f"Split percentages sum to {sum_percent}%, expected 100%.")
            
        shares = []
        for user in split_users:
            u_name = user.name.lower()
            u_email = user.email.lower()
            percentage = details.get(u_name) or details.get(u_email) or Decimal("0")
            
            raw_share = amount_val * (percentage / Decimal("100"))
            shares.append(raw_share.quantize(Decimal("0.01")))
            
        sum_shares = sum(shares)
        difference = amount_val - sum_shares
        
        # Apply rounding error adjustment to the first splitter
        shares[0] += difference
        
        for idx, user in enumerate(split_users):
            split_allocations.append((user, shares[idx]))

    elif split_type == "exact":
        details = parse_details_to_dict()
        if not details:
            raise HTTPException(status_code=400, detail="Exact split type requires split details.")
            
        sum_shares = Decimal("0.0")
        for user in split_users:
            u_name = user.name.lower()
            u_email = user.email.lower()
            exact_amt = details.get(u_name) or details.get(u_email) or Decimal("0")
            split_allocations.append((user, exact_amt))
            sum_shares += exact_amt
            
        # Verify exact sum matches total
        if sum_shares != amount_val:
            raise HTTPException(status_code=400, detail=f"Exact split details sum to {sum_shares}, expected {amount_val}.")

    elif split_type in ("share", "unequal"):
        details = parse_details_to_dict()
        if not details:
            raise HTTPException(status_code=400, detail="Share/unequal split type requires split details.")
            
        total_shares = sum(details.values())
        if total_shares <= 0:
            raise HTTPException(status_code=400, detail="Total split shares must be greater than zero.")
            
        shares = []
        for user in split_users:
            u_name = user.name.lower()
            u_email = user.email.lower()
            user_shares = details.get(u_name) or details.get(u_email) or Decimal("0")
            
            raw_share = amount_val * (user_shares / total_shares)
            shares.append(raw_share.quantize(Decimal("0.01")))
            
        sum_shares = sum(shares)
        difference = amount_val - sum_shares
        
        # Apply rounding error adjustment to the first splitter
        shares[0] += difference
        
        for idx, user in enumerate(split_users):
            split_allocations.append((user, shares[idx]))
            
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported split type: '{split_type}'"
        )

    # 9. Write production Expense record
    production_expense = models.Expense(
        group_id=shared_group_id,
        description=staging.raw_description,
        amount=amount_val,
        currency=raw_currency,
        exchange_rate_to_inr=exchange_rate,
        date=date_val,
        paid_by_id=payer_user.id,
        split_type=split_type,
        notes=staging.raw_notes
    )
    db.add(production_expense)
    db.commit()
    db.refresh(production_expense)

    # 10. Write production ExpenseSplit records
    for user, split_amount in split_allocations:
        prod_split = models.ExpenseSplit(
            expense_id=production_expense.id,
            user_id=user.id,
            amount=split_amount
        )
        db.add(prod_split)
        
    # 11. Clean up StagingExpense record
    db.delete(staging)
    db.commit()

    return {
        "message": f"Successfully approved staging record ID {row_id} and promoted to production.",
        "expense_id": production_expense.id
    }
