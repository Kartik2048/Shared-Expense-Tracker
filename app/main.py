from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app import crud, models, schemas
from app.database import engine, get_db

# Auto-create tables (SQLite/MySQL) on application start
models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Shared Expense Tracker API",
    description="FastAPI backend for tracking shared expenses",
    version="1.0.0"
)

@app.post("/users/", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    """
    Register a new User. Checks for email and username uniqueness.
    """
    db_user_email = crud.get_user_by_email(db, email=user.email)
    if db_user_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    db_user_username = crud.get_user_by_username(db, username=user.username)
    if db_user_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    return crud.create_user(db=db, user=user)


@app.post("/groups/", response_model=schemas.GroupResponse, status_code=status.HTTP_201_CREATED)
def create_group(group: schemas.GroupCreate, db: Session = Depends(get_db)):
    """
    Create a new shared expense Group.
    """
    return crud.create_group(db=db, group=group)


@app.post("/groups/{group_id}/members", response_model=schemas.GroupMemberResponse, status_code=status.HTTP_201_CREATED)
def add_user_to_group(group_id: int, member_data: schemas.GroupMemberAdd, db: Session = Depends(get_db)):
    """
    Add a User to a Group, with an option to specify a custom joined_at datetime.
    """
    db_group = crud.get_group(db, group_id=group_id)
    if not db_group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found"
        )
    
    db_user = crud.get_user(db, user_id=member_data.user_id)
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Optional: check if user is already an active member of this group
    for existing in db_group.members:
        if existing.user_id == member_data.user_id and existing.left_at is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is already an active member of this group"
            )
            
    return crud.add_user_to_group(db=db, group_id=group_id, member_data=member_data)
