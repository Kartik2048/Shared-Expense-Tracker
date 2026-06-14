import csv
from io import StringIO
from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db
from app.services import validation

router = APIRouter()

@router.post("/validate-staging", status_code=status.HTTP_200_OK)
def trigger_validation(db: Session = Depends(get_db)):
    """
    Triggers the validation engine checks on all pending staging records.
    """
    return validation.validate_pending_expenses(db)

@router.post("/upload-csv", status_code=status.HTTP_201_CREATED)
def upload_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Accepts a CSV file, parses it, blindly inserts all rows into 
    the StagingExpense table as raw strings with 'pending' status,
    runs the validation engine, and returns validation summary and data.
    """
    # Read file contents and convert from bytes to a text stream
    content = file.file.read().decode("utf-8-sig")  # utf-8-sig handles byte-order-mark (BOM) cleanly
    csv_file = StringIO(content)
    
    # DictReader automatically parses the first row as headers
    reader = csv.DictReader(csv_file)
    
    staging_records_added = []
    for row in reader:
        # Normalize keys by stripping whitespace and lowering characters to handle messy headers
        normalized_row = {
            (k.strip().lower() if k else ""): (v.strip() if v else "")
            for k, v in row.items()
        }
        
        # Helper lookup to support multiple potential header mappings
        def get_field(possible_headers):
            for h in possible_headers:
                if h in normalized_row:
                    return normalized_row[h]
            return None

        # Build raw StagingExpense record
        staging_expense = models.StagingExpense(
            raw_date=get_field(["date", "raw_date", "timestamp", "datetime"]),
            raw_description=get_field(["description", "raw_description", "desc", "expense"]),
            raw_paid_by=get_field(["paid_by", "paid_by_id", "raw_paid_by", "payer", "who_paid"]),
            raw_amount=get_field(["amount", "raw_amount", "cost", "total"]),
            raw_currency=get_field(["currency", "raw_currency", "ccy", "unit"]),
            raw_split_type=get_field(["split_type", "raw_split_type", "type"]),
            raw_split_with=get_field(["split_with", "raw_split_with", "splitters"]),
            raw_split_details=get_field(["split_details", "raw_split_details", "details"]),
            raw_notes=get_field(["notes", "raw_notes", "comment", "note"]),
            status="pending",
            anomaly_flags=None
        )
        
        db.add(staging_expense)
        staging_records_added.append(staging_expense)
        
    db.commit()
    
    # Immediately trigger validation on the pending records
    validation.validate_pending_expenses(db)
    
    # Re-query the added records to ensure we return their updated status and anomaly_flags
    staging_ids = [r.id for r in staging_records_added]
    updated_records = db.query(models.StagingExpense).filter(models.StagingExpense.id.in_(staging_ids)).all()
    
    valid_count = sum(1 for r in updated_records if r.status == "valid")
    flagged_count = sum(1 for r in updated_records if r.status == "flagged")
    
    return {
        "summary": {
            "total_ingested": len(updated_records),
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
            for r in updated_records
        ]
    }
