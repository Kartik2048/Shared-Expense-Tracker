import os
import json
from decimal import Decimal
from datetime import datetime
from io import BytesIO

# Force SQLite database file for testing
os.environ["DATABASE_URL"] = "sqlite:///./test_actions.db"

from fastapi.testclient import TestClient
from app.database import Base, engine, SessionLocal
from app.models import User, Group, GroupMember, StagingExpense, Expense, ExpenseSplit
from app.main import app

client = TestClient(app)

def seed_data():
    db = SessionLocal()
    # Clean and create tables
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    # Users
    kartik = User(name="kartik", email="kartik@example.com")
    aisha = User(name="aisha", email="aisha@example.com")
    rohan = User(name="rohan", email="rohan@example.com")
    priya_s = User(name="priya s", email="priyas@example.com")
    db.add_all([kartik, aisha, rohan, priya_s])
    db.commit()
    
    # Group
    group = Group(name="Flatmates")
    db.add(group)
    db.commit()
    
    # Memberships
    member_kartik = GroupMember(group_id=group.id, user_id=kartik.id, joined_at=datetime(2026, 1, 1))
    member_aisha = GroupMember(group_id=group.id, user_id=aisha.id, joined_at=datetime(2026, 1, 1))
    member_rohan = GroupMember(group_id=group.id, user_id=rohan.id, joined_at=datetime(2026, 1, 1))
    member_priya_s = GroupMember(group_id=group.id, user_id=priya_s.id, joined_at=datetime(2026, 1, 1))
    db.add_all([member_kartik, member_aisha, member_rohan, member_priya_s])
    db.commit()
    
    # Seed staging expenses
    # Staging row 1 (Valid exact splits with space formatting & name with space)
    se1 = StagingExpense(
        id=1,
        raw_date="2026-02-10",
        raw_description="Grocery exact",
        raw_paid_by="kartik",
        raw_amount="1200.00",
        raw_currency="INR",
        raw_split_type="exact",
        raw_split_with="kartik,aisha,priya s",
        raw_split_details="kartik 400; aisha 400; priya s 400",
        status="pending"
    )
    # Staging row 2 (Valid equal splits USD)
    se2 = StagingExpense(
        id=2,
        raw_date="2026-02-11",
        raw_description="Internet USD",
        raw_paid_by="rohan",
        raw_amount="100.00",
        raw_currency="USD",
        raw_split_type="equal",
        raw_split_with="rohan,kartik",
        raw_split_details="",
        status="pending"
    )
    # Staging row 3 (Flagged: missing payer)
    se3 = StagingExpense(
        id=3,
        raw_date="2026-02-12",
        raw_description="Gas Bill",
        raw_paid_by="",
        raw_amount="150.00",
        raw_currency="INR",
        raw_split_type="equal",
        raw_split_with="kartik",
        raw_split_details="",
        status="pending"
    )
    # Staging row 4 (Valid equal splits needing rounding adjustment: 100.00 / 3)
    se4 = StagingExpense(
        id=4,
        raw_date="2026-02-15",
        raw_description="Shared Dinner",
        raw_paid_by="kartik",
        raw_amount="100.00",
        raw_currency="INR",
        raw_split_type="equal",
        raw_split_with="kartik,aisha,rohan",
        raw_split_details="",
        status="pending"
    )
    db.add_all([se1, se2, se3, se4])
    db.commit()
    db.close()
    
    # Run initial validation on staging to set statuses
    # Trigger validate staging
    client.post("/validate-staging")
    print("Database seeded and validated.")


