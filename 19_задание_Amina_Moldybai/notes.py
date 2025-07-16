from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import Field
import asyncio
from redis_cache import get_redis
from schemas import Note, NoteCreate, NoteUpdate, NoteOut
from sqlmodel import Session, select
from typing import List, Annotated
from data import get_db, get_current_user
from schemas import User

router = APIRouter(tags=["Notes"], prefix="/notes")

@router.post(
    "/",
    response_model=NoteOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать заметку",
    description="Создает новую заметку для текущего пользователя.",
    tags=["Заметки"],
    responses={
        201: {
            "description": "Заметка успешно создана",
            "content": {
                "application/json": {
                    "example": {"id": 1, "title": "Пример", "content": "Текст заметки", "owner_id": 1}
                }
            }
        },
        400: {"description": "Ошибка создания"}
    }
)
def create_note(
    note: NoteCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)]
):
    new_note = Note(
        title=note.title,
        content=note.content,
        owner_id=current_user.id
    )
    db.add(new_note)
    db.commit()
    db.refresh(new_note)
    return new_note

@router.get(
    "/",
    response_model=List[NoteOut],
    summary="Получить список заметок",
    description="Возвращает список заметок текущего пользователя. Поддерживает кеширование и поиск.",
    tags=["Заметки"],
    responses={
        200: {
            "description": "Список заметок",
            "content": {
                "application/json": {
                    "example": [
                        {"id": 1, "title": "Пример", "content": "Текст заметки", "owner_id": 1}
                    ]
                }
            }
        }
    }
)
async def get_notes(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    skip: int = 0,
    limit: int = 10,
    search: str = None
):
    redis = await get_redis()
    cache_key = f"notes:{current_user.id}:{skip}:{limit}:{search}"
    cached = await redis.get(cache_key)
    if cached:
        import json
        return json.loads(cached)
    query = select(Note).where(Note.owner_id == current_user.id)
    if search:
        query = query.where(Note.title.ilike(f"%{search}%"))
    notes = db.exec(query.offset(skip).limit(limit)).all()
    import json
    await redis.set(cache_key, json.dumps([note.dict() for note in notes]), ex=60)
    return notes

@router.get(
    "/{note_id}",
    response_model=NoteOut,
    summary="Получить заметку по ID",
    description="Возвращает заметку по идентификатору, если она принадлежит текущему пользователю.",
    tags=["Заметки"],
    responses={
        200: {
            "description": "Заметка найдена",
            "content": {
                "application/json": {
                    "example": {"id": 1, "title": "Пример", "content": "Текст заметки", "owner_id": 1}
                }
            }
        },
        404: {"description": "Заметка не найдена"},
        403: {"description": "Нет доступа"}
    }
)
async def get_note(
    note_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)]
):
    note = db.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    if note.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this note")
    return note

@router.put(
    "/{note_id}",
    response_model=NoteOut,
    summary="Обновить заметку",
    description="Обновляет заметку по идентификатору, если она принадлежит текущему пользователю.",
    tags=["Заметки"],
    responses={
        200: {
            "description": "Заметка обновлена",
            "content": {
                "application/json": {
                    "example": {"id": 1, "title": "Обновлено", "content": "Новый текст", "owner_id": 1}
                }
            }
        },
        404: {"description": "Заметка не найдена"},
        403: {"description": "Нет доступа"}
    }
)
async def update_note(
    note_id: int,
    note_update: NoteUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)]
):
    redis = await get_redis()
    await redis.delete(f"notes:{current_user.id}:*")
    note = db.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    if note.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this note")
    if note_update.title is not None:
        note.title = note_update.title
    if note_update.content is not None:
        note.content = note_update.content
    db.commit()
    db.refresh(note)
    redis = await get_redis()
    await redis.delete(f"notes:{current_user.id}:*")
    return note

@router.delete(
    "/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить заметку",
    description="Удаляет заметку по идентификатору, если она принадлежит текущему пользователю.",
    tags=["Заметки"],
    responses={
        204: {"description": "Заметка удалена"},
        404: {"description": "Заметка не найдена"},
        403: {"description": "Нет доступа"}
    }
)
async def delete_note(
    note_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)]
):
    note = db.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    if note.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this note")
    db.delete(note)
    db.commit()
    redis = await get_redis()
    await redis.delete(f"notes:{current_user.id}:*")
    return None