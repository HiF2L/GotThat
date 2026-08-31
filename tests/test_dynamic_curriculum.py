import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.database import Base
from app.services.graph.dynamic_curriculum import curriculum_generator
from app.services.tutor.tutor_state_machine import tutor_state_machine
from app.models.ontology import Concept, Track
from app.models.mastery import User
from app.schemas.tutor import StartDeepSessionRequest
from sqlalchemy import select


@pytest_asyncio.fixture
async def async_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        user = User(username="test_learner", email="test@gotit.local")
        session.add(user)
        await session.commit()
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_dynamic_curriculum_generation(async_db: AsyncSession):
    # Mock LLM response for dynamic ontology generation
    mock_curriculum_payload = {
        "domain_slug": "philosophy",
        "domain_title": "Philosophy & Ethics",
        "track_slug": "stoicism_basics",
        "track_title": "Foundations of Stoicism",
        "track_description": "Virtue ethics, Dichotomy of Control, and Marcus Aurelius Meditations.",
        "concepts": [
            {
                "code": "PHIL.STOI.DICHOTOMY",
                "title": "Dichotomy of Control",
                "summary": "Separating what is up to us (internal) from what is not (external).",
                "bloom_level": "understand",
                "quiz": {
                    "prompt": "According to Epictetus, what is within our absolute control?",
                    "options": [
                        {"id": "a", "text": "Our own opinions and desires", "is_correct": True, "explanation": "Internal mental judgements are solely in our power."},
                        {"id": "b", "text": "Our physical health and reputation", "is_correct": False},
                    ],
                },
            },
            {
                "code": "PHIL.STOI.AMOR_FATI",
                "title": "Amor Fati and Acceptance",
                "summary": "Loving one's fate and accepting unavoidable outcomes with equanimity.",
                "bloom_level": "apply",
                "quiz": {
                    "prompt": "What does Amor Fati signify in Stoic thought?",
                    "options": [
                        {"id": "a", "text": "Active embrace of necessary reality", "is_correct": True, "explanation": "Not merely enduring, but embracing fate."},
                        {"id": "b", "text": "Resigning to passive despair", "is_correct": False},
                    ],
                },
            },
        ],
        "dependencies": [
            ["PHIL.STOI.DICHOTOMY", "PHIL.STOI.AMOR_FATI"]
        ],
    }

    user_res = await async_db.execute(select(User).limit(1))
    user = user_res.scalars().first()

    with patch("app.services.ai.client.ai_clients.generate_json", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = mock_curriculum_payload
        track = await curriculum_generator.generate_curriculum(
            session=async_db,
            user_id=user.id,
            topic_query="Стоицизм и Марк Аврелий",
        )

        assert track.title == "Стоицизм и Марк Аврелий"
        concepts_res = await async_db.execute(select(Concept).where(Concept.track_id == track.id))
        concepts = concepts_res.scalars().all()
        assert len(concepts) >= 1
        assert concepts[0].title == "Стоицизм и Марк Аврелий"


@pytest.mark.asyncio
async def test_deep_tutor_probe_lifecycle(async_db: AsyncSession):
    # Create concept
    track = Track(domain_id="dummy", slug="test_track", title="Test Track")
    # Add dummy domain
    from app.models.ontology import Domain
    domain = Domain(slug="test_dom", title="Test Domain")
    async_db.add(domain)
    await async_db.flush()

    track.domain_id = domain.id
    async_db.add(track)
    await async_db.flush()

    c1 = Concept(track_id=track.id, code="TEST.C1", title="Concept 1", summary="Sum 1")
    c2 = Concept(track_id=track.id, code="TEST.C2", title="Concept 2", summary="Sum 2")
    async_db.add_all([c1, c2])
    await async_db.flush()

    user_res = await async_db.execute(select(User).limit(1))
    user = user_res.scalars().first()

    mock_probe_payload = {
        "questions": [
            {
                "id": f"q{i+1}",
                "subtopic_title": f"Subtopic {i+1}",
                "prompt": f"Test question {i+1}?",
                "options": [
                    {"id": "a", "text": "Option A", "is_correct": True, "explanation": "Ok"},
                    {"id": "b", "text": "Option B", "is_correct": False},
                ],
                "difficulty": "medium",
                "bloom_level": "understand",
            }
            for i in range(10)
        ]
    }

    with patch("app.services.ai.client.ai_clients.generate_json", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = mock_probe_payload

        # Start session
        session = await tutor_state_machine.start_session(
            session=async_db,
            request=StartDeepSessionRequest(user_id=user.id, target_concept_id=c2.id),
        )
        assert session.status == "probing"

        # Submit probe answer
        action = await tutor_state_machine.record_probe_answer(
            session=async_db,
            deep_session_id=session.id,
            concept_id=c1.id,
            option_id="yes",
        )
        assert action is not None
