from fastapi import FastAPI, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from celery import Celery
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
from settings import setting
import logging
import json

from rate_limiter import RateLimiterMiddleware



@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(engine)
    yield


# Celery config
CELERY_BROKER_URL = setting.CELERY_BROKET_URL
CELERY_RESULT_BACKEND = setting.CELERY_RESULT_BACKEND
celery_app = Celery(
    "worker",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND
)


from websocket_manager import ConnectionManager
manager = ConnectionManager()


# Структурированное логирование
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "level": record.levelname,
            "time": self.formatTime(record, self.datefmt),
            "message": record.getMessage(),
            "name": record.name,
        }
        return json.dumps(log_record)

logging.basicConfig(level=logging.INFO, format='%(message)s')
for handler in logging.root.handlers:
    handler.setFormatter(JsonFormatter())

logger = logging.getLogger("app")



app = FastAPI(
    title="Amina Notes API",
    description="API для управления заметками, пользователями, отправки email, WebSocket, мониторинга и ограничения частоты запросов.",
    version="1.0.0",
    lifespan=lifespan
)
app.add_middleware(RateLimiterMiddleware, limit=10, window=60)
app.include_router(notes_router)

# Инициализация Prometheus метрик
Instrumentator().instrument(app).expose(app)

@app.get(
    "/health",
    summary="Проверка состояния API",
    description="Проверяет, что сервис работает корректно.",
    tags=["Сервис"],
    responses={
        200: {
            "description": "Сервис работает",
            "content": {
                "application/json": {
                    "example": {"status": "ok"}
                }
            }
        }
    }
)
def health():
    logger.info("Health check requested")
    return {"status": "ok"}

# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await manager.broadcast(f"Message: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)



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


# Импорт задачи
from tasks import send_email_task

class EmailRequest(BaseModel):
    email: str = Field(..., description="Email получателя", example="test@example.com")

@app.post(
    "/send-email/",
    summary="Запуск фоновой задачи отправки email",
    description="Запускает задачу Celery для имитации отправки email.",
    tags=["Email"],
    response_model=dict,
    responses={
        200: {
            "description": "Email поставлен в очередь",
            "content": {
                "application/json": {
                    "example": {"task_id": "abc123", "status": "queued"}
                }
            }
        }
    }
)
def send_email(request: EmailRequest):
    task = send_email_task.delay(request.email)
    return {"task_id": task.id, "status": "queued"}

@app.post(
    "/register/",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация пользователя",
    description="Создает нового пользователя.",
    tags=["Пользователи"],
    responses={
        201: {
            "description": "Пользователь успешно создан",
            "content": {
                "application/json": {
                    "example": {"id": 1, "username": "amina", "role": "user"}
                }
            }
        },
        400: {"description": "Имя пользователя уже занято"}
    }
)
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

@app.post(
    "/login/",
    response_model=Token,
    summary="Вход пользователя",
    description="Аутентификация пользователя и выдача токена.",
    tags=["Пользователи"],
    responses={
        200: {
            "description": "Успешный вход",
            "content": {
                "application/json": {
                    "example": {"access_token": "jwt_token", "token_type": "bearer"}
                }
            }
        },
        401: {"description": "Неверные данные"}
    }
)
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

@app.get(
    "/users/me/",
    response_model=UserOut,
    summary="Получить текущего пользователя",
    description="Возвращает данные текущего пользователя.",
    tags=["Пользователи"],
    responses={
        200: {
            "description": "Данные пользователя",
            "content": {
                "application/json": {
                    "example": {"id": 1, "username": "amina", "role": "user"}
                }
            }
        }
    }
)
def read_users_me(current_user: Annotated[User, Depends(get_current_user)]) -> UserOut:
    return current_user


@app.get(
    "/admin/users/",
    response_model=List[UserOut],
    summary="Получить всех пользователей (только для admin)",
    description="Возвращает список всех пользователей. Доступно только для роли admin.",
    tags=["Пользователи"],
    responses={
        200: {
            "description": "Список пользователей",
            "content": {
                "application/json": {
                    "example": [
                        {"id": 1, "username": "amina", "role": "admin"},
                        {"id": 2, "username": "user1", "role": "user"}
                    ]
                }
            }
        },
        403: {"description": "Нет доступа"}
    }
)
def get_users(
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[Session, Depends(get_db)]
) -> List[UserOut]:
    users = db.exec(select(User)).all()
    return [UserOut(id=user.id, username=user.username, role=user.role) for user in users]