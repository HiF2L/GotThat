import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.database import Base
from app.models.ontology import Domain, Track, Concept, ConceptDependency, DependencyType
from app.models.mastery import User, UserMasteryState
from app.models.session import DeepLearningSession, DeepSessionStep

from app.schemas.tutor import StartDeepSessionRequest, DeepStepAnswerSubmission
from app.services.tutor.tutor_state_machine import tutor_state_machine
from app.services.tutor.step_executor import step_executor
from app.services.ai.client import ai_clients


@pytest.mark.asyncio
async def test_continuous_multi_concept_arc():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    mock_probe_payload = {
        "questions": [
            {
                "id": f"q{i+1}",
                "subtopic_title": f"Subtopic {i+1}",
                "prompt": f"Test question {i+1}?",
                "options": [
                    {"id": "a", "text": "Correct option", "is_correct": True, "explanation": "Correct"},
                    {"id": "b", "text": "Distractor", "is_correct": False, "explanation": "Incorrect"},
                ],
                "difficulty": "medium",
                "bloom_level": "understand",
            }
            for i in range(10)
        ]
    }

    mock_plan_payload = {
        "concepts": [
            {"code": "CALC.1", "title": "Limits and Continuity", "summary": "Foundations of limits.", "bloom_level": "understand", "is_already_mastered": False},
            {"code": "CALC.2", "title": "Derivatives", "summary": "Rate of change.", "bloom_level": "apply", "is_already_mastered": False},
            {"code": "CALC.3", "title": "Integrals", "summary": "Accumulation and area.", "bloom_level": "evaluate", "is_already_mastered": False},
        ],
        "dependencies": [
            ["CALC.1", "CALC.2"],
            ["CALC.2", "CALC.3"],
        ],
    }

    mock_teach_payload = {
        "explanation_markdown": "### Intuition & First Principles\n\nCalculus formalizes dynamic systems and change through rigorous infinitesimal limits and accumulation of continuous quantities.",
        "needs_visual_diagram": False,
        "needs_real_image": False,
        "verification_question": {
            "prompt": "What is the core definition of a derivative?",
            "options": [
                {"id": "a", "text": "Instantaneous rate of change as limit approaches 0", "is_correct": True, "explanation": "Correct."},
                {"id": "b", "text": "Total accumulated area", "is_correct": False, "explanation": "Incorrect."},
            ],
        },
        "options": [
            {"id": "a", "text": "Instantaneous rate of change as limit approaches 0", "is_correct": True, "explanation": "Correct."},
            {"id": "b", "text": "Total accumulated area", "is_correct": False, "explanation": "Incorrect."},
        ],
    }

    with patch.object(ai_clients, "generate_json", new_callable=AsyncMock) as mock_json, \
         patch.object(ai_clients, "generate_chat", new_callable=AsyncMock) as mock_chat, \
         patch("app.services.ai.visualizer.visualizer.generate_visualization", new_callable=AsyncMock) as mock_vis, \
         patch("app.services.ai.fact_checker.fact_checker.verify_concept_explanation", new_callable=AsyncMock) as mock_fc, \
         patch("app.services.ai.image_finder.image_finder.find_educational_image", new_callable=AsyncMock) as mock_img:

        def _extract_messages(*args, **kwargs):
            if "messages" in kwargs:
                return kwargs["messages"]
            for a in args:
                if isinstance(a, list):
                    return a
            return []

        def _mock_chat_dispatcher(*args, **kwargs):
            messages = _extract_messages(*args, **kwargs)
            combined = " ".join(str(m.get("content", "")) for m in messages if isinstance(m, dict))
            if "Moderation" in combined or "Safety" in combined or "Classify" in combined:
                return "ALLOWED"
            return "### Intuition & First Principles\n\nCalculus formalizes dynamic systems and change through rigorous infinitesimal limits and accumulation of continuous quantities over continuous intervals."

        def _mock_json_dispatcher(*args, **kwargs):
            messages = _extract_messages(*args, **kwargs)
            combined = " ".join(str(m.get("content", "")) for m in messages if isinstance(m, dict))
            if "technical examiner" in combined or "diagnostic interview" in combined.lower() or "DIAGNOSTIC INTERVIEW" in combined:
                return mock_probe_payload
            elif "curriculum architect" in combined or "Zero-to-Mastery Course" in combined:
                return mock_plan_payload
            else:
                return mock_teach_payload

        mock_chat.side_effect = _mock_chat_dispatcher
        mock_json.side_effect = _mock_json_dispatcher
        mock_vis.return_value = None
        mock_fc.return_value = None
        mock_img.return_value = None

        async with session_factory() as session:
            # Create user
            user = User(username="arc_learner", email="learner@arc.local")
            session.add(user)

            # Create Domain and Track
            domain = Domain(slug="math", title="Mathematics")
            session.add(domain)
            await session.flush()

            track = Track(domain_id=domain.id, slug="calc_arc", title="Calculus Arc")
            session.add(track)
            await session.flush()

            # Create 3 concepts in sequence: C1 -> C2 -> C3
            c1 = Concept(track_id=track.id, code="CALC.1", title="Limits and Continuity", summary="Foundations of limits.")
            c2 = Concept(track_id=track.id, code="CALC.2", title="Derivatives", summary="Rate of change.")
            c3 = Concept(track_id=track.id, code="CALC.3", title="Integrals", summary="Accumulation and area.")
            session.add_all([c1, c2, c3])
            await session.flush()

            # Add dependencies C1 -> C2 -> C3
            d1 = ConceptDependency(source_concept_id=c1.id, target_concept_id=c2.id, relation_type=DependencyType.STRICT_PREREQUISITE)
            d2 = ConceptDependency(source_concept_id=c2.id, target_concept_id=c3.id, relation_type=DependencyType.STRICT_PREREQUISITE)
            session.add_all([d1, d2])
            await session.commit()

            # 1. Start Session even if user picked C1 - the arc should include the entire track!
            deep_session = await tutor_state_machine.start_session(
                session=session,
                request=StartDeepSessionRequest(user_id=user.id, target_concept_id=c1.id),
            )
            assert deep_session.status == "probing"

            # 2. Complete Multi-Stage Diagnostic Interview -> Moves to Planning
            probe_action = await tutor_state_machine.record_probe_answer(
                session=session,
                deep_session_id=deep_session.id,
                concept_id=c1.id,
                option_id="idk",
            )
            while probe_action.get("phase") == "probing":
                next_q = probe_action.get("probe_question", {})
                c_id = next_q.get("concept_id", c2.id)
                probe_action = await tutor_state_machine.record_probe_answer(
                    session=session,
                    deep_session_id=deep_session.id,
                    concept_id=c_id,
                    option_id="idk",
                )

            if probe_action.get("phase") == "plan_ready":
                probe_action = await tutor_state_machine.get_next_action(session, deep_session.id)

            assert probe_action["phase"] == "step_ready"
            dag = probe_action["dag"]
            assert len(dag.nodes) >= 3 # Full multi-step tailored DAG generated!
            assert probe_action["step"] is not None
            assert len(probe_action["step"].explanation_markdown) > 10

            # 3. Submit Verification for Step 1
            res1 = await step_executor.evaluate_step_answer(
                session=session,
                deep_session=deep_session,
                submission=DeepStepAnswerSubmission(
                    session_id=deep_session.id,
                    step_sequence=1,
                    selected_option_ids=["a"],
                ),
            )
            await tutor_state_machine.advance_to_next_node(session, deep_session.id)

            # 5. Seamlessly Transition to Step 2 WITHOUT ending the session!
            action_step2 = await tutor_state_machine.get_next_action(session=session, deep_session_id=deep_session.id)
            assert action_step2["phase"] == "step_ready"
            assert action_step2["step"] is not None
            assert len(action_step2["step"].concept_title) > 0

            # 6. Submit Verification for Step 2
            await step_executor.evaluate_step_answer(
                session=session,
                deep_session=deep_session,
                submission=DeepStepAnswerSubmission(
                    session_id=deep_session.id,
                    step_sequence=2,
                    selected_option_ids=["a"],
                ),
            )
            await tutor_state_machine.advance_to_next_node(session, deep_session.id)

            # 7. Transition to Step 3
            action_step3 = await tutor_state_machine.get_next_action(session=session, deep_session_id=deep_session.id)
            assert action_step3["phase"] == "step_ready"
            assert action_step3["step"] is not None
            assert len(action_step3["step"].concept_title) > 0

            # 8. Fast-forward to the terminal step to test full arc completion
            for node in dag.nodes:
                cid = str(node.id)
                res = await session.execute(
                    select(UserMasteryState).where(
                        and_(
                            UserMasteryState.user_id == user.id,
                            UserMasteryState.concept_id == cid,
                        )
                    )
                )
                ms = res.scalar_one_or_none()
                if not ms:
                    ms = UserMasteryState(
                        user_id=user.id,
                        concept_id=cid,
                        mastery_prob=0.95,
                        uncertainty=0.1,
                    )
                    session.add(ms)
                else:
                    ms.mastery_prob = 0.95
                    ms.uncertainty = 0.1
            await session.commit()

            deep_session.current_concept_index = len(dag.nodes) - 1
            await session.commit()

            action_terminal = await tutor_state_machine.get_next_action(session=session, deep_session_id=deep_session.id)
            assert action_terminal["phase"] == "step_ready"

            res_term = await step_executor.evaluate_step_answer(
                session=session,
                deep_session=deep_session,
                submission=DeepStepAnswerSubmission(
                    session_id=deep_session.id,
                    step_sequence=len(dag.nodes),
                    selected_option_ids=["a"],
                ),
            )
            assert res_term.is_correct is True
            await tutor_state_machine.advance_to_next_node(session, deep_session.id)

            # 9. Arc is now complete!
            action_final = await tutor_state_machine.get_next_action(session=session, deep_session_id=deep_session.id)
            assert action_final["phase"] == "completed"

    await engine.dispose()
