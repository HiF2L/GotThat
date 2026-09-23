import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, Optional
from app.core.database import get_db_session
from app.schemas.tutor import (
    StartDeepSessionRequest,
    DeepStepAnswerSubmission,
    DeepStepAnswerResult,
    DeepStepPayload,
    PlannedDAGSchema,
)
from app.services.tutor.tutor_state_machine import tutor_state_machine
from app.services.tutor.step_executor import step_executor
from app.models.session import DeepLearningSession, DeepSessionStep
from app.models.ontology import Concept
from app.config import settings
from app.services.ai.client import ai_clients
from app.services.moderation import moderation_service
from sqlalchemy import select, and_, delete

logger = logging.getLogger("got_it.deep_tutor")
router = APIRouter(prefix="/deep", tags=["Deep Tutor Mode"])


@router.post("/start")
async def start_deep_session(
    request: StartDeepSessionRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Initializes a full Deep Learning Arc for a target concept.
    Begins in PROBING state to locate the knowledge edge.
    """
    if request.initial_user_context and request.initial_user_context.strip():
        await moderation_service.validate_or_raise(
            text=request.initial_user_context,
            context={"intent": "deep_session_init", "target_concept_id": request.target_concept_id},
        )

    session = await tutor_state_machine.start_session(db, request)
    next_action = await tutor_state_machine.get_next_action(
        session=db,
        deep_session_id=session.id,
        user_notes=request.initial_user_context or "",
    )
    return {
        "session_id": session.id,
        "status": session.status,
        "initial_action": next_action,
    }


from pydantic import BaseModel

class SubmitProbeAnswerRequest(BaseModel):
    session_id: str
    concept_id: str
    selected_option_id: str
    user_notes: Optional[str] = None


@router.post("/submit-probe")
async def submit_probe_answer(
    request: SubmitProbeAnswerRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Submits student's response to diagnostic probe.
    Advances diagnostic boundary and moves session towards planning when complete.
    """
    try:
        return await tutor_state_machine.record_probe_answer(
            session=db,
            deep_session_id=request.session_id,
            concept_id=request.concept_id,
            option_id=request.selected_option_id,
            user_notes=request.user_notes or "",
        )
    except Exception as e:
        logger.error(f"Error recording probe answer for session {request.session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to record diagnostic answer: {e}")


@router.get("/action/{session_id}")
async def get_next_tutor_action(
    session_id: str,
    user_notes: Optional[str] = Query(None, description="Optional user thinking scratchpad text"),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Fetches the next event in the state machine (Probe question -> Plan DAG -> Atomic Step).
    """
    return await tutor_state_machine.get_next_action(
        session=db,
        deep_session_id=session_id,
        user_notes=user_notes or "",
    )


class SelectStepRequest(BaseModel):
    session_id: str
    concept_id: str
    user_notes: Optional[str] = None


@router.post("/select-step")
async def select_concept_step(
    request: SelectStepRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Directly jumps to a specific concept within an active deep session DAG.
    """
    try:
        return await tutor_state_machine.switch_concept_step(
            session=db,
            deep_session_id=request.session_id,
            concept_id=request.concept_id,
            user_notes=request.user_notes or "",
        )
    except Exception as e:
        logger.error(f"Failed to switch concept step: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to switch step: {e}")


@router.post("/submit-step", response_model=DeepStepAnswerResult)
async def submit_step_verification(
    submission: DeepStepAnswerSubmission,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Submits user answer for the current step's verification challenge.
    Unlocks progress or triggers Remediation Branching on mistake.
    """
    try:
        session_res = await db.execute(
            select(DeepLearningSession).where(DeepLearningSession.id == submission.session_id)
        )
        deep_session = session_res.scalars().first()
        if not deep_session:
            raise HTTPException(status_code=404, detail="Сессия обучения не найдена.")

        result = await step_executor.evaluate_step_answer(
            session=db,
            deep_session=deep_session,
            submission=submission,
        )

        if result.is_correct:
            # Advance DAG to next node
            await tutor_state_machine.advance_to_next_node(db, deep_session.id)

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting step answer: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка проверки ответа: {str(e)}")


from fastapi import UploadFile, File
from app.services.ai.stt_service import stt_service

class PrefetchStepRequest(BaseModel):
    session_id: str
    concept_id: str
    step_sequence: Optional[int] = None
    user_notes: Optional[str] = None


@router.post("/prefetch")
async def prefetch_next_lesson(
    request: PrefetchStepRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Speculatively pre-generates the next lesson in the background so that
    when the user finishes reading and clicks Next Lesson, it opens with 0ms latency.
    """
    session_res = await db.execute(
        select(DeepLearningSession).where(DeepLearningSession.id == request.session_id)
    )
    deep_session = session_res.scalars().first()
    if not deep_session:
        raise HTTPException(status_code=404, detail="Session not found")

    step_seq = request.step_sequence or (deep_session.current_concept_index + 2)
    step_executor.trigger_background_prefetch(
        user_id=deep_session.user_id,
        session_id=deep_session.id,
        concept_id=request.concept_id,
        step_sequence=step_seq,
        user_notes=request.user_notes or "",
    )
    return {"status": "prefetching_started", "concept_id": request.concept_id}


@router.post("/transcribe-note")
async def transcribe_deep_tutor_voice_note(
    audio_file: UploadFile = File(...),
):
    """
    Transcribes audio notes recorded during Deep Tutor sessions and returns text
    to unify Spoken Reasoning + Text Yap into the AI tutor's contextual reasoning.
    """
    audio_bytes = await audio_file.read()
    transcript = await stt_service.transcribe_audio(audio_bytes, audio_file.filename or "voice_yap.webm")
    return {"transcript": transcript}


class AskTutorRequest(BaseModel):
    session_id: str
    step_sequence: int
    question: str


@router.post("/ask-tutor")
async def ask_tutor_in_lesson(
    request: AskTutorRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Allows the student to ask questions, request alternative analogies, derivations,
    or clarifications live during any lesson without losing step state.
    """
    session_res = await db.execute(
        select(DeepLearningSession).where(DeepLearningSession.id == request.session_id)
    )
    deep_session = session_res.scalars().first()
    if not deep_session:
        raise HTTPException(status_code=404, detail="Session not found")

    step_res = await db.execute(
        select(DeepSessionStep).where(
            and_(
                DeepSessionStep.session_id == request.session_id,
                DeepSessionStep.step_sequence == request.step_sequence,
            )
        )
    )
    step = step_res.scalars().first()
    step_context = step.explanation_markdown if step else "Current Lesson Step"

    concept_res = await db.execute(
        select(Concept).where(Concept.id == step.concept_id if step else deep_session.current_concept_id)
    )
    concept = concept_res.scalars().first()
    concept_title = concept.title if concept else "Current Concept"

    # Safety & Content Moderation Audit on student question
    await moderation_service.validate_or_raise(
        text=request.question,
        context={"intent": "ask_tutor_question", "topic": concept_title},
    )

    target_lang = getattr(deep_session, "language", None) or "ru"
    is_russian = (target_lang == "ru") or any('\u0400' <= char <= '\u04FF' for char in (request.question or ""))
    if target_lang == "en":
        is_russian = False

    lang_rule = (
        "CRITICAL LANGUAGE MANDATE: Respond strictly in fluent, natural RUSSIAN (Русский язык). Even if technical terms are in English, all explanations MUST be in Russian."
        if is_russian
        else "CRITICAL LANGUAGE MANDATE: Respond strictly in fluent, natural ENGLISH."
    )

    messages = [
        {
            "role": "system",
            "content": (
                "You are an elite, patient, world-class 1-on-1 private tutor.\n"
                "The student is currently reading a lesson and has asked a specific question.\n"
                "Explain the answer with extraordinary clarity, first-principles intuition, and LaTeX math where helpful.\n"
                f"{lang_rule}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Topic: {concept_title}\n"
                f"Current Lesson Context:\n{step_context}\n\n"
                f"Student Question: {request.question}"
            ),
        },
    ]

    answer = await ai_clients.generate_chat(
        messages=messages,
        model=settings.DEEP_MODEL,
        temperature=0.3,
    )

    if step:
        current_qa = list(step.qa_history or [])
        current_qa.append({"question": request.question, "answer": answer})
        step.qa_history = current_qa
        await db.commit()

    return {"answer_markdown": answer}


class RegenerateStepRequest(BaseModel):
    session_id: str
    concept_id: Optional[str] = None
    step_sequence: Optional[int] = None
    user_notes: Optional[str] = None


@router.post("/regenerate-step", response_model=DeepStepPayload)
async def regenerate_tutorial_step(
    request: RegenerateStepRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Forces AI to re-generate the current tutorial step with fresh wording, analogies,
    illustrations, and verification questions without advancing or resetting the DAG.
    """
    session_res = await db.execute(
        select(DeepLearningSession).where(DeepLearningSession.id == request.session_id)
    )
    deep_session = session_res.scalars().first()
    if not deep_session:
        raise HTTPException(status_code=404, detail="Session not found")

    target_cid = request.concept_id or deep_session.current_concept_id
    concept_res = await db.execute(select(Concept).where(Concept.id == target_cid))
    concept = concept_res.scalars().first()
    if not concept:
        raise HTTPException(status_code=404, detail="Concept not found")

    step_seq = request.step_sequence or (deep_session.current_concept_index + 1)

    # Delete previous cached step in SQLite to guarantee a fresh generation
    await db.execute(
        delete(DeepSessionStep).where(
            and_(
                DeepSessionStep.session_id == deep_session.id,
                DeepSessionStep.concept_id == concept.id,
            )
        )
    )
    await db.commit()

    step_payload = await step_executor.execute_atomic_step(
        session=db,
        deep_session=deep_session,
        concept=concept,
        step_sequence=step_seq,
        user_notes=request.user_notes or "",
        force_regenerate=True,
    )
    return step_payload


import io
from fastapi.responses import StreamingResponse
from app.services.ai.tts_service import tts_service

class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = None
    speed: Optional[float] = 1.0


@router.post("/tts")
async def synthesize_lesson_speech(
    request: TTSRequest,
):
    """
    Synthesizes clean speech for a tutorial lesson using ProxyAPI (gpt-4o-mini-tts).
    Returns binary MP3 streaming audio.
    """
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    try:
        audio_bytes = await tts_service.synthesize_speech(
            text=request.text,
            voice=request.voice,
            speed=request.speed or 1.0,
        )
        if not audio_bytes:
            raise HTTPException(status_code=500, detail="Failed to generate audio")

        return StreamingResponse(
            io.BytesIO(audio_bytes),
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": "inline; filename=lesson_speech.mp3",
                "Content-Length": str(len(audio_bytes)),
                "Accept-Ranges": "bytes",
            },
        )
    except Exception as e:
        logger.error(f"TTS synthesis error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"TTS synthesis failed: {e}")


