import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.database import Base
from app.models.ontology import Domain, Track, Concept, TrackFolder
from app.models.mastery import User
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.database import get_db_session


@pytest.mark.asyncio
async def test_track_folders_and_pinning():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    # Seed User and Domain
    async with session_factory() as session:
        user = User(username="folder_user", email="folder@user.local")
        session.add(user)
        domain = Domain(slug="general_studies", title="General Studies")
        session.add(domain)
        await session.flush()

        t1 = Track(domain_id=domain.id, slug="calc-101", title="Calculus 101")
        session.add(t1)
        await session.commit()
        track_id = t1.id

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create Folder
        res = await client.post("/api/v1/tracks/folders", json={
            "name": "STEM & Math",
            "description": "Mathematics and exact sciences",
            "color": "#6366f1",
            "icon": "calculator",
            "is_pinned": False,
        })
        assert res.status_code == 200
        folder_data = res.json()
        folder_id = folder_data["id"]
        assert folder_data["name"] == "STEM & Math"
        assert folder_data["color"] == "#6366f1"
        assert folder_data["is_pinned"] is False

        # 2. Create Second Folder that is pinned
        res2 = await client.post("/api/v1/tracks/folders", json={
            "name": "Top Priority AI",
            "color": "#10b981",
            "is_pinned": True,
        })
        assert res2.status_code == 200
        f2_id = res2.json()["id"]

        # 3. List Folders - pinned should be first
        res_list = await client.get("/api/v1/tracks/folders")
        assert res_list.status_code == 200
        folders = res_list.json()
        assert len(folders) == 2
        assert folders[0]["id"] == f2_id
        assert folders[0]["is_pinned"] is True

        # 4. Assign track to folder and pin track
        res_org = await client.patch(f"/api/v1/tracks/{track_id}/organization", json={
            "folder_id": folder_id,
            "is_pinned": True,
        })
        assert res_org.status_code == 200
        org_data = res_org.json()
        assert org_data["folder_id"] == folder_id
        assert org_data["is_pinned"] is True

        # Check folder track count in folder list
        res_list2 = await client.get("/api/v1/tracks/folders")
        stem_folder = next(f for f in res_list2.json() if f["id"] == folder_id)
        assert stem_folder["track_count"] == 1

        # 5. List Tracks - check is_pinned and folder_id present
        tracks_res = await client.get("/api/v1/tracks/list")
        assert tracks_res.status_code == 200
        track_entry = next(t for t in tracks_res.json() if t["track_id"] == track_id)
        assert track_entry["folder_id"] == folder_id
        assert track_entry["is_pinned"] is True

        # 6. Update folder (rename and pin)
        update_folder_res = await client.patch(f"/api/v1/tracks/folders/{folder_id}", json={
            "name": "Advanced Mathematics",
            "is_pinned": True,
        })
        assert update_folder_res.status_code == 200
        assert update_folder_res.json()["name"] == "Advanced Mathematics"
        assert update_folder_res.json()["is_pinned"] is True

        # 7. Delete folder - track must NOT be deleted, but unlinked
        del_f_res = await client.delete(f"/api/v1/tracks/folders/{folder_id}")
        assert del_f_res.status_code == 200

        # Verify track still exists in DB with folder_id == None
        tracks_res_after = await client.get("/api/v1/tracks/list")
        track_after = next(t for t in tracks_res_after.json() if t["track_id"] == track_id)
        assert track_after is not None
        assert track_after["folder_id"] is None
        assert track_after["is_pinned"] is True

    app.dependency_overrides.clear()
    await engine.dispose()
