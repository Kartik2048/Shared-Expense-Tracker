import os
import sys
from datetime import datetime

# Enable absolute imports for the app module when executed stand-alone
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal, engine, Base
from app.models import User, Group, GroupMember

def seed_database():
    print("Connecting to the database...")
    db = SessionLocal()
    
    try:
        # Step 1: Ensure tables are created
        print("Creating tables if they do not exist...")
        Base.metadata.create_all(bind=engine)
        
        # Step 2: Seed Users
        users_to_seed = [
            {"name": "Aisha", "email": "aisha@example.com"},
            {"name": "Rohan", "email": "rohan@example.com"},
            {"name": "Priya", "email": "priya@example.com"},
            {"name": "Meera", "email": "meera@example.com"},
            {"name": "Dev", "email": "dev@example.com"},
            {"name": "Sam", "email": "sam@example.com"},
        ]
        
        seeded_users = {}
        for u_data in users_to_seed:
            # Check if user already exists by email
            existing_user = db.query(User).filter(User.email == u_data["email"]).first()
            if not existing_user:
                print(f"Creating user: {u_data['name']}")
                new_user = User(name=u_data["name"], email=u_data["email"])
                db.add(new_user)
                db.commit()
                db.refresh(new_user)
                seeded_users[u_data["name"].lower()] = new_user
            else:
                print(f"User {u_data['name']} already exists.")
                seeded_users[u_data["name"].lower()] = existing_user
                
        # Step 3: Seed Group
        group_name = "Flatmates"
        flatmates_group = db.query(Group).filter(Group.name == group_name).first()
        if not flatmates_group:
            print(f"Creating group: {group_name}")
            flatmates_group = Group(name=group_name)
            db.add(flatmates_group)
            db.commit()
            db.refresh(flatmates_group)
        else:
            print(f"Group {group_name} already exists.")
            
        # Step 4: Seed Group Memberships
        # Clean existing memberships for this group to avoid duplicates and ensure clean boundaries
        db.query(GroupMember).filter(GroupMember.group_id == flatmates_group.id).delete()
        db.commit()
        
        memberships_to_seed = [
            {"name": "aisha", "joined": "2026-02-01", "left": None},
            {"name": "rohan", "joined": "2026-02-01", "left": None},
            {"name": "priya", "joined": "2026-02-01", "left": None},
            {"name": "meera", "joined": "2026-02-01", "left": "2026-03-31"},
            {"name": "sam", "joined": "2026-04-01", "left": None},
            {"name": "dev", "joined": "2026-03-08", "left": "2026-03-15"},
        ]
        
        print(f"Adding memberships to group '{group_name}'...")
        for m_data in memberships_to_seed:
            user_obj = seeded_users.get(m_data["name"])
            if not user_obj:
                print(f"Error: User '{m_data['name']}' not found in cache. Skipping.")
                continue
                
            joined_dt = datetime.strptime(m_data["joined"], "%Y-%m-%d")
            left_dt = datetime.strptime(m_data["left"], "%Y-%m-%d") if m_data["left"] else None
            
            member_link = GroupMember(
                group_id=flatmates_group.id,
                user_id=user_obj.id,
                joined_at=joined_dt,
                left_at=left_dt
            )
            db.add(member_link)
            print(f" -> Linked {user_obj.name}: Joined={m_data['joined']}, Left={m_data['left']}")
            
        db.commit()
        print("Database seeding completed successfully!")
        
    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
