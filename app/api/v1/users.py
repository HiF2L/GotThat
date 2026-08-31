import uuid
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db_session
from app.models.mastery import User, UserTrackEnrollment
from app.models.ontology import Track

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/active")
async def get_or_create_active_user(db: AsyncSession = Depends(get_db_session)):
    """
    Returns the active user profile (or creates one if not existing)
    along with their enrolled tracks.
    """
    user_res = await db.execute(select(User).limit(1))
    user = user_res.scalars().first()

    if not user:
        user = User(
            id=str(uuid.uuid4()),
            username="hitori_learner",
            email="learner@gotit.local",
        )
        db.add(user)
        await db.flush()

        # Enroll into all active tracks
        tracks_res = await db.execute(select(Track).where(Track.is_active == True))
        tracks = tracks_res.scalars().all()
        for t in tracks:
            enrollment = UserTrackEnrollment(
                id=str(uuid.uuid4()),
                user_id=user.id,
                track_id=t.id,
                is_active_in_feed=True,
            )
            db.add(enrollment)
        await db.commit()

    return {
        "user_id": user.id,
        "username": user.username,
        "email": user.email,
        "preferred_language": user.preferred_language or "ru",
        "preferred_model": user.preferred_model or "kimi-k3",
    }


class UserSettingsUpdate(BaseModel):
    preferred_language: Optional[str] = None # 'ru' | 'en'
    preferred_model: Optional[str] = None


@router.get("/{user_id}/settings")
async def get_user_settings(
    user_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    user_res = await db.execute(select(User).where(User.id == user_id))
    user = user_res.scalars().first()
    if not user:
        return {"user_id": user_id, "preferred_language": "ru", "preferred_model": "kimi-k3"}
    return {
        "user_id": user.id,
        "preferred_language": user.preferred_language or "ru",
        "preferred_model": user.preferred_model or "kimi-k3",
    }


@router.patch("/{user_id}/settings")
async def update_user_settings(
    user_id: str,
    settings_data: UserSettingsUpdate,
    db: AsyncSession = Depends(get_db_session),
):
    user_res = await db.execute(select(User).where(User.id == user_id))
    user = user_res.scalars().first()
    if user:
        if settings_data.preferred_language:
            user.preferred_language = settings_data.preferred_language
        if settings_data.preferred_model:
            user.preferred_model = settings_data.preferred_model
        await db.commit()
    return {
        "user_id": user_id,
        "preferred_language": user.preferred_language if user else (settings_data.preferred_language or "ru"),
        "preferred_model": user.preferred_model if user else (settings_data.preferred_model or "kimi-k3"),
    }
