from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import List, Optional
from datetime import datetime
from app.core.database import get_db_session
from app.models.ontology import Domain, Track, Concept
from app.models.mastery import UserMasteryState, User
from app.schemas.mastery import UserMasteryOverview, ConceptMasterySummary

router = APIRouter(prefix="/tracks", tags=["Tracks & Ontology"])


from pydantic import BaseModel
from app.services.graph.dynamic_curriculum import curriculum_generator
from app.services.moderation import moderation_service
from app.models.ontology import Domain, Track, Concept, TrackFolder
from sqlalchemy import func, update, or_

class CreateFolderRequest(BaseModel):
    name: str
    description: Optional[str] = None
    color: Optional[str] = "#6366f1"
    icon: Optional[str] = "folder"
    is_pinned: Optional[bool] = False

class UpdateFolderRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    is_pinned: Optional[bool] = None
    order_index: Optional[float] = None

class UpdateTrackOrganizationRequest(BaseModel):
    folder_id: Optional[str] = None
    is_pinned: Optional[bool] = None

class GenerateTrackRequest(BaseModel):
    user_id: str
    topic_query: str
    depth_level: Optional[str] = "high" # 'low' (~6), 'medium' (15-25), 'high' (maximum/expert)
    user_wishes: Optional[str] = None
    folder_id: Optional[str] = None


class ExpandTrackRequest(BaseModel):
    user_id: str
    depth_level: str = "high" # 'low', 'medium', 'high'
    user_notes: Optional[str] = None


@router.get("/folders")
async def list_folders(db: AsyncSession = Depends(get_db_session)):
    """
    Lists all course folders with their track count, ordered by pinned status and order_index.
    """
    folders_res = await db.execute(
        select(TrackFolder).order_by(TrackFolder.is_pinned.desc(), TrackFolder.order_index.asc(), TrackFolder.created_at.asc())
    )
    folders = folders_res.scalars().all()

    counts_res = await db.execute(
        select(Track.folder_id, func.count(Track.id))
        .where(and_(Track.folder_id.isnot(None), Track.is_active == True))
        .group_by(Track.folder_id)
    )
    counts_map = {row[0]: row[1] for row in counts_res.all()}

    return [
        {
            "id": f.id,
            "name": f.name,
            "description": f.description,
            "color": f.color or "#6366f1",
            "icon": f.icon or "folder",
            "is_pinned": bool(f.is_pinned),
            "order_index": f.order_index or 0.0,
            "track_count": counts_map.get(f.id, 0),
            "created_at": f.created_at.isoformat() if f.created_at else None,
        }
        for f in folders
    ]


