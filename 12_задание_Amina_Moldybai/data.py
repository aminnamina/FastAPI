from passlib.context import CryptContext
import os
from dotenv import load_dotenv
from jose import jwt, JWTError
from datetime import datetime, timedelta, UTC
from sqlmodel import create_engine
from typing import Optional, Annotated
from fastapi.security import OAuth2PasswordBearer
from fastapi import FastAPI, Depends, HTTPException, status
from sqlmodel import Session, select
from schemas import User, UserCreate, UserLogin, UserOut, Token

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=30)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_db():
    db = Session(engine)
    try:
        yield db
    finally:
        db.close()

def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)]
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = get_user(username, db)
    if user is None:
        raise credentials_exception
    return user

def get_user(username: str, db: Session):
    return db.exec(select(User).where(User.username == username)).first()


