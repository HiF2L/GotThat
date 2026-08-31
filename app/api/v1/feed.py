from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.core.database import get_db_session
from app.schemas.feed import FeedCardResponse, QuizAnswerSubmission, QuizAnswerResult
from app.services.feed.feed_orchestrator import feed_orchestrator
from app.services.ai.stt_service import stt_service
from app.models.ontology import Concept, AssessmentItem
from sqlalchemy import select

router = APIRouter(prefix="/feed", tags=["Quick Feed"])


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
