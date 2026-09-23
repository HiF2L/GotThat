import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.main import app
from app.core.database import Base, get_db_session
from app.services.ai.cost_tracker import cost_tracker
from app.models.usage import AIUsageLog


@pytest_asyncio.fixture
async def client_and_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, session_factory

    app.dependency_overrides.clear()
    await engine.dispose()


def test_calculate_cost_rub():
    # 1. Standard model: gpt-4.1-mini (15 in / 60 out per 1M)
    # 1,000 in, 1,000 out => 0.015 + 0.060 = 0.075 RUB
    cost = cost_tracker.calculate_cost_rub("openai/gpt-4.1-mini", 1000, 1000, 0)
    assert cost == pytest.approx(0.075, rel=1e-3)

    # 100,000 in, 50,000 out => 1.5 + 3.0 = 4.5 RUB
    cost = cost_tracker.calculate_cost_rub("openai/gpt-4.1-mini", 100_000, 50_000, 0)
    assert cost == pytest.approx(4.5, rel=1e-3)

    # 2. Reasoning model: deepseek-v4-pro (190 in / 375 out per 1M)
    # 10,000 in, 10,000 out (including 5,000 reasoning) => 1.9 + 1.875 + 1.875 = 5.65 RUB
    cost = cost_tracker.calculate_cost_rub("deepseek/deepseek-v4-pro", 10_000, 10_000, 5_000)
    assert cost == pytest.approx(5.65, rel=1e-3)


@pytest.mark.asyncio
async def test_costs_endpoint_and_summary(client_and_db):
    client, session_factory = client_and_db

    # Manually add an entry using session_factory
    async with session_factory() as s:
        entry = AIUsageLog(
            task_type="step_teaching",
            model="openai/gpt-4.1-mini",
            prompt_tokens=2500,
            completion_tokens=1200,
            reasoning_tokens=0,
            total_tokens=3700,
            cost_rub=0.1095,
            latency_ms=1800,
            status="success",
        )
        s.add(entry)
        await s.commit()

        # Query cost summary directly
        summary = await cost_tracker.get_cost_summary(s)
        assert summary["today_spent_rub"] >= 0.1095
        assert summary["today_tokens"] >= 3700
        assert "step_teaching" in summary["breakdown_by_task"]
        assert "openai/gpt-4.1-mini" in summary["breakdown_by_model"]
        assert len(summary["recent_calls"]) >= 1

    # Call API GET /api/v1/deep/costs
    res = await client.get("/api/v1/deep/costs")
    assert res.status_code == 200
    data = res.json()
    assert "today_spent_rub" in data
    assert "breakdown_by_task" in data
    assert "recent_calls" in data
