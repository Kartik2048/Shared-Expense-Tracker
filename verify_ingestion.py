import os
import json
from datetime import datetime, timezone
from io import BytesIO

# Force SQLite database file for testing
os.environ["DATABASE_URL"] = "sqlite:///./test_ingest.db"

from fastapi.testclient import TestClient
from app.database import Base, engine, SessionLocal
from app.models import User, Group, GroupMember, StagingExpense
from app.main import app

client = TestClient(app)

# Seed mock database values required for validation (users, groups, memberships)
def seed_data():
    db = SessionLocal()
    # Clean previous tables
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    # Create users
    kartik = User(name="kartik", email="kartik@example.com")
    alice = User(name="alice", email="alice@example.com")
    rohan = User(name="rohan", email="rohan@example.com")
    aisha = User(name="aisha", email="aisha@example.com")
    db.add_all([kartik, alice, rohan, aisha])
    db.commit()
    
    # Create group
    group = Group(name="Apartment 204")
    db.add(group)
    db.commit()
    
    # Add memberships
    # Active memberships from 2026-01-01
    member_kartik = GroupMember(
        group_id=group.id,
        user_id=kartik.id,
        joined_at=datetime(2026, 1, 1, 12, 0)
    )
    member_rohan = GroupMember(
        group_id=group.id,
        user_id=rohan.id,
        joined_at=datetime(2026, 1, 1, 12, 0)
    )
    member_aisha = GroupMember(
        group_id=group.id,
        user_id=aisha.id,
        joined_at=datetime(2026, 1, 1, 12, 0)
    )
    # Alice leaves on 2026-03-01
    member_alice = GroupMember(
        group_id=group.id,
        user_id=alice.id,
        joined_at=datetime(2026, 1, 1, 12, 0),
        left_at=datetime(2026, 3, 1, 12, 0)
    )
    
    db.add_all([member_kartik, member_rohan, member_aisha, member_alice])
    db.commit()
    db.close()
    print("Mock database seeded successfully.")

