from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from app.core.database import get_db_session
from app.schemas.feed import (
    FeedCardResponse,
    QuizAnswerSubmission,
    QuizAnswerResult,
    DiscoveryLessonTeaser,
    ConceptVoteRequest,
    ConceptVoteResponse,
)
from app.services.feed.feed_orchestrator import feed_orchestrator
from app.services.ai.stt_service import stt_service
from app.models.ontology import Concept, AssessmentItem
from sqlalchemy import select

router = APIRouter(prefix="/feed", tags=["Feed"])


@router.get("/discovery", response_model=List[DiscoveryLessonTeaser])
async def get_discovery_feed(
    user_id: Optional[str] = Query(None, description="Optional user ID for personalized mastery tags"),
    limit: int = Query(20, ge=1, le=100, description="Max teasers to return"),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Discovery Feed: Exploratory recommendation stream of lessons with introductory teasers/hooks
    and seamless one-click bridge to Deep Tutor.
    """
    return await feed_orchestrator.get_discovery_feed(db, user_id=user_id, limit=limit)


@router.post("/vote", response_model=ConceptVoteResponse)
async def vote_concept(
    body: ConceptVoteRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Records an upvote, downvote, or vote clearing for a concept card in the feed.
    """
    try:
        return await feed_orchestrator.record_concept_vote(
            session=db,
            user_id=body.user_id,
            concept_id=body.concept_id,
            vote_type=body.vote_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))




@router.get("/next", response_model=FeedCardResponse)
async def get_next_feed_card(
    user_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Fetches the next prioritized quiz card in TikTok/Duolingo style.
    Combines SRS review needs and frontier probing.
    """
    card = await feed_orchestrator.get_next_feed_card(db, user_id)
    if not card:
        raise HTTPException(status_code=404, detail="No active cards found for enrolled tracks")
    return card


@router.post("/attempt", response_model=QuizAnswerResult)
async def submit_quiz_answer(
    submission: QuizAnswerSubmission,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Submits a choice answer for a feed card. Updates Bayesian mastery and FSRS intervals.
    """
    return await feed_orchestrator.evaluate_answer(
        session=db,
        submission=submission,
        voice_analysis=None,
    )


@router.post("/voice-attempt", response_model=QuizAnswerResult)
async def submit_voice_reasoning_answer(
    user_id: str = Form(...),
    card_id: str = Form(...),
    concept_id: str = Form(...),
    selected_option_id: str = Form(...),
    audio_file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Voice Yap Mode: Uploads audio of student's spoken reasoning.
    Transcribes audio -> LLM extracts cognitive coherence -> BKT leaps!
    """
    # 1. Transcribe audio via dedicated STT provider (ProxyAPI)
    audio_bytes = await audio_file.read()
    transcript = await stt_service.transcribe_audio(audio_bytes, audio_file.filename or "voice.wav")

    # 2. Get question prompt and concept title
    concept_res = await db.execute(select(Concept).where(Concept.id == concept_id))
    concept = concept_res.scalars().first()
    concept_title = concept.title if concept else "Concept"

    item_res = await db.execute(select(AssessmentItem).where(AssessmentItem.id == card_id))
    item = item_res.scalars().first()
    prompt = item.prompt_markdown if item else "Question"
    correct_summary = next((o.get("explanation", "") for o in (item.options if item else []) if o.get("is_correct")), "")

    # 3. Analyze mental model from spoken transcript
    voice_analysis = await stt_service.analyze_reasoning(
        transcript=transcript,
        question_prompt=prompt,
        correct_answer_summary=correct_summary,
        concept_title=concept_title,
    )

    # 4. Evaluate answer with voice boost
    submission = QuizAnswerSubmission(
        user_id=user_id,
        card_id=card_id,
        concept_id=concept_id,
        selected_option_ids=[selected_option_id],
        yap_text_note=transcript,
    )

    return await feed_orchestrator.evaluate_answer(
        session=db,
        submission=submission,
        voice_analysis=voice_analysis,
    )
