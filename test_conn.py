import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Load environment variables
load_dotenv()

db_url = os.getenv("DATABASE_URL")
print(f"Loaded DATABASE_URL: {db_url}")

if not db_url:
    print("Error: DATABASE_URL not found in environment!")
    exit(1)

# Pre-process database URL to support mysql:// using PyMySQL and support SSL arguments
connect_args = {}

if db_url.startswith("mysql://") or db_url.startswith("mysql+pymysql://"):
    if db_url.startswith("mysql://"):
        db_url = db_url.replace("mysql://", "mysql+pymysql://", 1)
    
    if "ssl-mode=REQUIRED" in db_url or "ssl_mode=REQUIRED" in db_url:
        connect_args["ssl"] = {"ssl_mode": "REQUIRED"}
        if "?" in db_url:
            db_url = db_url.split("?")[0]

try:
    print("Connecting to database...")
    engine = create_engine(db_url, connect_args=connect_args, pool_pre_ping=True)
    
    # Import models and Base
    from app.database import Base
    from app.models import User, Group, GroupMember
    
    print("Initializing schema (creating tables if not exist)...")
    Base.metadata.create_all(bind=engine)
    print("Schema initialized successfully!")
    
    # Setup session
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    try:
        print("Inserting test User and Group...")
        user = User(name="Cloud Test User", email="cloud_test@example.com")
        group = Group(name="Cloud Test Group")
        db.add_all([user, group])
        db.commit()
        db.refresh(user)
        db.refresh(group)
        print(f" -> User created: ID {user.id}")
        print(f" -> Group created: ID {group.id}")
        
        print("Adding user to group...")
        membership = GroupMember(group_id=group.id, user_id=user.id)
        db.add(membership)
        db.commit()
        db.refresh(membership)
        print(f" -> Membership created: ID {membership.id}")
        
        # Verify relationship
        db.refresh(group)
        print(f" -> Group members verification: Count = {len(group.members)}")
        for m in group.members:
            print(f"    - Member: {m.user.name}")
            assert m.user.name == "Cloud Test User"
            
        print("\nAll database tables and relationships successfully verified on live MySQL!")
        
        # Clean up test data
        print("Cleaning up test data...")
        db.delete(membership)
        db.delete(user)
        db.delete(group)
        db.commit()
        print("Test data cleaned up successfully.")
        
    finally:
        db.close()
        engine.dispose()
        
except Exception as e:
    print("\nDatabase verification failed!")
    print(f"Error Details: {e}")