@router.post("/folders")
async def create_folder(
    request: CreateFolderRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Creates a new course folder.
    """
    folder = TrackFolder(
        name=request.name.strip(),
        description=request.description.strip() if request.description else None,
        color=request.color or "#6366f1",
        icon=request.icon or "folder",
        is_pinned=bool(request.is_pinned),
    )
    db.add(folder)
    await db.commit()
    await db.refresh(folder)
    return {
        "id": folder.id,
        "name": folder.name,
        "description": folder.description,
        "color": folder.color,
        "icon": folder.icon,
        "is_pinned": folder.is_pinned,
        "order_index": folder.order_index,
        "track_count": 0,
        "created_at": folder.created_at.isoformat() if folder.created_at else None,
    }


@router.patch("/folders/{folder_id}")
async def update_folder(
    folder_id: str,
    request: UpdateFolderRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Updates folder name, color, icon, is_pinned status, or order_index.
    """
    folder_res = await db.execute(select(TrackFolder).where(TrackFolder.id == folder_id))
    folder = folder_res.scalars().first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    if request.name is not None:
        folder.name = request.name.strip()
    if request.description is not None:
        folder.description = request.description.strip() if request.description else None
    if request.color is not None:
        folder.color = request.color
    if request.icon is not None:
        folder.icon = request.icon
    if request.is_pinned is not None:
        folder.is_pinned = request.is_pinned
    if request.order_index is not None:
        folder.order_index = request.order_index

    await db.commit()
    await db.refresh(folder)

    counts_res = await db.execute(
        select(func.count(Track.id)).where(and_(Track.folder_id == folder.id, Track.is_active == True))
    )
    count = counts_res.scalar() or 0

    return {
        "id": folder.id,
        "name": folder.name,
        "description": folder.description,
        "color": folder.color,
        "icon": folder.icon,
        "is_pinned": folder.is_pinned,
        "order_index": folder.order_index,
        "track_count": count,
        "created_at": folder.created_at.isoformat() if folder.created_at else None,
    }


@router.delete("/folders/{folder_id}")
async def delete_folder(
    folder_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Deletes a folder safely. Tracks inside are unlinked (folder_id -> None), NOT deleted.
    """
    folder_res = await db.execute(select(TrackFolder).where(TrackFolder.id == folder_id))
    folder = folder_res.scalars().first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    await db.execute(
        update(Track).where(Track.folder_id == folder_id).values(folder_id=None)
    )
    await db.delete(folder)
    await db.commit()
    return {"status": "deleted", "folder_id": folder_id}


@router.patch("/{track_id}/organization")
async def update_track_organization(
    track_id: str,
    request: UpdateTrackOrganizationRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Updates a track's folder assignment and/or is_pinned status.
    """
    track_res = await db.execute(
        select(Track).where(or_(Track.id == track_id, Track.slug == track_id))
    )
    track = track_res.scalars().first()
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")

    if request.folder_id:
        f_res = await db.execute(select(TrackFolder).where(TrackFolder.id == request.folder_id))
        if not f_res.scalars().first():
            raise HTTPException(status_code=400, detail="Target folder does not exist")

    req_dict = request.model_dump(exclude_unset=True)
    if "folder_id" in req_dict:
        track.folder_id = request.folder_id
    if "is_pinned" in req_dict:
        track.is_pinned = request.is_pinned

    await db.commit()
    await db.refresh(track)
    return {
        "track_id": track.id,
        "slug": track.slug,
        "title": track.title,
        "folder_id": track.folder_id,
        "is_pinned": bool(track.is_pinned),
    }


@router.post("/generate")
async def generate_custom_track(
    request: GenerateTrackRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    On-demand AI Curriculum Generation: Creates a complete knowledge graph track
    for ANY user topic (Physics, Philosophy, Coding, History, etc.)
    """
    # 0. Safety & Content Moderation Audit
    await moderation_service.validate_course_request_or_raise(
        topic_query=request.topic_query,
        user_wishes=request.user_wishes,
    )

    track = await curriculum_generator.generate_curriculum(
        session=db,
        user_id=request.user_id,
        topic_query=request.topic_query,
        depth_level=request.depth_level or "high",
        user_wishes=request.user_wishes,
        folder_id=request.folder_id,
    )
    # Fetch concepts for response
    concepts_res = await db.execute(select(Concept).where(Concept.track_id == track.id))
    raw_concepts = list(concepts_res.scalars().all())
    from app.models.ontology import ConceptDependency
    from app.services.graph.knowledge_graph import deterministic_topological_sort
    deps_res = await db.execute(
        select(ConceptDependency).where(
            ConceptDependency.source_concept_id.in_([c.id for c in raw_concepts])
        )
    )
    deps = [(d.source_concept_id, d.target_concept_id) for d in deps_res.scalars().all()]
    concepts = deterministic_topological_sort(raw_concepts, deps)

    return {
        "track_id": track.id,
        "slug": track.slug,
        "title": track.title,
        "description": track.description,
        "user_wishes": track.user_wishes,
        "depth_level": track.depth_level or "high",
        "folder_id": track.folder_id,
        "is_pinned": bool(track.is_pinned),
        "total_concepts": len(concepts),
        "concepts": [{"id": c.id, "slug": c.slug, "code": c.code, "title": c.title, "summary": c.summary} for c in concepts],
    }


@router.post("/{track_id}/expand")
async def expand_custom_track(
    track_id: str,
    request: ExpandTrackRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Expands an existing course (track) volume with 3 detail levels (low, medium, high),
    preserving previously mastered concepts and updating knowledge graph and active learning session.
    """
    from app.services.tutor.plan_phase import plan_manager
    from sqlalchemy import or_

    track_res = await db.execute(
        select(Track).where(or_(Track.id == track_id, Track.slug == track_id))
    )
    track = track_res.scalars().first()
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")

    if request.user_notes and request.user_notes.strip():
        await moderation_service.validate_or_raise(
            text=request.user_notes,
            context={"intent": "track_expansion_notes", "topic": track.title},
        )

    dag_plan = await plan_manager.expand_track_curriculum(
        session=db,
        user_id=request.user_id,
        track_id=track.id,
        target_depth_level=request.depth_level or "high",
        user_notes=request.user_notes or "",
    )

    concepts_res = await db.execute(select(Concept).where(Concept.track_id == track.id))
    raw_concepts = list(concepts_res.scalars().all())
    from app.models.ontology import ConceptDependency
    from app.services.graph.knowledge_graph import deterministic_topological_sort
    deps_res = await db.execute(
        select(ConceptDependency).where(
            ConceptDependency.source_concept_id.in_([c.id for c in raw_concepts])
        )
    )
    deps = [(d.source_concept_id, d.target_concept_id) for d in deps_res.scalars().all()]
    concepts = deterministic_topological_sort(raw_concepts, deps)

    return {
        "track_id": track.id,
        "slug": track.slug,
        "title": track.title,
        "description": track.description,
        "depth_level": track.depth_level or request.depth_level or "high",
        "total_concepts": len(concepts),
        "concepts": [{"id": c.id, "slug": c.slug, "code": c.code, "title": c.title, "summary": c.summary} for c in concepts],
        "dag": dag_plan.model_dump() if hasattr(dag_plan, "model_dump") else dag_plan,
        "message": "Course volume successfully expanded",
    }


from typing import List, Optional
from fastapi import Query


@router.get("")
@router.get("/")
@router.get("/list")
async def list_available_tracks(db: AsyncSession = Depends(get_db_session)):
    """
    Lists all available subject tracks and concepts, prioritizing pinned tracks.
    """
    res = await db.execute(
        select(Track).where(Track.is_active == True).order_by(Track.is_pinned.desc(), Track.created_at.desc())
    )
    tracks = res.scalars().all()
    from app.models.ontology import ConceptDependency
    from app.services.graph.knowledge_graph import deterministic_topological_sort
    out = []
    for t in tracks:
        concepts_res = await db.execute(select(Concept).where(Concept.track_id == t.id))
        raw_concepts = list(concepts_res.scalars().all())
        deps_res = await db.execute(
            select(ConceptDependency).where(
                ConceptDependency.source_concept_id.in_([c.id for c in raw_concepts])
            )
        )
        deps = [(d.source_concept_id, d.target_concept_id) for d in deps_res.scalars().all()]
        concepts = deterministic_topological_sort(raw_concepts, deps)
        out.append({
            "track_id": t.id,
            "slug": t.slug,
            "title": t.title,
            "description": t.description,
            "user_wishes": t.user_wishes,
            "depth_level": t.depth_level or "high",
            "folder_id": t.folder_id,
            "is_pinned": bool(t.is_pinned),
            "total_concepts": len(concepts),
            "concepts": [{"id": c.id, "slug": c.slug, "code": c.code, "title": c.title, "summary": c.summary} for c in concepts],
        })
    return out


@router.get("/{track_id}/mastery", response_model=UserMasteryOverview)
@router.get("/{track_id}/mastery/{user_id}", response_model=UserMasteryOverview)
async def get_user_track_mastery(
    track_id: str,
    user_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Returns full visual breakdown of student mastery across all concepts in a track.
    """
    effective_user_id = user_id
    if not effective_user_id:
        user_res = await db.execute(select(User.id).limit(1))
        effective_user_id = user_res.scalars().first() or "demo_user"
    from sqlalchemy import or_
    from app.core.slug import generate_slug

    track_res = await db.execute(
        select(Track).where(or_(Track.id == track_id, Track.slug == track_id))
    )
    track = track_res.scalars().first()
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")

    from app.models.ontology import ConceptDependency
    from app.services.graph.knowledge_graph import deterministic_topological_sort

    concepts_res = await db.execute(select(Concept).where(Concept.track_id == track.id))
    raw_concepts = list(concepts_res.scalars().all())
    concept_map = {c.id: c for c in raw_concepts}

    # Topologically sort concepts deterministically by track dependencies and natural pedagogical order
    deps_res = await db.execute(
        select(ConceptDependency).where(
            and_(
                ConceptDependency.source_concept_id.in_(list(concept_map.keys())),
                ConceptDependency.target_concept_id.in_(list(concept_map.keys())),
            )
        )
    )
    deps = [(d.source_concept_id, d.target_concept_id) for d in deps_res.scalars().all()]
    concepts = deterministic_topological_sort(raw_concepts, deps)

    mastery_res = await db.execute(
        select(UserMasteryState).where(
            and_(
                UserMasteryState.user_id == effective_user_id,
                UserMasteryState.concept_id.in_([c.id for c in concepts]),
            )
        )
    )
    mastery_map = {m.concept_id: m for m in mastery_res.scalars().all()}

    now = datetime.utcnow()
    summaries: List[ConceptMasterySummary] = []
    mastered_count = 0
    in_progress_count = 0

    for c in concepts:
        m = mastery_map.get(c.id)
        m_prob = m.mastery_prob if m else 0.0
        unc = m.uncertainty if m else 1.0
        retriev = m.retrievability if m else 0.0
        stab = m.stability if m else 0.0
        is_mastered = (m_prob >= 0.85) or (m_prob >= 0.80 and unc <= 0.40)
        is_due = (m.next_review_due <= now) if (m and m.next_review_due) else False

        if is_mastered:
            mastered_count += 1
        elif m_prob > 0.1:
            in_progress_count += 1

        summaries.append(
            ConceptMasterySummary(
                concept_id=c.id,
                concept_code=c.code,
                title=c.title,
                slug=getattr(c, 'slug', None) or generate_slug(c.title),
                mastery_prob=m_prob,
                uncertainty=unc,
                retrievability=retriev,
                stability=stab,
                is_mastered=is_mastered,
                is_due_for_review=is_due,
            )
        )

    track_desc = track.description
    if not track_desc or track_desc.strip() == "":
        is_russian = any('\u0400' <= char <= '\u04FF' for char in (track.title or ""))
        if is_russian:
            track_desc = f"Практический курс по «{track.title}»: системное освоение от базовых понятий до практического мастерства через адаптивную карту знаний."
        else:
            track_desc = f"Comprehensive personalized course on {track.title}: mastering all foundational and advanced principles step-by-step."

    return UserMasteryOverview(
        user_id=effective_user_id,
        track_id=track.id,
        track_slug=track.slug,
        track_title=track.title,
        track_description=track_desc,
        track_user_wishes=track.user_wishes,
        track_depth_level=track.depth_level or "high",
        track_folder_id=track.folder_id,
        track_is_pinned=bool(track.is_pinned),
        total_concepts=len(concepts),
        mastered_concepts=mastered_count,
        in_progress_concepts=in_progress_count,
        concepts=summaries,
    )


from sqlalchemy import delete, or_
from app.models.ontology import ConceptDependency, AssessmentItem
from app.models.session import DeepLearningSession, DeepSessionStep
from app.models.mastery import UserTrackEnrollment

@router.delete("/{track_id}")
async def delete_track(
    track_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Deletes a subject track and cascades deletion across its concepts, dependencies,
    assessment items, and associated learning sessions.
    """
    track_res = await db.execute(
        select(Track).where(or_(Track.id == track_id, Track.slug == track_id))
    )
    track = track_res.scalars().first()
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    real_track_id = track.id

    # 1. Fetch all concept IDs belonging to this track
    concepts_res = await db.execute(select(Concept).where(Concept.track_id == real_track_id))
    concepts = concepts_res.scalars().all()
    concept_ids = [c.id for c in concepts]

    if concept_ids:
        # 2. Delete Dependencies
        await db.execute(
            delete(ConceptDependency).where(
                or_(
                    ConceptDependency.source_concept_id.in_(concept_ids),
                    ConceptDependency.target_concept_id.in_(concept_ids),
                )
            )
        )

        # 3. Delete Assessment Items
        await db.execute(
            delete(AssessmentItem).where(AssessmentItem.concept_id.in_(concept_ids))
        )

        # 4. Delete Mastery States
        await db.execute(
            delete(UserMasteryState).where(UserMasteryState.concept_id.in_(concept_ids))
        )

        # 5. Delete Deep Session Steps and Sessions
        sessions_res = await db.execute(
            select(DeepLearningSession).where(
                or_(
                    DeepLearningSession.target_concept_id.in_(concept_ids),
                    DeepLearningSession.current_concept_id.in_(concept_ids),
                )
            )
        )
        sessions = sessions_res.scalars().all()
        session_ids = [s.id for s in sessions]
        if session_ids:
            await db.execute(
                delete(DeepSessionStep).where(DeepSessionStep.session_id.in_(session_ids))
            )
            await db.execute(
                delete(DeepLearningSession).where(DeepLearningSession.id.in_(session_ids))
            )

        # 6. Delete Concepts
        await db.execute(
            delete(Concept).where(Concept.track_id == track_id)
        )

    # 7. Delete User Enrollments & Track
    await db.execute(
        delete(UserTrackEnrollment).where(UserTrackEnrollment.track_id == track_id)
    )
    await db.delete(track)
    await db.commit()

    return {"status": "deleted", "track_id": track_id}

