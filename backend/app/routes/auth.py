from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import timedelta
from backend.app.database import get_db, settings
from backend.app.models import User
from backend.app.schemas import UserCreate, UserLogin, UserOut, Token
from backend.app.auth.security import get_password_hash, verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register_patient(user_in: UserCreate, db: Session = Depends(get_db)):
    """
    Public registration endpoint. Forces role to 'patient'.
    Case-insensitive uniqueness check on email.
    """
    # Force lowercase email check
    email_lower = user_in.email.lower()
    existing_user = db.query(User).filter(func.lower(User.email) == email_lower).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
        
    hashed_password = get_password_hash(user_in.password)
    new_user = User(
        email=email_lower,
        password_hash=hashed_password,
        role="patient",  # Forced to patient
        first_name=user_in.first_name,
        last_name=user_in.last_name
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.post("/login", response_model=Token)
def login(credentials: UserLogin, db: Session = Depends(get_db)):
    """
    Login endpoint. Supports case-insensitive email lookup.
    """
    email_lower = credentials.email.lower()
    user = db.query(User).filter(func.lower(User.email) == email_lower).first()
    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    access_token = create_access_token(
        data={"sub": user.email, "role": user.role}
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user.role
    }

@router.get("/me", response_model=UserOut)
def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user
