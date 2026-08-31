import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.database import Base
from app.models.ontology import Domain, Track, Concept, ConceptDependency, DependencyType, AssessmentItem
from app.models.mastery import User, UserMasteryState, UserTrackEnrollment
from app.models.session import DeepLearningSession, DeepSessionStep
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.database import get_db_session


@pytest.mark.asyncio
async def test_delete_track_cascade():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    # Seed track and children
    async with session_factory() as session:
        user = User(username="del_user", email="del@user.local")
        session.add(user)
        domain = Domain(slug="del_domain", title="Del Domain")
        session.add(domain)
        await session.flush()

        track = Track(domain_id=domain.id, slug="del_track", title="Delete Me Track")
        session.add(track)
        await session.flush()

        c1 = Concept(track_id=track.id, code="DEL.1", title="Del Concept 1", summary="test")
        c2 = Concept(track_id=track.id, code="DEL.2", title="Del Concept 2", summary="test")
        session.add_all([c1, c2])
        await session.flush()

        dep = ConceptDependency(source_concept_id=c1.id, target_concept_id=c2.id, relation_type=DependencyType.STRICT_PREREQUISITE)
        session.add(dep)

        item = AssessmentItem(concept_id=c1.id, prompt_markdown="Test item", options=[{"id": "a", "text": "A"}])
        session.add(item)

        m = UserMasteryState(user_id=user.id, concept_id=c1.id, mastery_prob=0.9, uncertainty=0.1)
        session.add(m)

        deep_s = DeepLearningSession(user_id=user.id, target_concept_id=c2.id, status="teaching")
        session.add(deep_s)
        await session.commit()
        track_id = track.id

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Delete track
        res = await client.delete(f"/api/v1/tracks/{track_id}")
        assert res.status_code == 200
        assert res.json()["status"] == "deleted"

    # Verify everything is cascaded and deleted
    async with session_factory() as session:
        t_check = await session.execute(select(Track).where(Track.id == track_id))
        assert t_check.scalars().first() is None

        c_check = await session.execute(select(Concept).where(Concept.track_id == track_id))
        assert len(c_check.scalars().all()) == 0

        dep_check = await session.execute(select(ConceptDependency))
        assert len(dep_check.scalars().all()) == 0

    app.dependency_overrides.clear()
    await engine.dispose()
