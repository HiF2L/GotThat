import uuid
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.ontology import Domain, Track, Concept
from app.models.mastery import User, UserTrackEnrollment

logger = logging.getLogger(__name__)


class DynamicCurriculumGenerator:
    """
    On-demand AI Track Initializer:
    Registers a new subject track cleanly. The full individual 25-35 concept course DAG
    is dynamically synthesized by PlanPhaseManager AFTER the learner completes the diagnostic assessment.
    """

    async def generate_curriculum(
        self,
        session: AsyncSession,
        user_id: str,
        topic_query: str,
        model: Optional[str] = None,
        depth_level: str = "high",
        user_wishes: Optional[str] = None,
        folder_id: Optional[str] = None,
    ) -> Track:
        """
        Creates and persists a clean track in < 0.1 seconds without premature fake concept stubs.
        """
        logger.info(f"Registering on-demand track for topic: {topic_query} (depth: {depth_level}, wishes: {user_wishes})")
        is_russian = any('\u0400' <= char <= '\u04FF' for char in (topic_query or ""))

        # 1. Resolve or Create Domain
        domain_res = await session.execute(select(Domain).where(Domain.slug == "general_studies"))
        domain = domain_res.scalars().first()
        if not domain:
            domain = Domain(
                id=str(uuid.uuid4()),
                slug="general_studies",
                title="Общие дисциплины" if is_russian else "General Studies",
                description="Academic and engineering tracks",
            )
            session.add(domain)
            await session.flush()

        # 2. Create Track
        from app.core.slug import generate_slug
        base_slug = generate_slug(topic_query)
        # Generate clean human-readable slug (e.g. 'mozg' or 'mozg-2' if duplicate, never random hex)
        existing_track_res = await session.execute(select(Track).where(Track.slug == base_slug))
        if existing_track_res.scalars().first():
            counter = 2
            track_slug = f"{base_slug}-{counter}"
            while True:
                chk = await session.execute(select(Track).where(Track.slug == f"{base_slug}-{counter}"))
                if not chk.scalars().first():
                    track_slug = f"{base_slug}-{counter}"
                    break
                counter += 1
        else:
            track_slug = base_slug

        track_desc = (
            f"Индивидуальный курс по «{topic_query}»: пошаговое изучение от фундаментальных понятий до глубокого понимания через адаптивную карту знаний."
            if is_russian
            else f"Personalized curriculum for {topic_query}: mastering all core and advanced concepts step-by-step."
        )
        track = Track(
            id=str(uuid.uuid4()),
            domain_id=domain.id,
            slug=track_slug,
            title=topic_query,
            description=track_desc,
            user_wishes=user_wishes.strip() if user_wishes and user_wishes.strip() else None,
            depth_level=depth_level or "high",
            folder_id=folder_id,
            icon_url="https://cdn-icons-png.flaticon.com/512/3749/3749784.png",
        )
        session.add(track)
        await session.flush()

        # 3. Create Root Goal Concept (Anchor for track before diagnostic profiling)
        root_concept = Concept(
            id=str(uuid.uuid4()),
            track_id=track.id,
            slug=base_slug,
            code=f"GOAL_{uuid.uuid4().hex[:4]}",
            title=topic_query,
            summary=f"Индивидуальный курс от основ до мастерства: {topic_query}" if is_russian else f"Zero-to-mastery personalized course for: {topic_query}",
            bloom_level="evaluate",
        )
        session.add(root_concept)
        await session.flush()

        # 4. Enroll User into New Track
        user_res = await session.execute(select(User).where(User.id == user_id))
        user = user_res.scalars().first()
        if not user:
            user_res = await session.execute(select(User).limit(1))
            user = user_res.scalars().first()

        if user:
            enrollment = UserTrackEnrollment(
                user_id=user.id,
                track_id=track.id,
                is_active_in_feed=True,
            )
            session.add(enrollment)

        await session.commit()
        await session.refresh(track)
        return track


curriculum_generator = DynamicCurriculumGenerator()
