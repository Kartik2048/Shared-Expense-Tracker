import os
from decimal import Decimal
from datetime import datetime, timezone

# Force SQLite in-memory for testing
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.database import Base, engine, SessionLocal
from app.models import User, Group, GroupMember, Expense, ExpenseSplit, Settlement, StagingExpense

def run_verification():
    print("Initializing test database schema...")
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        print("Creating mock users...")
        kartik = User(
            username="kartik",
            email="kartik@example.com",
            hashed_password="hashedpassword_kartik"
        )
        alice = User(
            username="alice",
            email="alice@example.com",
            hashed_password="hashedpassword_alice"
        )
        db.add_all([kartik, alice])
        db.commit()
        db.refresh(kartik)
        db.refresh(alice)
        print(f"Users created successfully. Kartik ID: {kartik.id}, Alice ID: {alice.id}")
        
        print("Creating mock group...")
        apartment_group = Group(
            name="Apartment 204",
            description="Shared expenses for Room 204"
        )
        db.add(apartment_group)
        db.commit()
        db.refresh(apartment_group)
        print(f"Group '{apartment_group.name}' created with ID: {apartment_group.id}")
        
        print("Adding users to group with joined_at and left_at timestamps...")
        # Kartik is currently in the group
        member_kartik = GroupMember(
            group_id=apartment_group.id,
            user_id=kartik.id,
            joined_at=datetime(2026, 1, 1, 12, 0)
        )
        # Alice moved in and then left
        member_alice = GroupMember(
            group_id=apartment_group.id,
            user_id=alice.id,
            joined_at=datetime(2026, 1, 1, 12, 0),
            left_at=datetime(2026, 3, 1, 12, 0)
        )
        db.add_all([member_kartik, member_alice])
        db.commit()
        
        # Verify group memberships
        db.refresh(apartment_group)
        print(f"Group member count: {len(apartment_group.members)}")
        for m in apartment_group.members:
            status = f"Left at: {m.left_at}" if m.left_at else "Active member"
            print(f" - Member User ID {m.user_id} ({m.user.username}): Joined at {m.joined_at}, {status}")
            assert m.joined_at is not None
            if m.user_id == alice.id:
                assert m.left_at == datetime(2026, 3, 1, 12, 0)
                
        print("Adding a multi-currency expense paid by Kartik...")
        internet_expense = Expense(
            group_id=apartment_group.id,
            paid_by_id=kartik.id,
            description="Internet subscription (USD)",
            amount=Decimal("49.99"),
            currency="USD",
            exchange_rate_to_inr=Decimal("83.45000000"),
            date=datetime(2026, 2, 1, 10, 0)
        )
        db.add(internet_expense)
        db.commit()
        db.refresh(internet_expense)
        print(f"Expense created: {internet_expense.description}, Amount: {internet_expense.amount} {internet_expense.currency}, Rate: {internet_expense.exchange_rate_to_inr}")
        
        print("Adding splits for the expense...")
        split_kartik = ExpenseSplit(
            expense_id=internet_expense.id,
            user_id=kartik.id,
            amount=Decimal("25.00")
        )
        split_alice = ExpenseSplit(
            expense_id=internet_expense.id,
            user_id=alice.id,
            amount=Decimal("24.99")
        )
        db.add_all([split_kartik, split_alice])
        db.commit()
        
        # Verify expense splits relation
        db.refresh(internet_expense)
        print(f"Expense splits count: {len(internet_expense.splits)}")
        total_split = Decimal("0.0")
        for s in internet_expense.splits:
            print(f" - User {s.user.username} owes {s.amount} of the expense.")
            total_split += s.amount
        assert total_split == internet_expense.amount, f"Splits sum {total_split} != expense amount {internet_expense.amount}"
        
        print("Creating a settlement...")
        settlement = Settlement(
            group_id=apartment_group.id,
            payer_id=alice.id,
            payee_id=kartik.id,
            amount=Decimal("2085.42"),  # 24.99 USD * 83.45 in INR
            currency="INR",
            exchange_rate_to_inr=Decimal("1.00000000"),
            status="completed"
        )
        db.add(settlement)
        db.commit()
        db.refresh(settlement)
        print(f"Settlement: User {settlement.payer.username} settled {settlement.amount} {settlement.currency} to {settlement.payee.username}. Status: {settlement.status}")
        assert settlement.payer_id == alice.id
        assert settlement.payee_id == kartik.id
        
        print("Creating a StagingExpense with CSV strings and JSON anomaly flags...")
        staging_data = StagingExpense(
            raw_description="Rent payment (USD)",
            raw_amount="1200.00",
            raw_currency="USD",
            raw_date="2026-06-12",
            raw_paid_by="kartik",
            raw_group_name="Apartment 204",
            raw_splits="kartik:600,alice:600",
            status="pending",
            anomaly_flags={"warnings": ["User 'alice' is marked as having left the group."]}
        )
        db.add(staging_data)
        db.commit()
        db.refresh(staging_data)
        
        print(f"StagingExpense created: ID {staging_data.id}, Raw Amount: {staging_data.raw_amount}, Status: {staging_data.status}")
        print(f"Anomaly Flags Type: {type(staging_data.anomaly_flags)}")
        print(f"Anomaly Flags Content: {staging_data.anomaly_flags}")
        assert isinstance(staging_data.anomaly_flags, dict)
        assert "warnings" in staging_data.anomaly_flags
        
        print("\nAll model fields, datatypes, and relationships verified successfully!")
        
    finally:
        db.close()

if __name__ == "__main__":
    run_verification()
