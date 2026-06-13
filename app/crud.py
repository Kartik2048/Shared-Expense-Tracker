import hashlib
from sqlalchemy.orm import Session
from app import models, schemas

def get_user(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.id == user_id).first()

def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()

def get_user_by_username(db: Session, username: str):
    return db.query(models.User).filter(models.User.username == username).first()

def create_user(db: Session, user: schemas.UserCreate):
    # Simple SHA-256 hashing for password safety without external heavy dependency
    hashed_password = hashlib.sha256(user.password.encode("utf-8")).hexdigest()
    
    db_user = models.User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def get_group(db: Session, group_id: int):
    return db.query(models.Group).filter(models.Group.id == group_id).first()

def create_group(db: Session, group: schemas.GroupCreate):
    db_group = models.Group(
        name=group.name,
        description=group.description
    )
    db.add(db_group)
    db.commit()
    db.refresh(db_group)
    return db_group

def add_user_to_group(db: Session, group_id: int, member_data: schemas.GroupMemberAdd):
    # If joined_at is provided, use it; otherwise, the database model default will kick in
    extra_args = {}
    if member_data.joined_at is not None:
        # Strip timezone if present to align with timezone-naive schema
        joined_at_naive = member_data.joined_at.replace(tzinfo=None)
        extra_args["joined_at"] = joined_at_naive
        
    db_member = models.GroupMember(
        group_id=group_id,
        user_id=member_data.user_id,
        **extra_args
    )
    db.add(db_member)
    db.commit()
    db.refresh(db_member)
    return db_member
