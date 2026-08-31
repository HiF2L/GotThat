import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.database import Base
from app.services.graph.dynamic_curriculum import curriculum_generator
from app.services.tutor.plan_phase import plan_manager
from app.services.tutor.tutor_state_machine import tutor_state_machine
from app.models.ontology import Concept, Track, Domain
from app.models.mastery import User, UserMasteryState
from app.models.session import DeepLearningSession
from app.schemas.tutor import StartDeepSessionRequest
from sqlalchemy import select


@pytest_asyncio.fixture
async def async_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        user = User(username="expansion_learner", email="learner@test.local")
        session.add(user)
        domain = Domain(slug="physics", title="Физика")
        session.add(domain)
        await session.commit()
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_track_expansion_service(async_db: AsyncSession):
    # 1. Setup user & track
    user_res = await async_db.execute(select(User).limit(1))
    user = user_res.scalars().first()

    mock_initial_curriculum = {
        "domain_slug": "physics",
        "domain_title": "Физика",
        "track_slug": "quantum_entanglement",
        "track_title": "Квантовая запутанность",
        "track_description": "Основы квантовой запутанности.",
        "concepts": [
            {"code": "Q.01", "title": "Кубиты и суперпозиция", "summary": "Основы суперпозиции", "bloom_level": "understand"},
            {"code": "Q.02", "title": "Парадокс ЭПР", "summary": "Парадокс Эйнштейна-Подольского-Розена", "bloom_level": "understand"},
        ],
        "dependencies": [["Q.01", "Q.02"]],
    }

    with patch("app.services.ai.client.ai_clients.generate_json", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = mock_initial_curriculum
        track = await curriculum_generator.generate_curriculum(
            session=async_db,
            user_id=user.id,
            topic_query="Квантовая запутанность",
            depth_level="low",
        )
    assert track.depth_level == "low"

    # Add 2 initial concepts (one mastered)
    c1 = Concept(
        track_id=track.id,
        code="Q.01",
        title="Кубиты и суперпозиция",
        summary="Основы суперпозиции",
    )
    c2 = Concept(
        track_id=track.id,
        code="Q.02",
        title="Парадокс ЭПР",
        summary="Парадокс Эйнштейна-Подольского-Розена",
    )
    async_db.add_all([c1, c2])
    await async_db.flush()

    # User has mastered c1
    m1 = UserMasteryState(
        user_id=user.id,
        concept_id=c1.id,
        mastery_prob=0.95,
        uncertainty=0.1,
    )
    async_db.add(m1)
    await async_db.commit()

    # 2. Mock expanded curriculum generation (High depth with 6 concepts)
    mock_expanded_payload = {
        "concepts": [
            {"code": "EXP.01", "title": "Кубиты и суперпозиция", "summary": "Фундамент", "bloom_level": "understand", "is_already_mastered": True},
            {"code": "EXP.02", "title": "Парадокс ЭПР и локальный реализм", "summary": "Теория", "bloom_level": "understand", "is_already_mastered": False},
            {"code": "EXP.03", "title": "Неравенства Белла", "summary": "Экспериментальная проверка", "bloom_level": "apply", "is_already_mastered": False},
            {"code": "EXP.04", "title": "Квантовая телепортация", "summary": "Протокол переноса состояния", "bloom_level": "apply", "is_already_mastered": False},
            {"code": "EXP.05", "title": "Квантовая криптография (BB84 & E91)", "summary": "Прикладные протоколы", "bloom_level": "analyze", "is_already_mastered": False},
            {"code": "EXP.06", "title": "Декогеренция и квантовые повторители", "summary": "Инженерия квантовой памяти", "bloom_level": "evaluate", "is_already_mastered": False},
        ],
        "dependencies": [
            ["EXP.01", "EXP.02"],
            ["EXP.02", "EXP.03"],
            ["EXP.03", "EXP.04"],
            ["EXP.04", "EXP.05"],
            ["EXP.05", "EXP.06"],
        ],
    }

    with patch("app.services.ai.client.ai_clients.generate_json", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = mock_expanded_payload

        expanded_dag = await plan_manager.expand_track_curriculum(
            session=async_db,
            user_id=user.id,
            track_id=track.id,
            target_depth_level="high",
            user_notes="Больше упора на протоколы связи",
        )

        assert expanded_dag is not None
        assert expanded_dag.total_nodes == 6
        assert len(expanded_dag.nodes) == 6

        # Check that track depth level was updated in DB
        await async_db.refresh(track)
        assert track.depth_level == "high"

        # Check that new concepts exist in DB
        concepts_res = await async_db.execute(select(Concept).where(Concept.track_id == track.id))
        all_concepts = concepts_res.scalars().all()
        assert len(all_concepts) == 6

        # Check that mastery state for "Кубиты и суперпозиция" was preserved
        c1_new = next((c for c in all_concepts if "Кубиты" in c.title), None)
        assert c1_new is not None
        m_check = await async_db.execute(
            select(UserMasteryState).where(
                UserMasteryState.user_id == user.id,
                UserMasteryState.concept_id == c1_new.id,
            )
        )
        m_row = m_check.scalars().first()
        assert m_row is not None
        assert m_row.mastery_prob >= 0.85


@pytest.mark.asyncio
async def test_track_expansion_api_endpoint():
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    mock_gen_payload = {
        "domain_slug": "architecture",
        "domain_title": "Архитектура",
        "track_slug": "microservices",
        "track_title": "Микросервисная архитектура",
        "track_description": "Паттерны микросервисов.",
        "concepts": [
            {"code": "MS.01", "title": "Монолит vs Микросервисы", "summary": "Введение", "bloom_level": "understand"},
        ],
        "dependencies": [],
    }

    mock_payload = {
        "concepts": [
            {"code": "MS.01", "title": "Монолит vs Микросервисы", "summary": "Введение", "bloom_level": "understand", "is_already_mastered": True},
            {"code": "MS.02", "title": "API Gateway & Reverse Proxy", "summary": "Шлюзы", "bloom_level": "understand", "is_already_mastered": False},
            {"code": "MS.03", "title": "Event-Driven & Message Brokers", "summary": "Kafka и RabbitMQ", "bloom_level": "apply", "is_already_mastered": False},
            {"code": "MS.04", "title": "Паттерн Saga и распределенные транзакции", "summary": "Консистентность", "bloom_level": "apply", "is_already_mastered": False},
        ],
        "dependencies": [
            ["MS.01", "MS.02"],
            ["MS.02", "MS.03"],
            ["MS.03", "MS.04"],
        ],
    }

    with patch("app.services.ai.client.ai_clients.generate_json", new_callable=AsyncMock) as mock_llm:
        mock_llm.side_effect = lambda messages, **kwargs: (
            mock_payload if any("Expand" in str(m) or "EXPAND" in str(m) or "6-20" in str(m) or "expanded" in str(m).lower() for m in messages)
            else mock_gen_payload
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # Create a track
            gen_res = await ac.post("/api/v1/tracks/generate", json={
                "user_id": "test_user_exp",
                "topic_query": "Микросервисная архитектура",
                "depth_level": "low",
            })
            assert gen_res.status_code == 200
            track_data = gen_res.json()
            track_id = track_data["track_id"]
            assert track_data["depth_level"] == "low"

            # Expand the track
            exp_res = await ac.post(f"/api/v1/tracks/{track_id}/expand", json={
                "user_id": "test_user_exp",
                "depth_level": "high",
                "user_notes": "С упором на брокеры сообщений",
            })
            assert exp_res.status_code == 200
            exp_data = exp_res.json()
            assert exp_data["track_id"] == track_id
            assert exp_data["depth_level"] == "high"
            assert exp_data["total_concepts"] == 4
            assert len(exp_data["concepts"]) == 4


@pytest.mark.asyncio
async def test_track_arc_resumes_at_first_unmastered_concept(async_db: AsyncSession):
    user_res = await async_db.execute(select(User).limit(1))
    user = user_res.scalars().first()

    mock_rel_gen = {
        "domain_slug": "physics",
        "domain_title": "Физика",
        "track_slug": "relativity",
        "track_title": "Теория относительности",
        "track_description": "СТО и ОТО",
        "concepts": [{"code": "REL.01", "title": "Принцип относительности Галилея", "summary": "Классика", "bloom_level": "understand"}],
        "dependencies": [],
    }

    # 4 concepts in track, concepts 0 and 1 are already mastered
    mock_concepts_payload = {
        "concepts": [
            {"code": "REL.01", "title": "Принцип относительности Галилея", "summary": "Классика", "bloom_level": "understand", "is_already_mastered": True},
            {"code": "REL.02", "title": "Постулаты Эйнштейна", "summary": "СТО", "bloom_level": "understand", "is_already_mastered": True},
            {"code": "REL.03", "title": "Замедление времени и релятивистские эффекты", "summary": "Лоренц", "bloom_level": "apply", "is_already_mastered": False},
            {"code": "REL.04", "title": "Эквивалентность массы и энергии (E=mc^2)", "summary": "Синтез", "bloom_level": "evaluate", "is_already_mastered": False},
        ],
        "dependencies": [
            ["REL.01", "REL.02"],
            ["REL.02", "REL.03"],
            ["REL.03", "REL.04"],
        ],
    }

    with patch("app.services.ai.client.ai_clients.generate_json", new_callable=AsyncMock) as mock_llm:
        mock_llm.side_effect = lambda messages, **kwargs: (
            mock_concepts_payload if any("Expand" in str(m) or "EXPAND" in str(m) or "6-20" in str(m) or "expanded" in str(m).lower() for m in messages)
            else mock_rel_gen
        )

        track = await curriculum_generator.generate_curriculum(
            session=async_db,
            user_id=user.id,
            topic_query="Теория относительности",
            depth_level="low",
        )

        await plan_manager.expand_track_curriculum(
            session=async_db,
            user_id=user.id,
            track_id=track.id,
            target_depth_level="high",
        )

    # Now simulate user clicking "Start complete guided deep arc" for this track (passing track slug or track ID)
    session = await tutor_state_machine.start_session(
        session=async_db,
        request=StartDeepSessionRequest(
            user_id=user.id,
            target_concept_id=track.slug,
        ),
    )

    # Session MUST land on the 3rd concept (index 2: "Замедление времени"), skipping the first 2 mastered ones!
    assert session.status == "teaching"
    assert session.current_concept_index == 2

    # Fetch concepts to check title
    concepts_res = await async_db.execute(select(Concept).where(Concept.id == session.current_concept_id))
    current_c = concepts_res.scalars().first()
    assert current_c is not None
    assert "Замедление времени" in current_c.title

