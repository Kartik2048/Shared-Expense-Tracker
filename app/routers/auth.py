import os
import time
import jwt
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth
from sqlalchemy.orm import Session
from app.database import get_db
from app import models

router = APIRouter()

oauth = OAuth()
oauth.register(
    name='google',
    client_id=os.getenv('GOOGLE_CLIENT_ID', 'MOCK_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET', 'MOCK_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)

JWT_SECRET = os.getenv('JWT_SECRET', 'super-secret-key-change-in-production')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRY_HOURS = 24

@router.get("/login/google")
async def login_google(request: Request):
    # Determine callback URL dynamically based on request base URL
    redirect_uri = request.url_for('auth_callback')
    # If request is HTTP but proxying HTTPS, fix scheme
    if "localhost" not in redirect_uri and redirect_uri.startswith("http://"):
        redirect_uri = redirect_uri.replace("http://", "https://")
    return await oauth.google.authorize_redirect(request, redirect_uri)

@router.get("/auth/callback", name="auth_callback")
async def auth_callback(request: Request, db: Session = Depends(get_db)):
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OAuth authorization failed: {str(e)}")
    
    userinfo = token.get('userinfo')
    if not userinfo:
        raise HTTPException(status_code=400, detail="Failed to retrieve Google userinfo profile.")
    
    email = userinfo.get('email')
    name = userinfo.get('name')
    if not email:
        raise HTTPException(status_code=400, detail="Google account has no associated email address.")
    
    # Clean email and name
    email = email.strip()
    name = name.strip() if name else email.split('@')[0]
    
    # Find or create user
    user = db.query(models.User).filter(models.User.email.ilike(email)).first()
    if not user:
        user = models.User(name=name, email=email)
        db.add(user)
        db.commit()
        db.refresh(user)
        
    # Generate JWT Token (valid for 24 hours)
    payload = {
        "user_id": user.id,
        "email": user.email,
        "exp": int(time.time()) + (JWT_EXPIRY_HOURS * 3600)
    }
    jwt_token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    
    # Redirect back to the frontend with ?token= in the query parameters
    frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:8000/')
    # Strip any existing query params or hash if simple concat
    if "?" in frontend_url:
        redirect_url = f"{frontend_url}&token={jwt_token}"
    else:
        redirect_url = f"{frontend_url}?token={jwt_token}"
        
    return RedirectResponse(url=redirect_url)
