import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.database import Base
from app.models.ontology import Domain, Track, Concept
from app.models.mastery import User
from app.models.session import DeepLearningSession, DeepSessionStep
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.database import get_db_session


@pytest.mark.asyncio
async def test_ask_tutor_in_lesson():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    async with session_factory() as session:
        user = User(username="qa_user", email="qa@user.local")
        session.add(user)
        domain = Domain(slug="physics", title="Physics")
        session.add(domain)
        await session.flush()

        track = Track(domain_id=domain.id, slug="qm", title="Quantum Mechanics")
        session.add(track)
        await session.flush()

        concept = Concept(track_id=track.id, code="QM.1", title="Wave-Particle Duality", summary="Photons and electrons.")
        session.add(concept)
        await session.flush()

        deep_s = DeepLearningSession(user_id=user.id, target_concept_id=concept.id, status="teaching")
        session.add(deep_s)
        await session.flush()

        step = DeepSessionStep(
            session_id=deep_s.id,
            concept_id=concept.id,
            step_sequence=1,
            explanation_markdown="Photons exhibit both wave and particle characteristics as shown in the double-slit experiment.",
        )
        session.add(step)
        await session.commit()
        session_id = deep_s.id

    from unittest.mock import patch, AsyncMock
    with patch("app.services.ai.client.ai_clients.generate_chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = "Placing detectors causes wave function collapse, destroying the phase coherence needed for interference."
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/api/v1/deep/ask-tutor",
                json={
                    "session_id": session_id,
                    "step_sequence": 1,
                    "question": "Why does the interference pattern disappear when detectors are placed at the slits?",
                },
            )
            assert res.status_code == 200
            data = res.json()
            assert "answer_markdown" in data
            assert len(data["answer_markdown"]) > 10

    app.dependency_overrides.clear()
    await engine.dispose()
