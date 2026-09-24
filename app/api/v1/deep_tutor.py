import logging
import json
import asyncio
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, Optional
from app.core.database import get_db_session, async_session_maker
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
from app.models.mastery import User
from app.config import settings
from app.services.ai.client import ai_clients
from app.services.ai.cost_tracker import cost_tracker
from app.services.moderation import moderation_service
from app.services.tutor.step_executor import step_executor, is_valid_complete_step
from sqlalchemy import select, and_, delete, or_

logger = logging.getLogger("got_it.deep_tutor")
router = APIRouter(prefix="/deep", tags=["Deep Tutor Mode"])


@router.get("/active-session")
async def get_active_session(
    user_id: str = Query(...),
    target_concept_id: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Returns the user's ongoing DeepLearningSession to instantly restore state on reload.
    Supports resolving session by:
    1. Direct session_id
    2. Target concept step lookup (finds the exact session containing this concept)
    3. Target concept track / session match
    4. User resolution (by User.id or User.username, with graceful fallback)
    Also embeds cached_step if available to allow single-trip instant UI hydration.
    """
    sess = None

    # 1. Direct session ID lookup if provided
    if session_id:
        s_res = await db.execute(
            select(DeepLearningSession).where(DeepLearningSession.id == session_id)
        )
        sess = s_res.scalars().first()

    # 2. Resolve user entity (supports UUID, username, or fallback to first user)
    effective_user_id = user_id
    u_res = await db.execute(
        select(User).where(or_(User.id == user_id, User.username == user_id))
    )
    user_obj = u_res.scalars().first()
    if user_obj:
        effective_user_id = user_obj.id
    else:
        first_user = (await db.execute(select(User).limit(1))).scalars().first()
        if first_user:
            effective_user_id = first_user.id

    target_concept = None
    if not sess and target_concept_id:
        c_res = await db.execute(
            select(Concept).where(
                or_(
                    Concept.id == target_concept_id,
                    Concept.slug == target_concept_id,
                    Concept.code == target_concept_id,
                )
            )
        )
        target_concept = c_res.scalars().first()

        # 3. Check if any session already has a generated step for this concept!
        if target_concept:
            step_sess_res = await db.execute(
                select(DeepLearningSession)
                .join(DeepSessionStep, DeepSessionStep.session_id == DeepLearningSession.id)
                .where(
                    and_(
                        DeepLearningSession.user_id == effective_user_id,
                        DeepSessionStep.concept_id == target_concept.id,
                    )
                )
                .order_by(DeepSessionStep.created_at.desc())
            )
            sess = step_sess_res.scalars().first()
            if not sess:
                # Fallback without user_id restriction
                step_sess_res = await db.execute(
                    select(DeepLearningSession)
                    .join(DeepSessionStep, DeepSessionStep.session_id == DeepLearningSession.id)
                    .where(DeepSessionStep.concept_id == target_concept.id)
                    .order_by(DeepSessionStep.created_at.desc())
                )
                sess = step_sess_res.scalars().first()

        # 4. Check track or target_concept_id on the session itself
        if not sess:
            query = select(DeepLearningSession).where(DeepLearningSession.user_id == effective_user_id)
            if target_concept and target_concept.track_id:
                track_concepts_res = await db.execute(
                    select(Concept.id).where(Concept.track_id == target_concept.track_id)
                )
                track_cids = track_concepts_res.scalars().all()
                query = query.where(
                    or_(
                        DeepLearningSession.target_concept_id == target_concept.id,
                        DeepLearningSession.target_concept_id.in_(track_cids),
                    )
                )
            elif target_concept:
                query = query.where(DeepLearningSession.target_concept_id == target_concept.id)
            else:
                query = query.where(DeepLearningSession.target_concept_id == target_concept_id)

            query = query.order_by(DeepLearningSession.created_at.desc())
            sess = (await db.execute(query)).scalars().first()

            if not sess and target_concept:
                # Fallback without user_id restriction
                fb_query = select(DeepLearningSession)
                if target_concept.track_id:
                    track_concepts_res = await db.execute(
                        select(Concept.id).where(Concept.track_id == target_concept.track_id)
                    )
                    track_cids = track_concepts_res.scalars().all()
                    fb_query = fb_query.where(
                        or_(
                            DeepLearningSession.target_concept_id == target_concept.id,
                            DeepLearningSession.target_concept_id.in_(track_cids),
                        )
                    )
                else:
                    fb_query = fb_query.where(DeepLearningSession.target_concept_id == target_concept.id)
                fb_query = fb_query.order_by(DeepLearningSession.created_at.desc())
                sess = (await db.execute(fb_query)).scalars().first()

    # 5. Fallback: latest session for user
    if not sess:
        latest_res = await db.execute(
            select(DeepLearningSession)
            .where(DeepLearningSession.user_id == effective_user_id)
            .order_by(DeepLearningSession.created_at.desc())
        )
        sess = latest_res.scalars().first()

    if not sess:
        raise HTTPException(status_code=404, detail="No active session found")

    # 6. Try embedding the target or current lesson step for instant 0-latency UI hydration
    cached_step_dict = None
    cid_to_check = (target_concept.id if target_concept else None) or sess.current_concept_id
    if cid_to_check:
        step_res = await db.execute(
            select(DeepSessionStep)
            .where(
                and_(
                    DeepSessionStep.session_id == sess.id,
                    DeepSessionStep.concept_id == cid_to_check,
                    DeepSessionStep.explanation_markdown.isnot(None),
                )
            )
            .order_by(DeepSessionStep.created_at.desc())
        )
        for s in step_res.scalars().all():
            if s.explanation_markdown and is_valid_complete_step(s.explanation_markdown):
                c_step = target_concept
                if not c_step or c_step.id != s.concept_id:
                    c_step = (await db.execute(select(Concept).where(Concept.id == s.concept_id))).scalars().first()
                if c_step:
                    seq = s.step_sequence or (sess.current_concept_index + 1)
                    payload = step_executor._build_step_payload_from_db(s, c_step, sess, seq)
                    cached_step_dict = payload.model_dump()
                break

    return {
        "session_id": sess.id,
        "status": sess.status,
        "current_concept_index": sess.current_concept_index,
        "current_concept_id": sess.current_concept_id,
        "planned_dag": sess.planned_dag,
        "mermaid_diagram": sess.mermaid_diagram,
        "language": sess.language,
        "depth_level": sess.depth_level,
        "cached_step": cached_step_dict,
    }


@router.get("/step/{concept_id}", response_model=DeepStepPayload)
async def get_cached_step(
    concept_id: str,
    session_id: Optional[str] = Query(None),
    step_sequence: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Direct REST retrieval of an existing lesson step.
    Checks SQLite (both current session and global cache).
    Returns DeepStepPayload in < 10ms with 0 LLM calls, or 404 if step needs generation.
    """
    c_res = await db.execute(
        select(Concept).where(
            or_(
                Concept.id == concept_id,
                Concept.slug == concept_id,
                Concept.code == concept_id,
            )
        )
    )
    concept = c_res.scalars().first()
    if not concept:
        raise HTTPException(status_code=404, detail="Concept not found")

    existing_step = None
    deep_session = None
    if session_id:
        s_res = await db.execute(select(DeepLearningSession).where(DeepLearningSession.id == session_id))
        deep_session = s_res.scalars().first()
        step_res = await db.execute(
            select(DeepSessionStep)
            .where(
                and_(
                    DeepSessionStep.session_id == session_id,
                    DeepSessionStep.concept_id == concept.id,
                    DeepSessionStep.explanation_markdown.isnot(None),
                )
            )
            .order_by(DeepSessionStep.created_at.desc())
        )
        for s in step_res.scalars().all():
            if s.explanation_markdown and is_valid_complete_step(s.explanation_markdown):
                existing_step = s
                break

    if not existing_step:
        global_step_res = await db.execute(
            select(DeepSessionStep)
            .where(
                and_(
                    DeepSessionStep.concept_id == concept.id,
                    DeepSessionStep.explanation_markdown.isnot(None),
                )
            )
            .order_by(DeepSessionStep.created_at.desc())
        )
        for s in global_step_res.scalars().all():
            if s.explanation_markdown and is_valid_complete_step(s.explanation_markdown):
                if deep_session:
                    seq = step_sequence or (deep_session.current_concept_index + 1)
                    cloned = DeepSessionStep(
                        session_id=deep_session.id,
                        concept_id=concept.id,
                        step_sequence=seq,
                        step_type=s.step_type or "explanation",
                        explanation_markdown=s.explanation_markdown,
                        visual_type=s.visual_type,
                        visual_payload=s.visual_payload,
                        visual_alt=s.visual_alt,
                        verification_challenge=s.verification_challenge,
                        verification_passed=False,
                    )
                    db.add(cloned)
                    await db.commit()
                    await db.refresh(cloned)
                    existing_step = cloned
                else:
                    existing_step = s
                break

    if not existing_step or not existing_step.explanation_markdown or not is_valid_complete_step(existing_step.explanation_markdown):
        raise HTTPException(status_code=404, detail="Step not yet synthesized")

    if not deep_session:
        class _MockSession:
            id = existing_step.session_id
            user_id = "default"
        deep_session = _MockSession()

    effective_seq = step_sequence or existing_step.step_sequence or 1
    payload = step_executor._build_step_payload_from_db(existing_step, concept, deep_session, effective_seq)

    from app.services.ai.tts_service import tts_service
    asyncio.create_task(tts_service.prefetch_audio(payload.explanation_markdown))

    return payload


class PrefetchPipelineRequest(BaseModel):
    session_id: str
    current_concept_id: str
    step_sequence: Optional[int] = 1


@router.post("/prefetch-pipeline")
async def trigger_prefetch_pipeline_endpoint(
    request: PrefetchPipelineRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Triggers the rolling 2-lesson ahead text and TTS audio pipeline.
    """
    s_res = await db.execute(select(DeepLearningSession).where(DeepLearningSession.id == request.session_id))
    deep_sess = s_res.scalars().first()
    if not deep_sess:
        raise HTTPException(status_code=404, detail="Session not found")

    step_executor.trigger_background_prefetch_pipeline(
        user_id=deep_sess.user_id,
        session_id=deep_sess.id,
        current_concept_id=request.current_concept_id,
        current_sequence=request.step_sequence or 1,
    )
    return {"status": "pipeline_started", "session_id": request.session_id}


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
    if session.status == "probing":
        next_action = await tutor_state_machine.get_next_action(
            session=db,
            deep_session_id=session.id,
            user_notes=request.initial_user_context or "",
        )
    else:
        # Plan is ready! Return plan_ready immediately so that the frontend can stream Lesson 1 live
        next_action = {
            "phase": "plan_ready",
            "session_id": session.id,
            "dag": session.planned_dag,
            "mermaid_diagram": session.mermaid_diagram or (session.planned_dag or {}).get("mermaid_code", ""),
            "message": "Учебный план курса сформирован.",
        }
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


class StreamStepRequest(BaseModel):
    session_id: str
    concept_id: Optional[str] = None
    user_notes: Optional[str] = None


@router.post("/stream-step")
async def stream_lesson_step(
    request: StreamStepRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Live Server-Sent Events (SSE) streaming of a lesson tutorial.
    Tokens stream in real time (within 1-2s), preventing timeouts and showing progress live.
    """
    session_res = await db.execute(
        select(DeepLearningSession).where(DeepLearningSession.id == request.session_id)
    )
    deep_session = session_res.scalars().first()
    if not deep_session:
        raise HTTPException(status_code=404, detail="Сессия обучения не найдена.")

    target_cid = request.concept_id or deep_session.current_concept_id
    if not target_cid and deep_session.planned_dag:
        nodes = deep_session.planned_dag.get("nodes", [])
        if nodes:
            idx = min(deep_session.current_concept_index, len(nodes) - 1)
            target_cid = nodes[idx].get("id")

    concept_res = await db.execute(select(Concept).where(Concept.id == target_cid))
    concept = concept_res.scalars().first()
    if not concept:
        raise HTTPException(status_code=404, detail="Концепция урока не найдена.")

    step_seq = (deep_session.current_concept_index or 0) + 1
    if deep_session.planned_dag and deep_session.planned_dag.get("nodes"):
        for i, n in enumerate(deep_session.planned_dag["nodes"]):
            if n.get("id") == concept.id or n.get("concept_id") == concept.id:
                step_seq = i + 1
                break

    async def event_generator():
        async with async_session_maker() as stream_db:
            try:
                s_res = await stream_db.execute(
                    select(DeepLearningSession).where(DeepLearningSession.id == request.session_id)
                )
                active_session = s_res.scalars().first()
                c_res = await stream_db.execute(select(Concept).where(Concept.id == target_cid))
                active_concept = c_res.scalars().first()
                if not active_session or not active_concept:
                    yield f"data: {json.dumps({'type': 'error', 'error': 'Session or concept not found'}, ensure_ascii=False)}\n\n"
                    return

                async for event in step_executor.stream_step(
                    session=stream_db,
                    deep_session=active_session,
                    concept=active_concept,
                    step_sequence=step_seq,
                    user_notes=request.user_notes or "",
                ):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            except Exception as e:
                logger.error(f"Error in stream_step generator: {e}", exc_info=True)
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class StreamCurriculumRequest(BaseModel):
    user_id: str
    target_concept_id: str
    initial_user_context: Optional[str] = None
    language: Optional[str] = "ru"
    depth_level: Optional[str] = None
    skip_probing: Optional[bool] = True
    session_id: Optional[str] = None


@router.post("/stream-curriculum")
async def stream_curriculum(
    request: StreamCurriculumRequest,
):
    """
    Live Server-Sent Events (SSE) streaming for course initialization & first lesson.
    Streams planning activity logs continuously (heartbeat every second), preventing HTTP idle timeouts,
    yields the planned DAG map, and seamlessly continues into live-streaming Lesson 1 tokens.
    """
    async def event_generator():
        async with async_session_maker() as db:
            try:
                yield f"data: {json.dumps({'type': 'log', 'message': 'Инициализация учебного курса...'}, ensure_ascii=False)}\n\n"

                if request.initial_user_context and request.initial_user_context.strip():
                    await moderation_service.validate_or_raise(
                        text=request.initial_user_context,
                        context={"intent": "deep_session_init", "target_concept_id": request.target_concept_id},
                    )

                log_queue = asyncio.Queue()

                async def on_plan_log(msg: str):
                    await log_queue.put(msg)

                yield f"data: {json.dumps({'type': 'log', 'message': 'Анализирую структуру курса и ключевые концепции...'}, ensure_ascii=False)}\n\n"

                session = None
                if request.session_id:
                    s_res = await db.execute(
                        select(DeepLearningSession).where(DeepLearningSession.id == request.session_id)
                    )
                    existing_session = s_res.scalars().first()
                    if existing_session:
                        existing_session.status = "planning"
                        await db.commit()
                        session = existing_session

                if session:
                    session_task = asyncio.create_task(
                        tutor_state_machine.get_next_action(
                            session=db,
                            deep_session_id=session.id,
                            user_notes=request.initial_user_context or "",
                            on_progress=on_plan_log,
                        )
                    )
                else:
                    start_req = StartDeepSessionRequest(
                        user_id=request.user_id,
                        target_concept_id=request.target_concept_id,
                        initial_user_context=request.initial_user_context,
                        language=request.language or "ru",
                        depth_level=request.depth_level,
                        skip_probing=request.skip_probing if request.skip_probing is not None else True,
                    )
                    session_task = asyncio.create_task(
                        tutor_state_machine.start_session(db, start_req, on_progress=on_plan_log)
                    )

                while not session_task.done():
                    try:
                        log_msg = await asyncio.wait_for(log_queue.get(), timeout=1.0)
                        yield f"data: {json.dumps({'type': 'log', 'message': log_msg}, ensure_ascii=False)}\n\n"
                    except asyncio.TimeoutError:
                        # Send heartbeat ping to keep HTTP / Nginx socket streaming
                        yield f"data: {json.dumps({'type': 'ping'}, ensure_ascii=False)}\n\n"

                while not log_queue.empty():
                    log_msg = log_queue.get_nowait()
                    yield f"data: {json.dumps({'type': 'log', 'message': log_msg}, ensure_ascii=False)}\n\n"

                res_obj = await session_task
                if isinstance(res_obj, dict):
                    sid = res_obj.get("session_id") or (session.id if session else "")
                    s_reload = await db.execute(select(DeepLearningSession).where(DeepLearningSession.id == sid))
                    session = s_reload.scalars().first()
                    dag_data = res_obj.get("dag") or (session.planned_dag if session else {})
                    mermaid = res_obj.get("mermaid_diagram") or (session.mermaid_diagram if session else "")
                else:
                    session = res_obj
                    dag_data = session.planned_dag
                    mermaid = session.mermaid_diagram or (dag_data or {}).get("mermaid_code", "")

                if session and session.status == "probing":
                    next_act = await tutor_state_machine.get_next_action(
                        session=db,
                        deep_session_id=session.id,
                        user_notes=request.initial_user_context or "",
                    )
                    yield f"data: {json.dumps({'type': 'probing', 'session_id': session.id, 'action': next_act}, ensure_ascii=False)}\n\n"
                    return

                # Plan is ready!
                yield f"data: {json.dumps({'type': 'plan_ready', 'session_id': session.id, 'dag': dag_data, 'mermaid_diagram': mermaid}, ensure_ascii=False)}\n\n"

                # Immediately begin streaming the active lesson in sequence
                nodes = (dag_data or {}).get("nodes", [])
                if nodes:
                    curr_idx = min(getattr(session, "current_concept_index", 0) or 0, max(0, len(nodes) - 1))
                    target_node = nodes[curr_idx]
                    target_cid = target_node.get("id") or target_node.get("concept_id")
                    c_res = await db.execute(select(Concept).where(Concept.id == target_cid))
                    active_concept = c_res.scalars().first()

                    if active_concept:
                        yield f"data: {json.dumps({'type': 'lesson_start', 'concept_id': active_concept.id, 'title': active_concept.title}, ensure_ascii=False)}\n\n"
                        async for event in step_executor.stream_step(
                            session=db,
                            deep_session=session,
                            concept=active_concept,
                            step_sequence=curr_idx + 1,
                            user_notes=request.initial_user_context or "",
                        ):
                            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            except Exception as e:
                logger.error(f"Error in stream_curriculum: {e}", exc_info=True)
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/costs")
async def get_costs_overview(
    db: AsyncSession = Depends(get_db_session),
):
    """
    Returns today's comprehensive AI expenditures, token breakdown,
    model distribution, and recent call ledger from SQLite.
    """
    try:
        return await cost_tracker.get_cost_summary(db)
    except Exception as e:
        logger.error(f"Failed to fetch costs summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))



