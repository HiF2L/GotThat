import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select
from app.core.database import Base
from app.models.ontology import Domain, Track, Concept, ConceptDependency, DependencyType
from app.models.mastery import User, UserMasteryState
from app.schemas.tutor import StartDeepSessionRequest, DeepStepPayload
from app.services.graph.knowledge_graph import deterministic_topological_sort, natural_sort_key, knowledge_graph_service
from app.services.tutor.tutor_state_machine import tutor_state_machine


@pytest.mark.asyncio
async def test_natural_sort_key_hierarchy():
    codes = ["M1.01", "M1.10", "M1.02", "M2.01", "M10.01", "MOD3.05", "CS.1.2", "CS.1.10", "CS.1.1"]
    sorted_codes = sorted(codes, key=lambda c: natural_sort_key(c, 0))
    expected = ["CS.1.1", "CS.1.2", "CS.1.10", "M1.01", "M1.02", "M1.10", "M2.01", "M10.01", "MOD3.05"]
    assert sorted_codes == expected


@pytest.mark.asyncio
async def test_deterministic_topological_sort_preserves_prerequisites_and_modules():
    nodes = [
        {"id": "m3_02", "code": "M3.02"},
        {"id": "m1_02", "code": "M1.02"},
        {"id": "m2_01", "code": "M2.01"},
        {"id": "m3_01", "code": "M3.01"},
        {"id": "m1_01", "code": "M1.01"},
        {"id": "m2_02", "code": "M2.02"},
    ]
    deps = [
        ("m1_01", "m2_01"),
        ("m3_01", "m3_02"),
    ]
    sorted_res = deterministic_topological_sort(nodes, deps)
    sorted_codes = [n["code"] for n in sorted_res]

    assert sorted_codes.index("M1.01") < sorted_codes.index("M2.01")
    assert sorted_codes.index("M3.01") < sorted_codes.index("M3.02")
    assert sorted_codes == ["M1.01", "M1.02", "M2.01", "M2.02", "M3.01", "M3.02"]


@pytest.mark.asyncio
async def test_concept_navigation_by_slug_and_id():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        user = User(username="stoic_student", email="stoic@test.local")
        session.add(user)

        domain = Domain(slug="philosophy", title="Философия")
        session.add(domain)
        await session.flush()

        track = Track(domain_id=domain.id, slug="stoic_test", title="Стоицизм")
        session.add(track)
        await session.flush()

        concepts = []
        for mod in range(1, 4):
            for lesson in range(1, 4):
                code = f"M{mod}.0{lesson}"
                c = Concept(
                    track_id=track.id,
                    code=code,
                    slug=f"lesson-{code.lower()}",
                    title=f"Урок {code}",
                    summary=f"Описание {code}",
                )
                concepts.append(c)
        session.add_all(concepts)
        await session.flush()

        d1 = ConceptDependency(source_concept_id=concepts[0].id, target_concept_id=concepts[1].id, relation_type=DependencyType.STRICT_PREREQUISITE)
        d2 = ConceptDependency(source_concept_id=concepts[1].id, target_concept_id=concepts[3].id, relation_type=DependencyType.STRICT_PREREQUISITE)
        session.add_all([d1, d2])

        m1 = UserMasteryState(
            user_id=user.id,
            concept_id=concepts[0].id,
            mastery_prob=0.95,
            uncertainty=0.1,
        )
        session.add(m1)
        await session.commit()

        target_c8 = concepts[7]
        assert target_c8.code == "M3.02"

        deep_sess = await tutor_state_machine.start_session(
            session=session,
            request=StartDeepSessionRequest(
                user_id=user.id,
                target_concept_id=target_c8.slug,
            ),
        )

        assert deep_sess.current_concept_index == 7
        assert deep_sess.current_concept_id == target_c8.id

        dag_nodes = deep_sess.planned_dag["nodes"]
        assert dag_nodes[7]["id"] == target_c8.id
        assert dag_nodes[7]["code"] == "M3.02"
        assert dag_nodes[7]["status"] == "active"

        with patch("app.services.tutor.step_executor.step_executor.execute_atomic_step", new_callable=AsyncMock) as mock_step:
            mock_step.return_value = DeepStepPayload(
                session_id=deep_sess.id,
                concept_id=target_c8.id,
                concept_title=target_c8.title,
                concept_slug=target_c8.slug,
                track_id=track.id,
                track_slug=track.slug,
                step_sequence=8,
                explanation_markdown="Explanation for lesson 8",
            )

            action = await tutor_state_machine.get_next_action(session, deep_sess.id)
            assert action["phase"] == "step_ready"
            assert action["step"].step_sequence == 8
            assert action["step"].concept_title == "Урок M3.02"

        target_c4 = concepts[3]
        with patch("app.services.tutor.step_executor.step_executor.execute_atomic_step", new_callable=AsyncMock) as mock_step:
            mock_step.return_value = DeepStepPayload(
                session_id=deep_sess.id,
                concept_id=target_c4.id,
                concept_title=target_c4.title,
                concept_slug=target_c4.slug,
                track_id=track.id,
                track_slug=track.slug,
                step_sequence=4,
                explanation_markdown="Explanation for lesson 4",
            )
            switch_res = await tutor_state_machine.switch_concept_step(session, deep_sess.id, target_c4.slug)
            assert switch_res["phase"] == "step_ready"
            assert switch_res["step"].step_sequence == 4
            assert switch_res["step"].concept_title == "Урок M2.01"

    await engine.dispose()
