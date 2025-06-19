from typing import Optional
from sqlmodel import Field, SQLModel
from pydantic import BaseModel


class User(SQLModel, table=True):
    id: Optional[int] = Field(primary_key=True, default=None)
    username: str = Field(index=True, unique=True, min_length=3, max_length=50)
    password: str = Field(min_length=8)
    role: str = Field(default="user", index=True, max_length=20)

class UserCreate(BaseModel):
    username: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class UserOut(BaseModel):
    id: int
    username: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"