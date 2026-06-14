import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Load environment variables from .env file
load_dotenv()

# Default to MySQL local database, fallback to local SQLite database for easy testing
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://root:password@localhost:3306/shared_expenses"
)

# Pre-process database URL to support mysql:// using PyMySQL and support SSL arguments
connect_args = {}

if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
elif DATABASE_URL.startswith("mysql://") or DATABASE_URL.startswith("mysql+pymysql://"):
    # Replace default mysql protocol with pymysql for pure-Python client support
    if DATABASE_URL.startswith("mysql://"):
        DATABASE_URL = DATABASE_URL.replace("mysql://", "mysql+pymysql://", 1)
    
    # Extract SSL mode if present, then clean up query parameters to avoid PyMySQL parsing failures
    if "ssl-mode=REQUIRED" in DATABASE_URL or "ssl_mode=REQUIRED" in DATABASE_URL:
        connect_args["ssl"] = {"ssl_mode": "REQUIRED"}
        if "?" in DATABASE_URL:
            DATABASE_URL = DATABASE_URL.split("?")[0]

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,  # recommended for MySQL to prevent stale connections
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# FastAPI dependency helper
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
