import random
import uuid
from typing import List, Optional
from datetime import datetime
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.ontology import Concept, AssessmentItem, Track, AssessmentType
from app.models.mastery import UserMasteryState, AssessmentAttempt, VoiceReasoningLog, UserTrackEnrollment, User
from app.schemas.feed import (
    FeedCardResponse,
    QuizOption,
    QuizAnswerSubmission,
    QuizAnswerResult,
    VoiceReasoningAnalysis,
)
from app.services.cognitive.bkt_engine import bkt_engine
from app.services.cognitive.fsrs_scheduler import fsrs_scheduler
from app.services.ai.client import ai_clients
from app.config import settings


class FeedOrchestrator:
    """
    Manages the Duolingo/TikTok-style fast quiz feed.
    Continuously serves cards balancing:
    1. Spaced Repetition (SRS): strengthening decaying knowledge.
    2. Probing (Epistemic Exploration): probing unknown nodes on the frontier.
    """

    async def get_next_feed_card(
        self,
        session: AsyncSession,
        user_id: str,
    ) -> Optional[FeedCardResponse]:
        # 0. Resolve User
        user_res = await session.execute(select(User).where(User.id == user_id))
        user = user_res.scalars().first()
        if not user:
            user_res = await session.execute(select(User).limit(1))
            user = user_res.scalars().first()
            if not user:
                user = User(username="hitori_learner", email="learner@gotit.local")
                session.add(user)
                await session.flush()
        resolved_user_id = user.id

        # 1. Find user enrolled tracks
        enrolled_tracks_res = await session.execute(
            select(Track)
            .join(UserTrackEnrollment, UserTrackEnrollment.track_id == Track.id)
            .where(
                and_(
                    UserTrackEnrollment.user_id == resolved_user_id,
                    UserTrackEnrollment.is_active_in_feed == True,
                )
            )
        )
        enrolled_tracks = enrolled_tracks_res.scalars().all()
        if not enrolled_tracks:
            # Fallback: select any active track
            tracks_res = await session.execute(select(Track).limit(1))
            enrolled_tracks = tracks_res.scalars().all()

        track_ids = [t.id for t in enrolled_tracks]

        # 2. Query concepts and user mastery states
        concepts_res = await session.execute(
            select(Concept, UserMasteryState, Track)
            .join(Track, Concept.track_id == Track.id)
            .outerjoin(
                UserMasteryState,
                and_(
                    UserMasteryState.concept_id == Concept.id,
                    UserMasteryState.user_id == user_id,
                ),
            )
            .where(Concept.track_id.in_(track_ids))
        )
        candidates = concepts_res.all()
        if not candidates:
            return None

        # 3. Score candidates based on SRS due date & Probing uncertainty
        scored_candidates = []
        now = datetime.utcnow()

        for concept, mastery, track in candidates:
            m_prob = mastery.mastery_prob if mastery else 0.0
            uncertainty = mastery.uncertainty if mastery else 1.0
            is_due = (mastery.next_review_due <= now) if (mastery and mastery.next_review_due) else False

            # Calculate priority score
            srs_score = 3.5 if is_due else 0.0
            probe_score = uncertainty * 2.0
            total_score = srs_score + probe_score

            mode = "srs" if (is_due and m_prob > 0.5) else "probe"
            scored_candidates.append({
                "concept": concept,
                "mastery": mastery,
                "track": track,
                "score": total_score,
                "mode": mode,
                "m_prob": m_prob,
                "uncertainty": uncertainty,
            })

        # Sort highest score first, with some stochastic jitter for feed variety
        scored_candidates.sort(key=lambda x: x["score"] + random.uniform(0, 0.5), reverse=True)
        selected = scored_candidates[0]

        target_concept: Concept = selected["concept"]
        mode = selected["mode"]

        # 4. Fetch or generate assessment item for this concept
        items_res = await session.execute(
            select(AssessmentItem).where(AssessmentItem.concept_id == target_concept.id)
        )
        available_items = items_res.scalars().all()

        if available_items:
            chosen_item = random.choice(available_items)
            options = [
                QuizOption(
                    id=opt.get("id", str(i)),
                    text=opt.get("text", ""),
                )
                for i, opt in enumerate(chosen_item.options)
            ]
            prompt = chosen_item.prompt_markdown
            item_id = chosen_item.id
            item_type = chosen_item.item_type.value
        else:
            # Dynamically generate a quiz item via Fast Model and persist in DB
            item = await self._generate_dynamic_quiz(session, target_concept)
            options = [
                QuizOption(
                    id=opt.get("id", str(i)),
                    text=opt.get("text", ""),
                )
                for i, opt in enumerate(item.options)
            ]
            prompt = item.prompt_markdown
            item_id = item.id
            item_type = item.item_type.value

        return FeedCardResponse(
            card_id=item_id,
            concept_id=target_concept.id,
            concept_title=target_concept.title,
            concept_code=target_concept.code,
            track_title=selected["track"].title,
            item_type=item_type,
            prompt_markdown=prompt,
            options=options,
            card_mode=mode,
            current_mastery=selected["m_prob"],
            current_uncertainty=selected["uncertainty"],
            allow_voice_reasoning=True,
        )

    async def _generate_dynamic_quiz(self, session: AsyncSession, concept: Concept) -> AssessmentItem:
        messages = [
            {
                "role": "system",
                "content": (
                    "Generate a rigorous, bite-sized multiple-choice question for testing understanding of a concept. "
                    "Include 4 options (a, b, c, d), mark the correct one, and provide an explanation.\n"
                    "Output JSON: {\"prompt\": \"...\", \"options\": [{\"id\":\"a\", \"text\":\"...\", \"is_correct\": true, \"explanation\": \"...\"}, ...]}"
                ),
            },
            {
                "role": "user",
                "content": f"Concept: {concept.title}\nSummary: {concept.summary}",
            },
        ]
        generated = await ai_clients.generate_json(messages=messages, model=settings.FAST_MODEL)

        item = AssessmentItem(
            id=str(uuid.uuid4()),
            concept_id=concept.id,
            item_type=AssessmentType.SINGLE_CHOICE,
            prompt_markdown=generated.get("prompt", f"Question on {concept.title}"),
            options=generated.get("options", [
                {"id": "a", "text": "True", "is_correct": True, "explanation": "Correct"},
                {"id": "b", "text": "False", "is_correct": False},
            ]),
            difficulty=0.5,
        )
        session.add(item)
        await session.commit()
        return item

    async def evaluate_answer(
        self,
        session: AsyncSession,
        submission: QuizAnswerSubmission,
        voice_analysis: Optional[VoiceReasoningAnalysis] = None,
    ) -> QuizAnswerResult:
        """
        Evaluates answer, runs Bayesian Knowledge Tracing & FSRS update, and records attempt.
        """
        # 0. Resolve User
        user_res = await session.execute(select(User).where(User.id == submission.user_id))
        user = user_res.scalars().first()
        if not user:
            user_res = await session.execute(select(User).limit(1))
            user = user_res.scalars().first()
            if not user:
                user = User(username="hitori_learner", email="learner@gotit.local")
                session.add(user)
                await session.flush()
        resolved_user_id = user.id

        # 1. Fetch Concept and Mastery
        concept_res = await session.execute(select(Concept).where(Concept.id == submission.concept_id))
        concept = concept_res.scalars().first()
        if not concept:
            raise ValueError("Concept not found")

        mastery_res = await session.execute(
            select(UserMasteryState).where(
                and_(
                    UserMasteryState.user_id == resolved_user_id,
                    UserMasteryState.concept_id == submission.concept_id,
                )
            )
        )
        mastery = mastery_res.scalars().first()

        if not mastery:
            mastery = UserMasteryState(
                user_id=resolved_user_id,
                concept_id=submission.concept_id,
                mastery_prob=0.1,
                uncertainty=1.0,
            )
            session.add(mastery)

        # 2. Check correctness
        item_res = await session.execute(select(AssessmentItem).where(AssessmentItem.id == submission.card_id))
        item = item_res.scalars().first()

        if item:
            correct_options = [opt["id"] for opt in item.options if opt.get("is_correct")]
            explanation = next((opt.get("explanation", "") for opt in item.options if opt.get("is_correct")), "")
            is_correct = set(submission.selected_option_ids) == set(correct_options)
        else:
            # Dynamic question fallback check
            is_correct = "a" in submission.selected_option_ids
            correct_options = ["a"]
            explanation = "Correct deduction!"

        prior_m = mastery.mastery_prob
        prior_u = mastery.uncertainty

        # 3. Update BKT (Bayesian Knowledge Tracing)
        post_m, post_u = bkt_engine.update_mastery(
            prior_mastery=prior_m,
            prior_uncertainty=prior_u,
            is_correct=is_correct,
            voice_analysis=voice_analysis,
        )

        # 4. Update FSRS memory schedule
        stability, diff, retriev, next_due = fsrs_scheduler.update_memory_state(
            current_stability=mastery.stability,
            current_difficulty=mastery.difficulty,
            last_review_at=mastery.last_review_at,
            is_correct=is_correct,
        )

        mastery.mastery_prob = post_m
        mastery.uncertainty = post_u
        mastery.stability = stability
        mastery.difficulty = diff
        mastery.retrievability = retriev
        mastery.last_review_at = datetime.utcnow()
        mastery.next_review_due = next_due
        mastery.total_reviews = (mastery.total_reviews or 0) + 1
        if is_correct:
            mastery.successful_reviews = (mastery.successful_reviews or 0) + 1

        # 5. Record Attempt
        if not item:
            fallback_item_res = await session.execute(
                select(AssessmentItem).where(AssessmentItem.concept_id == submission.concept_id).limit(1)
            )
            item = fallback_item_res.scalars().first()
            if not item:
                item = AssessmentItem(
                    id=str(uuid.uuid4()),
                    concept_id=submission.concept_id,
                    item_type=AssessmentType.SINGLE_CHOICE,
                    prompt_markdown="Assessment Item",
                    options=[{"id": "a", "text": "Option A", "is_correct": True}],
                )
                session.add(item)
                await session.flush()

        attempt = AssessmentAttempt(
            user_id=resolved_user_id,
            assessment_item_id=item.id,
            source_context="quick_feed",
            selected_option_ids=submission.selected_option_ids,
            is_correct=is_correct,
            response_time_ms=submission.response_time_ms,
            prior_mastery=prior_m,
            posterior_mastery=post_m,
        )
        session.add(attempt)
        await session.commit()

        return QuizAnswerResult(
            is_correct=is_correct,
            correct_option_ids=correct_options,
            explanation=explanation,
            prior_mastery=prior_m,
            posterior_mastery=post_m,
            prior_uncertainty=prior_u,
            posterior_uncertainty=post_u,
            next_review_due=next_due.isoformat() if next_due else None,
            voice_analysis=voice_analysis,
        )


feed_orchestrator = FeedOrchestrator()
