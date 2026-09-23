import random
import uuid
import re
from typing import List, Optional, Dict
from datetime import datetime
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.ontology import Concept, AssessmentItem, Track, AssessmentType
from app.models.session import DeepSessionStep
from app.models.mastery import (
    UserMasteryState,
    AssessmentAttempt,
    VoiceReasoningLog,
    UserTrackEnrollment,
    User,
    ConceptReaction,
)
from app.schemas.feed import (
    FeedCardResponse,
    QuizOption,
    QuizAnswerSubmission,
    QuizAnswerResult,
    VoiceReasoningAnalysis,
    DiscoveryLessonTeaser,
    ConceptVoteResponse,
)
from app.services.cognitive.bkt_engine import bkt_engine
from app.services.cognitive.fsrs_scheduler import fsrs_scheduler
from app.services.ai.client import ai_clients, sanitize_markdown_text
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

    async def get_discovery_feed(
        self,
        session: AsyncSession,
        user_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[DiscoveryLessonTeaser]:
        """
        Generates an exploratory recommendation feed (Discovery Feed):
        Extracts teasers (introductory hooks, intuitive dilemmas, mental models)
        of lessons from active tracks in the knowledge graph.
        Provides a seamless bridge to launch the lesson in Deep Tutor.
        """
        # 1. Resolve User ID if provided
        resolved_user_id = user_id
        if not resolved_user_id:
            user_res = await session.execute(select(User).limit(1))
            user = user_res.scalars().first()
            if user:
                resolved_user_id = user.id

        # 2. Query concepts that ALREADY have generated full lesson steps
        # This guarantees only ready, rich, substantive lessons appear in the feed
        generated_steps_query = (
            select(Concept, Track, DeepSessionStep)
            .join(Track, Concept.track_id == Track.id)
            .join(DeepSessionStep, DeepSessionStep.concept_id == Concept.id)
            .where(
                and_(
                    Track.is_active == True,
                    func.length(DeepSessionStep.explanation_markdown) >= 150,
                )
            )
            .order_by(DeepSessionStep.step_sequence.asc())
        )
        steps_result = await session.execute(generated_steps_query)
        generated_rows = steps_result.all()

        seen_concepts = set()
        concepts_and_tracks = []
        steps_map: Dict[str, DeepSessionStep] = {}
        for c, t, s in generated_rows:
            if c.id not in seen_concepts:
                seen_concepts.add(c.id)
                concepts_and_tracks.append((c, t))
                steps_map[c.id] = s

        # Fallback: if no generated steps exist in DB at all (e.g. initial bare unit tests)
        if not concepts_and_tracks:
            fallback_query = (
                select(Concept, Track)
                .join(Track, Concept.track_id == Track.id)
                .where(Track.is_active == True)
            )
            fallback_res = await session.execute(fallback_query)
            concepts_and_tracks = fallback_res.all()
            if not concepts_and_tracks:
                return []

        # 3. Calculate total concepts per track for context
        track_counts: Dict[str, int] = {}
        for c, t in concepts_and_tracks:
            track_counts[t.id] = track_counts.get(t.id, 0) + 1

        # 4. Fetch mastery states for resolved_user_id
        concept_ids = [c.id for c, _ in concepts_and_tracks]
        mastery_map: Dict[str, UserMasteryState] = {}
        if resolved_user_id:
            mastery_res = await session.execute(
                select(UserMasteryState).where(
                    and_(
                        UserMasteryState.user_id == resolved_user_id,
                        UserMasteryState.concept_id.in_(concept_ids),
                    )
                )
            )
            mastery_map = {m.concept_id: m for m in mastery_res.scalars().all()}

        # 5b. Fetch reactions & votes for these concepts
        user_votes_map: Dict[str, str] = {}
        if resolved_user_id:
            user_react_res = await session.execute(
                select(ConceptReaction).where(
                    and_(
                        ConceptReaction.user_id == resolved_user_id,
                        ConceptReaction.concept_id.in_(concept_ids),
                    )
                )
            )
            for r in user_react_res.scalars().all():
                user_votes_map[r.concept_id] = r.vote_type

        # Aggregate upvotes and downvotes
        upvotes_query = await session.execute(
            select(ConceptReaction.concept_id, func.count(ConceptReaction.id))
            .where(
                and_(
                    ConceptReaction.concept_id.in_(concept_ids),
                    ConceptReaction.vote_type == "upvote",
                )
            )
            .group_by(ConceptReaction.concept_id)
        )
        upvotes_map = {cid: cnt for cid, cnt in upvotes_query.all()}

        downvotes_query = await session.execute(
            select(ConceptReaction.concept_id, func.count(ConceptReaction.id))
            .where(
                and_(
                    ConceptReaction.concept_id.in_(concept_ids),
                    ConceptReaction.vote_type == "downvote",
                )
            )
            .group_by(ConceptReaction.concept_id)
        )
        downvotes_map = {cid: cnt for cid, cnt in downvotes_query.all()}

        # 6. Build teasers
        teasers: List[DiscoveryLessonTeaser] = []
        for concept, track in concepts_and_tracks:
            m = mastery_map.get(concept.id)
            is_mastered = (m.mastery_prob >= 0.85) if m else False
            mastery_prob = round(m.mastery_prob, 2) if m else 0.0

            # Extract teaser text
            step = steps_map.get(concept.id)
            step_markdown = step.explanation_markdown if step else ""
            teaser_text = self._extract_teaser_text(
                explanation_markdown=step_markdown,
                summary=concept.summary,
                title=concept.title,
            )

            # Social scoring & metadata
            seed = (abs(hash(concept.code or concept.id)) % 68) + 18
            upvotes_cnt = upvotes_map.get(concept.id, 0)
            downvotes_cnt = downvotes_map.get(concept.id, 0)
            score = seed + upvotes_cnt - downvotes_cnt
            user_vote = user_votes_map.get(concept.id)

            words_count = len(teaser_text.split())
            read_time = max(2, min(8, round(words_count / 45) + 1))
            comments_count = (abs(hash(concept.title or concept.id)) % 14) + 2

            teasers.append(
                DiscoveryLessonTeaser(
                    concept_id=concept.id,
                    concept_title=concept.title,
                    concept_code=concept.code,
                    track_id=track.id,
                    track_title=track.title,
                    track_slug=track.slug,
                    teaser_text=teaser_text,
                    bloom_level=concept.bloom_level,
                    is_mastered=is_mastered,
                    total_track_concepts=track_counts.get(track.id, 1),
                    mastery_prob=mastery_prob,
                    score=score,
                    upvotes=upvotes_cnt,
                    downvotes=downvotes_cnt,
                    user_vote=user_vote,
                    comments_count=comments_count,
                    read_time_minutes=read_time,
                )
            )

        # 7. Shuffle and interleave tracks to guarantee topic diversity
        tracks_buckets: Dict[str, List[DiscoveryLessonTeaser]] = {}
        for t in teasers:
            tracks_buckets.setdefault(t.track_id, []).append(t)

        buckets_list = list(tracks_buckets.values())
        random.shuffle(buckets_list)
        for bucket in buckets_list:
            random.shuffle(bucket)

        interleaved: List[DiscoveryLessonTeaser] = []
        max_len = max(len(b) for b in buckets_list) if buckets_list else 0
        for i in range(max_len):
            for bucket in buckets_list:
                if i < len(bucket):
                    interleaved.append(bucket[i])

        return interleaved[:limit]

    def _extract_teaser_text(
        self,
        explanation_markdown: str,
        summary: str,
        title: str,
    ) -> str:
        """
        Extracts an engaging, substantive pedagogical excerpt from a lesson explanation.
        Provides a comprehensive preview (650-1000 characters) so that the user gets
        real educational value directly in their feed.
        """
        if explanation_markdown and len(explanation_markdown.strip()) > 50:
            cleaned = sanitize_markdown_text(explanation_markdown).strip()
            raw_paragraphs = [p.strip() for p in cleaned.split("\n\n") if p.strip()]

            # 1. Filter out solitary markdown separators, empty headings, and duplicate H1s
            paragraphs = []
            for p in raw_paragraphs:
                if p in ("#", "##", "###", "####", "---", "***", "___"):
                    continue
                if p.startswith("# ") and len(p.split("\n")) == 1:
                    continue
                if re.match(r"^#{1,3}\s*(?:4|5|IV|V|\bПРАКТИКА\b|\bТЕСТ\b|\bЗАДАНИЯ\b|\bПРОВЕРКА\b)", p, re.IGNORECASE):
                    break
                paragraphs.append(p)

            # 2. Accumulate paragraphs with image awareness
            hook_paragraphs = []
            char_count = 0
            for p in paragraphs:
                is_img = p.startswith("![") and "](" in p
                hook_paragraphs.append(p)
                # Count actual readable characters (excluding image markdown URLs)
                readable_len = len(re.sub(r'!\[.*?\]\(.*?\)', '', p))
                char_count += readable_len

                if char_count >= 650:
                    # If the current paragraph is an image, don't stop yet — take the next text paragraph
                    if is_img:
                        continue
                    break

            # 3. Guarantee that an image is never left stranded at the very bottom of the card
            if hook_paragraphs and hook_paragraphs[-1].startswith("!["):
                if len(paragraphs) > len(hook_paragraphs):
                    hook_paragraphs.append(paragraphs[len(hook_paragraphs)])
                else:
                    hook_paragraphs.pop()

            if hook_paragraphs:
                result = "\n\n".join(hook_paragraphs)
                if len(result) > 1350:
                    result = result[:1347].rstrip() + "..."
                return result

        if summary and len(summary.strip()) > 20:
            return summary.strip()

        return f"Откройте фундаментальные принципы, скрытые механизмы и ключевые интуиции темы «{title}»."

    async def record_concept_vote(
        self,
        session: AsyncSession,
        user_id: str,
        concept_id: str,
        vote_type: str,
    ) -> ConceptVoteResponse:
        """
        Records or clears a user's upvote/downvote reaction for a concept,
        and returns updated vote counts and net score.
        """
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

        # 1. Fetch existing reaction
        existing_res = await session.execute(
            select(ConceptReaction).where(
                and_(
                    ConceptReaction.user_id == resolved_user_id,
                    ConceptReaction.concept_id == concept_id,
                )
            )
        )
        existing = existing_res.scalars().first()

        effective_vote: Optional[str] = None
        if vote_type == "clear":
            if existing:
                await session.delete(existing)
            effective_vote = None
        elif vote_type in ("upvote", "downvote"):
            if existing:
                existing.vote_type = vote_type
                existing.updated_at = datetime.utcnow()
            else:
                reaction = ConceptReaction(
                    user_id=resolved_user_id,
                    concept_id=concept_id,
                    vote_type=vote_type,
                )
                session.add(reaction)
            effective_vote = vote_type
        else:
            raise ValueError(f"Invalid vote_type '{vote_type}'. Must be 'upvote', 'downvote', or 'clear'.")

        await session.commit()

        # 2. Compute updated aggregates
        upvotes_res = await session.execute(
            select(func.count(ConceptReaction.id)).where(
                and_(
                    ConceptReaction.concept_id == concept_id,
                    ConceptReaction.vote_type == "upvote",
                )
            )
        )
        upvotes_count = upvotes_res.scalar() or 0

        downvotes_res = await session.execute(
            select(func.count(ConceptReaction.id)).where(
                and_(
                    ConceptReaction.concept_id == concept_id,
                    ConceptReaction.vote_type == "downvote",
                )
            )
        )
        downvotes_count = downvotes_res.scalar() or 0

        concept_res = await session.execute(select(Concept).where(Concept.id == concept_id))
        concept = concept_res.scalars().first()
        seed = (abs(hash((concept.code if concept else concept_id))) % 68) + 18
        net_score = seed + upvotes_count - downvotes_count

        return ConceptVoteResponse(
            concept_id=concept_id,
            user_vote=effective_vote,
            score=net_score,
            upvotes=upvotes_count,
            downvotes=downvotes_count,
        )


feed_orchestrator = FeedOrchestrator()