def test_csv_ingestion_pipeline():
    # Build test CSV contents
    csv_data = (
        "date,description,paid_by,amount,currency,split_type,split_with,split_details,notes\n"
        # 1. Valid Expense (Unique, no warnings/errors)
        "2026-02-05,Dinner Party,kartik,1200.00,INR,exact,\"kartik,aisha,rohan\",\"kartik:400,aisha:400,rohan:400\",Consolidated cost\n"
        # 2. Duplicate Row A
        "2026-02-10,Groceries,kartik,600.00,INR,exact,\"kartik,rohan\",\"kartik:300,rohan:300\",Weekly Groceries\n"
        # 3. Duplicate Row B (Exact Duplicate of Row A)
        "2026-02-10,Groceries,kartik,600.00,INR,exact,\"kartik,rohan\",\"kartik:300,rohan:300\",Weekly Groceries\n"
        # 4. Conflicting Duplicate (same date & desc as Row A/B, but different amount)
        "2026-02-10,Groceries,kartik,800.00,INR,exact,\"kartik,rohan\",\"kartik:400,rohan:400\",Conflicting amount\n"
        # 5. Missing Critical Data (no payer)
        "2026-02-11,Cleaning supply,,100.00,INR,equal,kartik,,No payer name\n"
        # 6. Negative Amount (Refund Check)
        "2026-02-12,Refund for internet,rohan,-30.00,USD,equal,\"rohan,kartik\",,WiFi credit\n"
        # 7. Mathematical Split Error (Sum of exact split details 500+500 != 900)
        "2026-02-13,Gas Bill,kartik,900.00,INR,exact,\"kartik,aisha\",\"kartik:500,aisha:500\",Math mismatch\n"
        # 8. Time-bound Membership Violation (Alice is charged on 2026-04-10, but she left on 2026-03-01)
        "2026-04-10,Electricity Bill,kartik,1000.00,INR,equal,\"kartik,alice\",,Alice left\n"
        # 9. Settlement Disguised as Expense (Row 12 logic check - 'Rohan paid Aisha back')
        "2026-02-15,Rohan paid Aisha back,rohan,500.00,INR,equal,\"rohan,aisha\",,Settle debt\n"
    )
    
    # Upload CSV file
    file_payload = {"file": ("test_expenses.csv", BytesIO(csv_data.encode("utf-8")), "text/csv")}
    response = client.post("/upload-csv", files=file_payload)
    print("\n--- CSV Ingestion Response ---")
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    assert response.status_code == 201
    res_json = response.json()
    assert res_json["summary"]["total_ingested"] == 9
    assert res_json["summary"]["valid_count"] == 1
    assert res_json["summary"]["flagged_count"] == 8
    
    # Query staging expenses to inspect validation flags
    db = SessionLocal()
    staging_records = db.query(StagingExpense).order_by(StagingExpense.id).all()
    
    print("\n--- Detailed Staging Validations Checked ---")
    for r in staging_records:
        print(f"\nID {r.id} | Desc: '{r.raw_description}' | Status: {r.status.upper()}")
        if r.anomaly_flags:
            print(f" -> Errors: {len(r.anomaly_flags.get('errors', []))}")
            for err in r.anomaly_flags.get("errors", []):
                print(f"    [ERR] {err['code']}: {err['message']}")
            print(f" -> Warnings: {len(r.anomaly_flags.get('warnings', []))}")
            for wrn in r.anomaly_flags.get("warnings", []):
                print(f"    [WRN] {wrn['code']}: {wrn['message']}")
        else:
            print(" -> No Anomaly Flags.")
            
    # Assertions on each specific row outcome
    # Row 1 (Valid)
    assert staging_records[0].status == "valid"
    assert staging_records[0].anomaly_flags is None
    
    # Row 2 (Duplicate warning -> status flagged)
    assert staging_records[1].status == "flagged"
    assert any(w["code"] == "EXACT_DUPLICATE_ROW" for w in staging_records[1].anomaly_flags["warnings"])

    # Row 3 (Duplicate warning -> status flagged)
    assert staging_records[2].status == "flagged"
    assert any(w["code"] == "EXACT_DUPLICATE_ROW" for w in staging_records[2].anomaly_flags["warnings"])

    # Row 4 (Conflicting duplicate error -> status flagged)
    assert staging_records[3].status == "flagged"
    assert any(e["code"] == "CONFLICTING_DUPLICATE" for e in staging_records[3].anomaly_flags["errors"])

    # Row 5 (Missing Payer error -> status flagged)
    assert staging_records[4].status == "flagged"
    assert any(e["code"] == "MISSING_CRITICAL_DATA" for e in staging_records[4].anomaly_flags["errors"])

    # Row 6 (Negative Amount warning -> status flagged)
    assert staging_records[5].status == "flagged"
    assert any(w["code"] == "NEGATIVE_AMOUNT_REFUND" for w in staging_records[5].anomaly_flags["warnings"])

    # Row 7 (Math split error -> status flagged)
    assert staging_records[6].status == "flagged"
    assert any(e["code"] == "MATHEMATICAL_SPLIT_ERROR" for e in staging_records[6].anomaly_flags["errors"])

    # Row 8 (Membership time violation -> status flagged)
    assert staging_records[7].status == "flagged"
    assert any(e["code"] == "MEMBERSHIP_TIME_VIOLATION" for e in staging_records[7].anomaly_flags["errors"])

    # Row 9 (Settlement Disguised as Expense warning -> status flagged)
    assert staging_records[8].status == "flagged"
    assert any(w["code"] == "SETTLEMENT_DISGUISED_AS_EXPENSE" for w in staging_records[8].anomaly_flags["warnings"])
    
    db.close()
    print("\nCSV Ingestion & Validation Pipeline fully verified!")

if __name__ == "__main__":
    seed_data()
    try:
        test_csv_ingestion_pipeline()
    finally:
        # Release db handles and clean up SQLite file
        try:
            engine.dispose()
            if os.path.exists("test_ingest.db"):
                os.remove("test_ingest.db")
                print("Cleaned up test_ingest.db successfully.")
        except Exception as e:
            print(f"Clean up failed: {e}")
