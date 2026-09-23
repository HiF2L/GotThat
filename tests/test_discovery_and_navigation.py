import pytest
from app.services.ai.client import ai_clients
from app.services.tutor.tutor_state_machine import tutor_state_machine, is_concept_mastered
from app.models.mastery import UserMasteryState
from app.schemas.feed import DiscoveryLessonTeaser


def test_normalize_model_name_proxyapi():
    """Verify that ProxyAPI model names with and without vendor prefixes are properly normalized."""
    assert ai_clients.normalize_model_name("google/gemini-2.5-flash") == "google/gemini-2.5-flash"
    assert ai_clients.normalize_model_name("gemini-2.5-flash") == "google/gemini-2.5-flash"
    assert ai_clients.normalize_model_name("gemini-3-flash-preview") == "google/gemini-3-flash-preview"
    assert ai_clients.normalize_model_name("openai/gpt-4.1-mini") == "openai/gpt-4.1-mini"
    assert ai_clients.normalize_model_name("gpt-4.1-mini") == "openai/gpt-4.1-mini"
    assert ai_clients.normalize_model_name("deepseek/deepseek-chat") == "deepseek/deepseek-chat"
    assert ai_clients.normalize_model_name("deepseek-chat") == "deepseek/deepseek-chat"
    assert ai_clients.normalize_model_name("anthropic/claude-sonnet-4-5") == "anthropic/claude-sonnet-4-5"
    assert ai_clients.normalize_model_name("claude-sonnet") == "anthropic/claude-sonnet-4-5"


@pytest.mark.asyncio
async def test_cyclic_gap_discovery_reconcile():
    """
    Test Cyclic Gap Discovery in reconcile_dag_with_mastery:
    If a student jumps forward or reaches the end with unmastered concepts earlier in the DAG,
    the state machine must wrap around and pick the first unmastered concept from the beginning.
    """
    class FakeSession:
        async def execute(self, stmt):
            class FakeResult:
                def scalars(self):
                    class FakeScalars:
                        def all(self):
                            return []
                        def first(self):
                            return None
                    return FakeScalars()
                def all(self):
                    return []
            return FakeResult()

    fake_session = FakeSession()

    nodes = [
        {"id": "c0", "code": "C0", "title": "Concept 0 (Skipped)"},
        {"id": "c1", "code": "C1", "title": "Concept 1 (Mastered)"},
        {"id": "c2", "code": "C2", "title": "Concept 2 (Current, Mastered)"},
    ]
    edges = [
        {"source": "c0", "target": "c1"},
        {"source": "c1", "target": "c2"},
    ]
    dag_data = {
        "nodes": nodes,
        "edges": edges,
        "total_nodes": 3,
        "completed_nodes": 0,
        "mermaid_code": "",
    }

    # Scenario 1: Normal forward advance (from c0 to c1 when c0 is mastered, c1 unmastered)
    # Mocking mastery in DB: c0 is mastered, c1 and c2 are not
    # In reconcile_dag_with_mastery, completed_indices comes from DB. With empty DB, all are unmastered.
    # Advancing from index 0 should pick index 1.
    res_dag, active_idx, active_cid, is_completed = await tutor_state_machine.reconcile_dag_with_mastery(
        session=fake_session,
        user_id="test_user",
        dag_data=dag_data,
        current_index=0,
        is_advancing=True,
    )
    assert active_idx == 1
    assert active_cid == "c1"
    assert not is_completed

    # Scenario 2: End of course reached at index 2, but index 0 was skipped (unmastered)
    # Forward scan from index 2 has nothing, so wrap-around scan must select index 0!
    res_dag, active_idx, active_cid, is_completed = await tutor_state_machine.reconcile_dag_with_mastery(
        session=fake_session,
        user_id="test_user",
        dag_data=dag_data,
        current_index=2,
        is_advancing=True,
    )
    assert active_idx == 0, f"Expected wrap-around to index 0, got {active_idx}"
    assert active_cid == "c0"
    assert not is_completed


@pytest.mark.asyncio
async def test_discovery_feed_endpoint():
    """Verify that GET /api/v1/feed/discovery returns 200 and valid schema."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    from app.core.database import init_db

    await init_db()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/v1/feed/discovery?limit=5")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        if len(data) > 0:
            teaser = data[0]
            assert "concept_id" in teaser
            assert "concept_title" in teaser
            assert "track_title" in teaser
            assert "teaser_text" in teaser
            assert "is_mastered" in teaser
            assert "score" in teaser
            assert "upvotes" in teaser
            assert "downvotes" in teaser


@pytest.mark.asyncio
async def test_concept_vote_endpoint():
    """Verify upvote, downvote, and clear vote functionality on /api/v1/feed/vote."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    from app.core.database import init_db

    await init_db()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Fetch a teaser to get a valid concept_id
        feed_res = await ac.get("/api/v1/feed/discovery?limit=1")
        assert feed_res.status_code == 200
        teasers = feed_res.json()
        if not teasers:
            pytest.skip("No concepts available to test voting")

        concept_id = teasers[0]["concept_id"]
        test_user_id = "test-voter-42"

        # 2. Upvote
        up_res = await ac.post("/api/v1/feed/vote", json={
            "user_id": test_user_id,
            "concept_id": concept_id,
            "vote_type": "upvote"
        })
        assert up_res.status_code == 200
        up_data = up_res.json()
        assert up_data["concept_id"] == concept_id
        assert up_data["user_vote"] == "upvote"
        assert up_data["upvotes"] >= 1

        # 3. Switch to Downvote
        down_res = await ac.post("/api/v1/feed/vote", json={
            "user_id": test_user_id,
            "concept_id": concept_id,
            "vote_type": "downvote"
        })
        assert down_res.status_code == 200
        down_data = down_res.json()
        assert down_data["user_vote"] == "downvote"
        assert down_data["downvotes"] >= 1

        # 4. Clear vote
        clear_res = await ac.post("/api/v1/feed/vote", json={
            "user_id": test_user_id,
            "concept_id": concept_id,
            "vote_type": "clear"
        })
        assert clear_res.status_code == 200
        clear_data = clear_res.json()
        assert clear_data["user_vote"] is None


def test_sanitize_markdown_text_latex_escapes():
    """Verify that sanitize_markdown_text and teaser extraction cleanly unpack JSON containing LaTeX formulas."""
    from app.services.ai.client import sanitize_markdown_text
    from app.services.feed.feed_orchestrator import feed_orchestrator

    # Case 1: JSON with LaTeX formulas (invalid JSON escapes like \cdot, \sigma, \frac)
    raw_json_with_latex = (
        '{\n'
        '  "explanation_markdown": "### Кризис Внимания: Почему Просто Сложение не работает?\\n\\n'
        'Формула: $$Q = x \\cdot W^Q$$\\n\\nПредставьте, что вы находитесь в гигантской библиотеке.",\n'
        '  "verification_question": {"prompt": "Тест"}\n'
        '}'
    )
    sanitized = sanitize_markdown_text(raw_json_with_latex)
    assert not sanitized.startswith("{")
    assert '"explanation_markdown"' not in sanitized
    assert "### Кризис Внимания" in sanitized
    assert "$$Q = x \\cdot W^Q$$" in sanitized

    # Case 2: Teaser extraction
    teaser = feed_orchestrator._extract_teaser_text(
        explanation_markdown=raw_json_with_latex,
        summary="Краткое описание",
        title="Внимание в Трансформерах",
    )
    assert not teaser.startswith("{")
    assert '"explanation_markdown"' not in teaser
    assert "Кризис Внимания" in teaser


