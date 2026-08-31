from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
)

async_session_maker = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


from sqlalchemy import text


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Safe SQLite Column Auto-Migrations
        try:
            res = await conn.execute(text("PRAGMA table_info(users)"))
            cols = [r[1] for r in res.fetchall()]
            if "preferred_language" not in cols:
                await conn.execute(text("ALTER TABLE users ADD COLUMN preferred_language VARCHAR(16) DEFAULT 'ru'"))
            if "preferred_model" not in cols:
                await conn.execute(text("ALTER TABLE users ADD COLUMN preferred_model VARCHAR(64) DEFAULT 'kimi-k3'"))
        except Exception:
            pass

        try:
            res = await conn.execute(text("PRAGMA table_info(deep_learning_sessions)"))
            cols = [r[1] for r in res.fetchall()]
            if "language" not in cols:
                await conn.execute(text("ALTER TABLE deep_learning_sessions ADD COLUMN language VARCHAR(16) DEFAULT 'ru'"))
            if "depth_level" not in cols:
                await conn.execute(text("ALTER TABLE deep_learning_sessions ADD COLUMN depth_level VARCHAR(32) DEFAULT 'high'"))
        except Exception:
            pass

        try:
            res = await conn.execute(text("PRAGMA table_info(tracks)"))
            cols = [r[1] for r in res.fetchall()]
            if "description" not in cols:
                await conn.execute(text("ALTER TABLE tracks ADD COLUMN description TEXT"))
            if "user_wishes" not in cols:
                await conn.execute(text("ALTER TABLE tracks ADD COLUMN user_wishes TEXT"))
            if "depth_level" not in cols:
                await conn.execute(text("ALTER TABLE tracks ADD COLUMN depth_level VARCHAR(32) DEFAULT 'high'"))
            if "folder_id" not in cols:
                await conn.execute(text("ALTER TABLE tracks ADD COLUMN folder_id VARCHAR(36)"))
            if "is_pinned" not in cols:
                await conn.execute(text("ALTER TABLE tracks ADD COLUMN is_pinned BOOLEAN DEFAULT 0"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tracks_folder_id ON tracks (folder_id)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tracks_is_pinned ON tracks (is_pinned)"))
        except Exception:
            pass

        try:
            res = await conn.execute(text("PRAGMA table_info(concepts)"))
            cols = [r[1] for r in res.fetchall()]
            if "slug" not in cols:
                await conn.execute(text("ALTER TABLE concepts ADD COLUMN slug VARCHAR(128)"))
            await conn.execute(text("DROP INDEX IF EXISTS ix_concepts_code"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_concepts_code ON concepts (code)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_concepts_slug ON concepts (slug)"))
        except Exception:
            pass
