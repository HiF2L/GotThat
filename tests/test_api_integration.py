import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.main import app
from app.core.database import Base, get_db_session
from app.services.graph.seed_data import seed_initial_knowledge_graph
from app.models.mastery import User
from app.config import settings
from sqlalchemy import select


@pytest_asyncio.fixture
async def client_and_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as s:
        await seed_initial_knowledge_graph(s)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, session_factory

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_health_endpoint(client_and_db):
    client, _ = client_and_db
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["deep_model"] == settings.DEEP_MODEL


@pytest.mark.asyncio
async def test_tracks_and_feed_flow(client_and_db):
    client, session_factory = client_and_db

    # 1. Fetch available tracks
    tracks_res = await client.get("/api/v1/tracks/")
    assert tracks_res.status_code == 200
    tracks = tracks_res.json()
    assert len(tracks) >= 1
    track = tracks[0]

    # 2. Get demo user id
    async with session_factory() as session:
        user_res = await session.execute(select(User).limit(1))
        user = user_res.scalars().first()
        user_id = user.id

    # 3. Request next feed card
    feed_res = await client.get(f"/api/v1/feed/next?user_id={user_id}")
    assert feed_res.status_code == 200
    card = feed_res.json()
    assert "concept_id" in card
    assert "options" in card
    assert len(card["options"]) >= 2

    # 4. Submit answer
    answer_res = await client.post(
        "/api/v1/feed/attempt",
        json={
            "user_id": user_id,
            "card_id": card["card_id"],
            "concept_id": card["concept_id"],
            "selected_option_ids": [card["options"][0]["id"]],
            "response_time_ms": 1200,
        },
    )
    assert answer_res.status_code == 200
    result = answer_res.json()
    assert "posterior_mastery" in result
    assert "is_correct" in result
