from fastapi import FastAPI, Depends, HTTPException, status
from sqlmodel import Field, SQLModel, Session, select
from typing import Optional, Annotated, List
from pydantic import BaseModel
from contextlib import asynccontextmanager
from data import engine, pwd_context, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES, SECRET_KEY, ALGORITHM, oauth2_scheme, JWTError
from datetime import timedelta
from jose import jwt
from schemas import User, UserCreate, UserLogin, UserOut, Token
from notes import router as notes_router
from data import get_db, get_current_user, get_user



@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(engine)
    yield

app = FastAPI(lifespan=lifespan)
app.include_router(notes_router)



def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)



def require_role(role: str):
    def role_checker(user: Annotated[User, Depends(get_current_user)]):
        if user.role != role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted",
            )
        return user
    return role_checker

@app.post("/register/", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(user: UserCreate, db: Session = Depends(get_db)):
    db_user = get_user(user.username, db)
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )

    user.password = hash_password(user.password)
    new_user = User(username=user.username, password=user.password, role="user")
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.post("/login/", response_model=Token)
def login(credentials: UserLogin, db: Annotated[Session, Depends(get_db)]):
    user = get_user(credentials.username, db)
    if not user or not verify_password(credentials.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"}
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user.username}, expires_delta=access_token_expires)
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/users/me/", response_model=UserOut)
def read_users_me(current_user: Annotated[User, Depends(get_current_user)]) -> UserOut:
    return current_user


@app.get("/admin/users/", response_model=List[UserOut])
def get_users(
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[Session, Depends(get_db)]
) -> List[UserOut]:
    users = db.exec(select(User)).all()
    return [UserOut(id=user.id, username=user.username, role=user.role) for user in users]