def test_staging_actions():
    db = SessionLocal()
    
    # Generate mock JWT for Kartik (who has email kartik@example.com in seeded db)
    import jwt
    import time
    JWT_SECRET = os.getenv('JWT_SECRET', 'super-secret-key-change-in-production')
    kartik_user = db.query(User).filter(User.email == "kartik@example.com").first()
    assert kartik_user is not None, "Kartik user must exist in seeded database"
    
    payload = {
        "user_id": kartik_user.id,
        "email": kartik_user.email,
        "exp": int(time.time()) + 3600
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    headers = {"Authorization": f"Bearer {token}"}
    
    print("\n--- 1. Testing MODIFY Staging Expense (PUT) ---")
    # Modify Row 3 to supply the missing raw_paid_by
    payload_data = {"raw_paid_by": "aisha"}
    response = client.put("/staging/3", json=payload_data, headers=headers)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["raw_paid_by"] == "aisha"
    # The record should now be re-validated and be VALID
    assert res_json["status"] == "valid"
    
    print("\n--- 2. Testing DISCARD Staging Expense (DELETE) ---")
    # Discard Row 3
    response = client.delete("/staging/3", headers=headers)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    assert response.status_code == 200
    
    # Verify row 3 is discarded
    staging_row3 = db.query(StagingExpense).filter(StagingExpense.id == 3).first()
    assert staging_row3 is not None and staging_row3.status == "discarded", "Staging row 3 status should be 'discarded'"
    
    print("\n--- 3. Testing APPROVE Staging Expense (POST) - Equal USD Splits ---")
    # Row 2 is 100.00 USD. Rate should be 83.5. Equal splits for rohan and kartik (50.00 each)
    response = client.post("/staging/2/approve", headers=headers)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    assert response.status_code == 201
    expense_id = response.json()["expense_id"]
    
    # Verify production records
    expense = db.query(Expense).filter(Expense.id == expense_id).first()
    assert expense is not None
    assert expense.amount == Decimal("100.0000")
    assert expense.exchange_rate_to_inr == Decimal("83.50000000")
    assert expense.currency == "USD"
    
    splits = db.query(ExpenseSplit).filter(ExpenseSplit.expense_id == expense_id).all()
    assert len(splits) == 2
    for s in splits:
        assert s.amount == Decimal("50.0000")
        print(f" -> Split created: User ID {s.user_id} owes {s.amount}")
        
    # Verify Row 2 is marked as approved in staging
    staging_row2 = db.query(StagingExpense).filter(StagingExpense.id == 2).first()
    assert staging_row2 is not None and staging_row2.status == "approved"

    print("\n--- 4. Testing APPROVE Staging Expense (POST) - Penny Rounding Remainder (100.00 / 3) ---")
    # Row 4 is 100.00 INR equal splits for 3 users (kartik, aisha, rohan)
    # 100.00 / 3 = 33.3333... Rounded splits: 33.33 each. Sum = 99.99. 
    # Rounding difference = 0.01. Should be applied to the first splitter (kartik), making it 33.34.
    response = client.post("/staging/4/approve", headers=headers)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    assert response.status_code == 201
    expense_id_rounded = response.json()["expense_id"]
    
    expense_rounded = db.query(Expense).filter(Expense.id == expense_id_rounded).first()
    assert expense_rounded.amount == Decimal("100.0000")
    
    splits_rounded = db.query(ExpenseSplit).filter(ExpenseSplit.expense_id == expense_id_rounded).all()
    assert len(splits_rounded) == 3
    
    split_amounts = [s.amount for s in splits_rounded]
    print(f" -> Calculated Split Shares: {[float(a) for a in split_amounts]}")
    # Verify sum matches total amount
    assert sum(split_amounts) == Decimal("100.0000")
    # First splitter should have 33.34, others 33.33
    assert splits_rounded[0].amount == Decimal("33.3400")
    assert splits_rounded[1].amount == Decimal("33.3300")
    assert splits_rounded[2].amount == Decimal("33.3300")
    
    # Verify Row 4 is marked as approved in staging
    staging_row4 = db.query(StagingExpense).filter(StagingExpense.id == 4).first()
    assert staging_row4 is not None and staging_row4.status == "approved"
    
    print("\n--- 5. Testing APPROVE Staging Expense (POST) - Exact Split Space Parsing & Names With Spaces ---")
    # Row 1 has exact splits: "kartik 400; aisha 400; priya s 400"
    response = client.post("/staging/1/approve", headers=headers)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    assert response.status_code == 201
    expense_id_exact = response.json()["expense_id"]
    
    expense_exact = db.query(Expense).filter(Expense.id == expense_id_exact).first()
    assert expense_exact.amount == Decimal("1200.0000")
    
    splits_exact = db.query(ExpenseSplit).filter(ExpenseSplit.expense_id == expense_id_exact).all()
    assert len(splits_exact) == 3
    for idx, s in enumerate(splits_exact):
        assert s.amount == Decimal("400.0000")
        print(f" -> Split created: User ID {s.user_id} owes {s.amount}")
        
    # Verify Row 1 is marked as approved in staging
    staging_row1 = db.query(StagingExpense).filter(StagingExpense.id == 1).first()
    assert staging_row1 is not None and staging_row1.status == "approved"

    print("\n--- 6. Testing GET /balances ---")
    # Fetch Kartik's balance (User ID 1)
    response = client.get(f"/balances?target_user_id={kartik_user.id}", headers=headers)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["user_name"] == "kartik"
    assert res_json["total_paid_inr"] == 1300.0
    assert res_json["total_owed_inr"] == 4608.34
    assert res_json["net_balance_inr"] == -3308.34
    assert len(res_json["paid_details"]) == 2
    assert len(res_json["owed_details"]) == 3

    print("\n--- 7. Testing GET /staging/report/download ---")
    response = client.get("/staging/report/download", headers=headers)
    print(f"Status Code: {response.status_code}")
    print("Response snippet (first 300 characters):")
    print(response.text[:300])
    assert response.status_code == 200
    assert "SHARED EXPENSES IMPORT REPORT" in response.text
    assert "Total Rows Processed: 4" in response.text

    db.close()
    print("\nStaging actions (Discard, Modify, Approve) and Balances verified successfully!")

if __name__ == "__main__":
    seed_data()
    try:
        test_staging_actions()
    finally:
        # Clean up database connection and file
        try:
            engine.dispose()
            if os.path.exists("test_actions.db"):
                os.remove("test_actions.db")
                print("Cleaned up test_actions.db successfully.")
        except Exception as e:
            print(f"Cleanup failed: {e}")
