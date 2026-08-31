import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.database import Base
from app.services.graph.seed_data import seed_initial_knowledge_graph
from app.services.graph.knowledge_graph import knowledge_graph_service
from app.models.ontology import Concept, Track
from sqlalchemy import select


@pytest_asyncio.fixture
async def async_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async_session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        await seed_initial_knowledge_graph(session)
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_prerequisite_subgraph_extraction(async_db: AsyncSession):
    # Find Generalized Stokes Concept
    res = await async_db.execute(select(Concept).where(Concept.code == "MATH.DF.GEN_STOKES"))
    stokes_concept = res.scalars().first()
    assert stokes_concept is not None

    subgraph = await knowledge_graph_service.get_prerequisite_subgraph(
        session=async_db,
        target_concept_id=stokes_concept.id,
    )

    # Subgraph must contain all prerequisite concepts
    assert len(subgraph.nodes) >= 6
    assert stokes_concept.id in subgraph.nodes


@pytest.mark.asyncio
async def test_curriculum_plan_mermaid_generation(async_db: AsyncSession):
    res = await async_db.execute(select(Concept).where(Concept.code == "MATH.DF.GEN_STOKES"))
    stokes_concept = res.scalars().first()

    dag_plan = await knowledge_graph_service.plan_curriculum_dag(
        session=async_db,
        user_id="test_user_123",
        target_concept_id=stokes_concept.id,
    )

    assert dag_plan.total_nodes >= 6
    assert "graph TD" in dag_plan.mermaid_code
    assert "MATH.DF.GEN_STOKES" in dag_plan.mermaid_code
    # First pending concept should be marked active
    assert any(n.status == "active" for n in dag_plan.nodes)
