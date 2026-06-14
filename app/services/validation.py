import re
from decimal import Decimal, InvalidOperation
from datetime import datetime
from sqlalchemy.orm import Session
from app import models

def validate_pending_expenses(db: Session):
    """
    Queries all StagingExpense rows where status == 'pending'.
    Runs checks for missing data, duplicates, conflicting records, refunds,
    membership timeframe matching, mathematical split accuracy, and settlements.
    
    Transitions row status:
    - 'pending' -> 'valid' (no warnings/errors)
    - 'pending' -> 'flagged' (has warnings or errors)
    """
    pending_records = db.query(models.StagingExpense).filter(models.StagingExpense.status == "pending").all()
    
    # Cache database users and group memberships for efficiency
    all_users = db.query(models.User).all()
    user_by_name = {u.name.strip().lower(): u for u in all_users if u.name}
    user_by_email = {u.email.strip().lower(): u for u in all_users if u.email}
    
    all_memberships = db.query(models.GroupMember).all()
    # group_id -> list of member mappings
    group_members = {}
    for m in all_memberships:
        group_members.setdefault(m.group_id, []).append(m)
        
    results = {"total_checked": 0, "valid": 0, "flagged": 0}
    
    for record in pending_records:
        errors = []
        warnings = []
        
        # --- Rule 1: Missing Critical Data ---
        critical_fields = {
            "raw_date": "Date",
            "raw_description": "Description",
            "raw_amount": "Amount",
            "raw_paid_by": "Payer",
            "raw_currency": "Currency"
        }
        for field, name in critical_fields.items():
            val = getattr(record, field)
            if not val or not str(val).strip():
                errors.append({
                    "code": "MISSING_CRITICAL_DATA",
                    "field": field,
                    "message": f"Missing critical field: {name}"
                })
        
        # Parse Amount for numerical validation
        parsed_amount = None
        if record.raw_amount and record.raw_amount.strip():
            try:
                # Strip currency symbols if present
                clean_amount = re.sub(r"[^\d.-]", "", record.raw_amount.strip())
                parsed_amount = Decimal(clean_amount)
            except (InvalidOperation, ValueError):
                errors.append({
                    "code": "INVALID_AMOUNT_FORMAT",
                    "message": f"Could not parse amount: '{record.raw_amount}'"
                })
                
        # Parse Date for membership window validation
        parsed_date = None
        if record.raw_date and record.raw_date.strip():
            date_str = record.raw_date.strip()
            # Try parsing multiple common formats
            for fmt in (
                "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y", 
                "%Y/%m/%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S", 
                "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S%z"
            ):
                try:
                    # Strip standard ISO Z or offset if needed
                    if "T" in date_str and (date_str.endswith("Z") or "+" in date_str):
                        clean_date_str = date_str.replace("Z", "").split("+")[0]
                    else:
                        clean_date_str = date_str
                    parsed_date = datetime.strptime(clean_date_str, fmt)
                    break
                except ValueError:
                    continue
            if not parsed_date:
                errors.append({
                    "code": "INVALID_DATE_FORMAT",
                    "message": f"Could not parse date: '{record.raw_date}'"
                })
        
        # --- Rule 2: Exact Duplicate Rows ---
        duplicate_count = db.query(models.StagingExpense).filter(
            models.StagingExpense.id != record.id,
            models.StagingExpense.raw_date == record.raw_date,
            models.StagingExpense.raw_description == record.raw_description,
            models.StagingExpense.raw_amount == record.raw_amount,
            models.StagingExpense.raw_paid_by == record.raw_paid_by,
            models.StagingExpense.raw_currency == record.raw_currency,
            models.StagingExpense.raw_split_type == record.raw_split_type,
            models.StagingExpense.raw_split_with == record.raw_split_with,
            models.StagingExpense.raw_split_details == record.raw_split_details,
            models.StagingExpense.raw_notes == record.raw_notes
        ).count()
        if duplicate_count > 0:
            warnings.append({
                "code": "EXACT_DUPLICATE_ROW",
                "message": f"This row has {duplicate_count} identical copies in staging."
            })
            
        # --- Rule 3: Conflicting Duplicates ---
        if record.raw_date and record.raw_description:
            conflicting_records = db.query(models.StagingExpense).filter(
                models.StagingExpense.id != record.id,
                models.StagingExpense.raw_date == record.raw_date,
                models.StagingExpense.raw_description == record.raw_description
            ).all()
            for cr in conflicting_records:
                if cr.raw_amount != record.raw_amount or cr.raw_paid_by != record.raw_paid_by:
                    errors.append({
                        "code": "CONFLICTING_DUPLICATE",
                        "message": f"Conflict with staging row ID {cr.id}: same date & description but different amount or payer."
                    })
                    break
                    
        # --- Rule 4: Negative Amounts (Refunds) ---
        if parsed_amount is not None and parsed_amount < 0:
            warnings.append({
                "code": "NEGATIVE_AMOUNT_REFUND",
                "message": "Negative amount detected. Flagged as a refund transaction."
            })
            
        # --- Rule 5: Time-bound Membership Violations ---
        payer_user = None
        if record.raw_paid_by and record.raw_paid_by.strip():
            payer_name = record.raw_paid_by.strip().lower()
            payer_user = user_by_name.get(payer_name) or user_by_email.get(payer_name)
            if not payer_user:
                errors.append({
                    "code": "PAYER_NOT_FOUND",
                    "message": f"Payer user '{record.raw_paid_by}' not found."
                })
                
        splitters = []
        if record.raw_split_with and record.raw_split_with.strip():
            # Support semicolon delimiter, fallback to comma
            delimiter = ";" if ";" in record.raw_split_with else ","
            split_names = [s.strip().lower() for s in record.raw_split_with.split(delimiter) if s.strip()]
            for name_or_email in split_names:
                u = user_by_name.get(name_or_email) or user_by_email.get(name_or_email)
                if not u:
                    errors.append({
                        "code": "SPLIT_USER_NOT_FOUND",
                        "message": f"Split recipient user '{name_or_email}' not found."
                    })
                else:
                    splitters.append(u)
                    
        # Check active memberships in shared groups on the expense date
        if parsed_date and payer_user and splitters:
            # Get groups containing the payer
            payer_group_ids = {m.group_id for m in all_memberships if m.user_id == payer_user.id}
            
            # Find groups containing BOTH the payer and ALL split recipients
            shared_group_ids = []
            for g_id in payer_group_ids:
                members_in_group = {m.user_id for m in group_members.get(g_id, [])}
                if all(s.id in members_in_group for s in splitters):
                    shared_group_ids.append(g_id)
                    
            if not shared_group_ids:
                errors.append({
                    "code": "NO_SHARED_GROUP",
                    "message": f"Payer '{payer_user.name}' and split recipients do not share any common group."
                })
            else:
                # Check membership time bounds on parsed_date for each shared group
                valid_group_found = False
                reasons = []
                for g_id in shared_group_ids:
                    group_is_valid = True
                    group_m_records = group_members.get(g_id, [])
                    # Verify bounds for all participants (payer + splitters)
                    participants = [payer_user] + splitters
                    for part in participants:
                        # Find the membership record in this group for the participant
                        m_rec = next((m for m in group_m_records if m.user_id == part.id), None)
                        if m_rec:
                            # Joined bounds check
                            if m_rec.joined_at and parsed_date < m_rec.joined_at:
                                group_is_valid = False
                                reasons.append(f"User '{part.name}' joined group ID {g_id} on {m_rec.joined_at.date()}, which is after the expense date ({parsed_date.date()})")
                            # Left bounds check
                            if m_rec.left_at and parsed_date > m_rec.left_at:
                                group_is_valid = False
                                reasons.append(f"User '{part.name}' left group ID {g_id} on {m_rec.left_at.date()}, which is before the expense date ({parsed_date.date()})")
                    if group_is_valid:
                        valid_group_found = True
                        break
                        
                if not valid_group_found:
                    errors.append({
                        "code": "MEMBERSHIP_TIME_VIOLATION",
                        "message": "Time-bound membership violation: " + "; ".join(reasons)
                    })
                    
        # --- Rule 6: Mathematical Errors in Splits ---
        if parsed_amount is not None and record.raw_split_type:
            split_type = record.raw_split_type.strip().lower()
            
            # Helper to parse raw_split_details (e.g. "kartik:600,alice:600" or "kartik:600;alice:600")
            def parse_details():
                splits_dict = {}
                if record.raw_split_details and record.raw_split_details.strip():
                    # Support semicolon delimiter, fallback to comma
                    delimiter = ";" if ";" in record.raw_split_details else ","
                    parts = [p.strip() for p in record.raw_split_details.split(delimiter) if p.strip()]
                    for part in parts:
                        if ":" in part:
                            user_str, val_str = part.split(":", 1)
                            user_str = user_str.strip().lower()
                            try:
                                splits_dict[user_str] = Decimal(val_str.strip())
                            except (InvalidOperation, ValueError):
                                errors.append({
                                    "code": "INVALID_SPLIT_VALUE",
                                    "message": f"Could not parse split value for '{user_str}': '{val_str}'"
                                })
                        else:
                            errors.append({
                                "code": "INVALID_SPLIT_FORMAT",
                                "message": f"Split detail '{part}' is missing a colon."
                            })
                return splits_dict

            if split_type == "exact":
                details = parse_details()
                if details:
                    total_splits = sum(details.values())
                    if total_splits != parsed_amount:
                        errors.append({
                            "code": "MATHEMATICAL_SPLIT_ERROR",
                            "message": f"Sum of split details ({total_splits}) does not match total amount ({parsed_amount})."
                        })
            elif split_type == "percentage":
                details = parse_details()
                if details:
                    total_percent = sum(details.values())
                    if total_percent != Decimal("100"):
                        errors.append({
                            "code": "MATHEMATICAL_SPLIT_ERROR",
                            "message": f"Sum of split percentages ({total_percent}%) does not equal 100%."
                        })
            elif split_type == "equal":
                # For equal split, if details are explicitly provided, check they sum to amount
                details = parse_details()
                if details:
                    total_splits = sum(details.values())
                    if total_splits != parsed_amount:
                        errors.append({
                            "code": "MATHEMATICAL_SPLIT_ERROR",
                            "message": f"Sum of explicit equal split values ({total_splits}) does not match total amount ({parsed_amount})."
                        })
                        
        # --- Rule 7: Settlement Disguised as Expense (Row 12 logic) ---
        if record.raw_description:
            desc = record.raw_description.strip().lower()
            settlement_patterns = [
                r"\bpaid\b.*\bback\b",   # Rohan paid Aisha back
                r"\brepaid\b",           # Repaid room rent share
                r"\bsettle\b",           # Settled debt
                r"\bsettlement\b",
                r"\brepayment\b",
                r"\bpay\b.*\bback\b"
            ]
            is_settlement = False
            for pat in settlement_patterns:
                if re.search(pat, desc):
                    is_settlement = True
                    break
            if is_settlement:
                warnings.append({
                    "code": "SETTLEMENT_DISGUISED_AS_EXPENSE",
                    "message": f"Description '{record.raw_description}' indicates a debt settlement rather than a shared group expense."
                })

        # --- State Management & Saving Anomaly Flags ---
        has_anomalies = len(errors) > 0 or len(warnings) > 0
        record.anomaly_flags = {
            "errors": errors,
            "warnings": warnings
        } if has_anomalies else None
        
        # If any errors or warnings are found, the row is flagged. Otherwise valid.
        if has_anomalies:
            record.status = "flagged"
            results["flagged"] += 1
        else:
            record.status = "valid"
            results["valid"] += 1
            
        results["total_checked"] += 1
        
    db.commit()
    return results
