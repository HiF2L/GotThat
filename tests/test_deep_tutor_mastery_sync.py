import pytest
import pytest_asyncio
import uuid
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select, and_

from app.core.database import Base
from app.models.ontology import Domain, Track, Concept, ConceptDependency, DependencyType
from app.models.mastery import User, UserMasteryState
from app.models.session import DeepLearningSession
from app.services.tutor.tutor_state_machine import tutor_state_machine, is_concept_mastered
from app.schemas.tutor import StartDeepSessionRequest
from app.api.v1.tracks import get_user_track_mastery


@pytest_asyncio.fixture
async def async_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async_session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    
    await engine.dispose()


@pytest.mark.asyncio
async def test_deep_tutor_mastery_sync_and_navigation(async_db: AsyncSession):
    # 1. Setup User and Domain
    user = User(id="test_user_mastery", username="tester", email="test@test.local")
    async_db.add(user)

    domain = Domain(id="dom_1", slug="test_domain", title="Test Domain", description="Test Domain")
    async_db.add(domain)

    track = Track(
        id="track_python",
        domain_id="dom_1",
        slug="python-backend",
        title="Python Backend",
        description="Learn backend development",
        depth_level="low",
    )
    async_db.add(track)

    # Create 4 concepts
    c1 = Concept(id="c1", track_id=track.id, slug="python-basics", code="PY.01", title="Python Basics", summary="Basics")
    c2 = Concept(id="c2", track_id=track.id, slug="fastapi-core", code="PY.02", title="FastAPI Core", summary="FastAPI")
    c3 = Concept(id="c3", track_id=track.id, slug="sqlalchemy-db", code="PY.03", title="SQLAlchemy DB", summary="Database")
    c4 = Concept(id="c4", track_id=track.id, slug="asyncio-concurrency", code="PY.04", title="AsyncIO", summary="Concurrency")
    async_db.add_all([c1, c2, c3, c4])

    # Add dependencies: c1 -> c2 -> c3 -> c4
    d1 = ConceptDependency(source_concept_id=c1.id, target_concept_id=c2.id, relation_type=DependencyType.STRICT_PREREQUISITE)
    d2 = ConceptDependency(source_concept_id=c2.id, target_concept_id=c3.id, relation_type=DependencyType.STRICT_PREREQUISITE)
    d3 = ConceptDependency(source_concept_id=c3.id, target_concept_id=c4.id, relation_type=DependencyType.STRICT_PREREQUISITE)
    async_db.add_all([d1, d2, d3])
    await async_db.commit()

    # 2. Start session with track slug
    req = StartDeepSessionRequest(
        user_id=user.id,
        target_concept_id=track.slug,
        initial_user_context="Starting course",
        language="ru",
    )
    session_obj = await tutor_state_machine.start_session(async_db, req)

    # Verify that the active concept is the FIRST concept (c1), NOT the last concept (c4)!
    assert session_obj.current_concept_index == 0
    assert session_obj.current_concept_id == c1.id
    assert session_obj.status == "teaching"

    dag = session_obj.planned_dag
    assert dag["total_nodes"] == 4
    assert dag["completed_nodes"] == 0
    assert dag["nodes"][0]["status"] == "active"
    assert dag["nodes"][1]["status"] == "pending"

    # 3. Simulate mastery of c1 (User passes verification)
    m1 = UserMasteryState(
        user_id=user.id,
        concept_id=c1.id,
        mastery_prob=0.95,
        uncertainty=0.10,
    )
    async_db.add(m1)
    await async_db.commit()

    # Advance to next node
    await tutor_state_machine.advance_to_next_node(async_db, session_obj.id)
    await async_db.refresh(session_obj)

    assert session_obj.current_concept_index == 1
    assert session_obj.current_concept_id == c2.id
    updated_dag = session_obj.planned_dag
    assert updated_dag["completed_nodes"] == 1
    assert updated_dag["nodes"][0]["status"] == "completed"
    assert updated_dag["nodes"][1]["status"] == "active"
    assert updated_dag["nodes"][2]["status"] == "pending"
    assert ":::completed" in session_obj.mermaid_diagram

    # 4. Check track overview
    overview = await get_user_track_mastery(track_id=track.slug, user_id=user.id, db=async_db)
    assert overview.total_concepts == 4
    assert overview.mastered_concepts == 1
    assert overview.concepts[0].concept_id == c1.id
    assert overview.concepts[0].is_mastered is True
    assert overview.concepts[1].concept_id == c2.id
    assert overview.concepts[1].is_mastered is False

    # 5. Simulate resuming session with track slug -> must retain 1/4 completed and active c2
    req_resume = StartDeepSessionRequest(
        user_id=user.id,
        target_concept_id=track.slug,
        initial_user_context="Continuing course",
        language="ru",
    )
    resumed_session = await tutor_state_machine.start_session(async_db, req_resume)
    assert resumed_session.id == session_obj.id
    assert resumed_session.current_concept_index == 1
    assert resumed_session.current_concept_id == c2.id
    assert resumed_session.planned_dag["completed_nodes"] == 1
    assert resumed_session.planned_dag["nodes"][0]["status"] == "completed"
    assert resumed_session.planned_dag["nodes"][1]["status"] == "active"

    # 6. Simulate smart-skip: c2 is also mastered before taking lesson
    m2 = UserMasteryState(
        user_id=user.id,
        concept_id=c2.id,
        mastery_prob=0.92,
        uncertainty=0.15,
    )
    async_db.add(m2)
    await async_db.commit()

    # Call advance
    await tutor_state_machine.advance_to_next_node(async_db, session_obj.id)
    await async_db.refresh(session_obj)

    # c2 was mastered, so active node should skip c2 and move to c3!
    assert session_obj.current_concept_index == 2
    assert session_obj.current_concept_id == c3.id
    assert session_obj.planned_dag["completed_nodes"] == 2
    assert session_obj.planned_dag["nodes"][0]["status"] == "completed"
    assert session_obj.planned_dag["nodes"][1]["status"] == "completed"
    assert session_obj.planned_dag["nodes"][2]["status"] == "active"
