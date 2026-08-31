import io
import logging
from typing import Dict, Any, Optional
from app.config import settings
from app.services.ai.client import ai_clients
from app.schemas.feed import VoiceReasoningAnalysis

logger = logging.getLogger(__name__)


class STTService:
    """
    Handles audio transcription via ProxyAPI (STT_BASE_URL)
    and cognitive extraction of student reasoning via LLM.
    """

    async def transcribe_audio(self, audio_bytes: bytes, filename: str = "audio.wav") -> str:
        # Normalize filename extension for OpenAI API (e.g. webm, wav, mp3)
        ext = filename.split(".")[-1].lower() if "." in filename else "wav"
        if ext not in ["wav", "webm", "mp3", "m4a", "ogg"]:
            ext = "webm"
        safe_name = f"recording.{ext}"

        for model_candidate in ["whisper-1", settings.STT_MODEL]:
            try:
                audio_file = io.BytesIO(audio_bytes)
                audio_file.name = safe_name
                transcript_response = await ai_clients.stt_client.audio.transcriptions.create(
                    model=model_candidate,
                    file=audio_file,
                )
                if transcript_response.text:
                    clean_text = transcript_response.text.strip()
                    # Filter out common Whisper hallucination tokens on pure background noise/silence
                    if clean_text.lower() in ["you", "thank you", "thanks for watching!", ".", "...", "bye"]:
                        return ""
                    return clean_text
            except Exception as e:
                logger.warning(f"STT model {model_candidate} error: {e}")
                continue

        return ""

    async def analyze_reasoning(
        self,
        transcript: str,
        question_prompt: str,
        correct_answer_summary: str,
        concept_title: str,
    ) -> VoiceReasoningAnalysis:
        """
        Parses student spoken thoughts ('thinking out loud') to evaluate whether they truly
        understand the underlying mechanism or are just guessing/making fallacies.
        """
        system_prompt = (
            "You are an expert cognitive evaluator and epistemics assessor. "
            "Your job is to analyze a student's verbal reasoning ('thinking out loud') for a quiz question. "
            "Determine if their internal mental model is genuinely sound, or if they have specific misconceptions, "
            "or are guessing without causal understanding.\n\n"
            "Return JSON matching this exact structure:\n"
            "{\n"
            '  "logical_coherence_score": float (0.0 to 1.0),\n'
            '  "demonstrated_understanding": ["key concept 1", "key intuition 2"],\n'
            '  "misconceptions_detected": ["misconception name if any"],\n'
            '  "reasoning_summary": "Brief 1-2 sentence assessment of student thought process",\n'
            '  "speech_hesitation_detected": boolean,\n'
            '  "is_genuine_understanding": boolean\n'
            "}"
        )

        user_content = (
            f"Concept: {concept_title}\n"
            f"Question Prompt: {question_prompt}\n"
            f"Target Knowledge: {correct_answer_summary}\n"
            f"Student Spoken Transcript: \"{transcript}\"\n\n"
            "Analyze the student's reasoning carefully."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        result = await ai_clients.generate_json(
            messages=messages,
            model=settings.FAST_MODEL,
            temperature=0.1,
        )

        return VoiceReasoningAnalysis(
            logical_coherence_score=float(result.get("logical_coherence_score", 0.7)),
            demonstrated_understanding=result.get("demonstrated_understanding", []),
            misconceptions_detected=result.get("misconceptions_detected", []),
            reasoning_summary=result.get("reasoning_summary", "Analyzed student reasoning."),
            speech_hesitation_detected=bool(result.get("speech_hesitation_detected", False)),
            is_genuine_understanding=bool(result.get("is_genuine_understanding", True)),
        )


stt_service = STTService()
