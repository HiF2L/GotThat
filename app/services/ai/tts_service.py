import logging
import asyncio
import hashlib
import re
from typing import Dict, Any, Optional, List
from collections import OrderedDict
from app.config import settings
from app.services.ai.client import ai_clients, extract_json_or_fallback

logger = logging.getLogger(__name__)

# LaTeX symbol phonetization map for natural speech
LATEX_PHONETIC_REPLACEMENTS = [
    (r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"\1, делённое на \2"),
    (r"\\sqrt\{([^{}]+)\}", r"квадратный корень из \1"),
    (r"\\Delta", "дельта"),
    (r"\\delta", "дельта"),
    (r"\\alpha", "альфа"),
    (r"\\beta", "бета"),
    (r"\\gamma", "гамма"),
    (r"\\pi", "пи"),
    (r"\\theta", "тета"),
    (r"\\sigma", "сигма"),
    (r"\\lambda", "лямбда"),
    (r"\\mu", "мю"),
    (r"\\omega", "омега"),
    (r"\\approx", " приблизительно равно "),
    (r"\\neq", " не равно "),
    (r"\\leq", " меньше или равно "),
    (r"\\geq", " больше или равно "),
    (r"\\times", " умножить на "),
    (r"\\cdot", " умножить на "),
    (r"\\pm", " плюс-минус "),
    (r"\\infty", "бесконечность"),
    (r"\\log_2", "двоичный логарифм"),
    (r"\\ln", "натуральный логарифм"),
    (r"\\log", "логарифм"),
    (r"\^2\b", " в квадрате"),
    (r"\^3\b", " в кубе"),
    (r"\^\{([^{}]+)\}", r" в степени \1"),
    (r"_\{([^{}]+)\}", r" с индексом \1"),
    (r"_([a-zA-Z0-9])", r" с индексом \1"),
]


def clean_markdown_for_speech(content: str) -> str:
    """
    Transforms raw educational Markdown with LaTeX, links, and formatting
    into clean, natural, expressive conversational text for TTS synthesis.
    
    IMPORTANT RULES:
    1. Text inside parentheses (like examples, clarifications, translations) MUST BE PRESERVED.
    2. Code blocks and raw technical syntax are gracefully converted or announced.
    3. LaTeX formulas are phonetically translated into readable speech.
    4. Image tags, markdown links, HTML wrappers, and formatting tokens are stripped.
    """
    if not content or not content.strip():
        return ""

    text = content.strip()

    # 1. If payload was wrapped in a JSON block, extract explanation text
    if (text.startswith("{") or text.startswith("```json")) and '"explanation' in text:
        try:
            parsed = extract_json_or_fallback(text)
            if isinstance(parsed, dict):
                text = parsed.get("explanation_markdown") or parsed.get("explanation") or text
        except Exception:
            pass

    # 2. Strip outer markdown container fences (e.g. ```markdown ... ``` or ``` ... ```)
    outer_fence_match = re.match(r"^```(?:markdown|md|text)?\s*\n([\s\S]*?)\n?```$", text, re.IGNORECASE)
    if outer_fence_match:
        text = outer_fence_match.group(1).strip()

    # 3. Strip HTML tags completely (figures, svgs, custom divs, buttons)
    text = re.sub(r"<figure[\s\S]*?</figure>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<svg[\s\S]*?</svg>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<div[\s\S]*?</div>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)

    # 4. Strip Markdown images ![alt](url)
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    text = re.sub(r"!\[.*?\]\[.*?\]", "", text)

    # 5. Convert Markdown links [Title](url) -> Title
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)

    # 6. Handle code blocks: convert fences to natural pauses without swallowing content
    text = re.sub(r"```[a-zA-Z0-9_\-]*\n", "\nПример кода:\n", text)
    text = re.sub(r"```", "\n", text)
    # Inline code ticks: `variable` -> variable
    text = re.sub(r"`([^`]+)`", r"\1", text)

    # 7. Phonetically translate LaTeX Block & Inline Math
    def _clean_math(match: re.Match) -> str:
        raw_m = match.group(1).strip()
        cleaned_m = raw_m
        for pattern, repl in LATEX_PHONETIC_REPLACEMENTS:
            cleaned_m = re.sub(pattern, repl, cleaned_m)
        # Remove leftover backslashes and braces
        cleaned_m = cleaned_m.replace("\\", " ").replace("{", " ").replace("}", " ")
        cleaned_m = re.sub(r"\s+", " ", cleaned_m).strip()
        return f" {cleaned_m} "

    text = re.sub(r"\$\$([\s\S]*?)\$\$", _clean_math, text)
    text = re.sub(r"(?<!\\)\$([^\$\n]+?)(?<!\\)\$", _clean_math, text)

    # 8. Extra LaTeX tag cleanups: \text{...}, \textbf{...}, \left, \right, etc.
    text = re.sub(r"\\(?:text|textbf|mathbf|mathrm|mathit)\{([^{}]+)\}", r"\1", text)
    text = re.sub(r"\\(?:left|right|big|Big|bigg|Bigg)", "", text)
    text = re.sub(r"\\[a-zA-Z]+", " ", text)

    # 9. Remove markdown headers (#, ##, ###, ####)
    text = re.sub(r"^[#]+\s*(.*?)$", r"\1.", text, flags=re.MULTILINE)

    # 10. Clean list item bullets (*, -, +, 1., 2.) into clean pauses
    text = re.sub(r"^\s*[\*\-\+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*(\d+)\.\s+", r"\1. ", text, flags=re.MULTILINE)

    # 11. Remove bold / italic markers (**text**, *text*, __text__, _text_) while PRESERVING text & parentheses
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"(?<!\w)\*([^*]+)\*(?!\w)", r"\1", text)
    text = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"\1", text)

    # 12. Remove blockquote markers >
    text = re.sub(r"^\s*>\s*", "", text, flags=re.MULTILINE)

    # 13. CRITICAL: Strip all technical symbols that TTS reads aloud!
    # - Backslash \ -> space (fixes "наклонная черта влево")
    # - Forward slash / -> space (fixes "наклонная черта вправо")
    # - Braces {}, brackets [], angle brackets <>, pipe |, tilde ~, caret ^, at @, hash #, ampersand &, underscore _, dollar $
    # Note: Keep parentheses () intact for natural spoken explanations!
    text = text.replace("\\", " ")
    text = text.replace("$", " ")
    text = re.sub(r"[{}\[\]|~^@#&_`<>=\+*]", " ", text)
    text = re.sub(r"\s*/\s*", " ", text)

    # Clean double quotes and single quotes if used as syntax delimiters
    text = text.replace('"', ' ').replace("'", ' ').replace("`", " ")

    # 14. Normalize duplicate punctuation, pauses, and whitespace
    # Remove emoji symbols if they cause TTS noise, but keep letters/numbers/punctuation/parentheses
    text = re.sub(r"[\U00010000-\U0010ffff]", "", text)
    # Normalize multiple newlines to clean sentence breaks
    text = re.sub(r"\n+", ". ", text)
    text = re.sub(r"\s*([.,!?:;])\s*", r"\1 ", text)
    # Collapse multiple dots into single period
    text = re.sub(r"\.{2,}", ".", text)
    # Normalize multiple spaces
    text = re.sub(r"[ \t]+", " ", text).strip()

    return text


try:
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False

VOICE_MAP = {
    # Russian Studio Neural Voices
    "svetlana": "ru-RU-SvetlanaNeural",
    "ru-ru-svetlananeural": "ru-RU-SvetlanaNeural",
    "dmitry": "ru-RU-DmitryNeural",
    "dmitri": "ru-RU-DmitryNeural",
    "ru-ru-dmitryneural": "ru-RU-DmitryNeural",

    # English Studio Neural Voices
    "jenny": "en-US-JennyNeural",
    "en-us-jennyneural": "en-US-JennyNeural",
    "guy": "en-US-GuyNeural",
    "en-us-guyneural": "en-US-GuyNeural",
    "aria": "en-US-AriaNeural",
    "en-us-arianeural": "en-US-AriaNeural",
    "sonia": "en-GB-SoniaNeural",
    "en-gb-sonianeural": "en-GB-SoniaNeural",

    # OpenAI Legacy Aliases mapped to Neural Voices
    "alloy": "ru-RU-SvetlanaNeural",
    "nova": "ru-RU-SvetlanaNeural",
    "shimmer": "ru-RU-SvetlanaNeural",
    "echo": "ru-RU-DmitryNeural",
    "onyx": "ru-RU-DmitryNeural",
    "fable": "en-GB-SoniaNeural",
}


class TTSService:
    """
    Dedicated Text-to-Speech service using high-quality Neural Voices (Edge-TTS / ProxyAPI).
    Features:
    - Zero API cost and minimal RAM footprint (<10MB), ideal for 2GB RAM VPS servers.
    - Studio Azure Neural voice quality with natural intonations and speed adjustment.
    - First-principles markdown-to-speech phonetic normalizer (preserving parentheses).
    - In-memory LRU audio caching for 0ms replay latency.
    """

    def __init__(self, max_cache_size: int = 100):
        self._cache: OrderedDict[str, bytes] = OrderedDict()
        self._max_cache_size = max_cache_size
        self._lock = asyncio.Lock()

    def resolve_voice(self, voice: Optional[str]) -> str:
        if not voice or not voice.strip():
            return settings.TTS_VOICE or "ru-RU-SvetlanaNeural"
        clean = voice.strip().lower()
        return VOICE_MAP.get(clean, voice.strip())

    def _get_cache_key(self, text: str, voice: str, speed: float) -> str:
        raw = f"{voice}:{speed:.2f}:{text}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def chunk_text(self, text: str, max_chars: int = 3500) -> List[str]:
        """
        Splits text into coherent chunks without breaking sentences or words.
        """
        if len(text) <= max_chars:
            return [text]

        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks = []
        current_chunk = []
        current_len = 0

        for sentence in sentences:
            s_clean = sentence.strip()
            if not s_clean:
                continue

            if current_len + len(s_clean) + 1 > max_chars and current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = [s_clean]
                current_len = len(s_clean)
            else:
                current_chunk.append(s_clean)
                current_len += len(s_clean) + 1

        if current_chunk:
            chunks.append(" ".join(current_chunk))

        return chunks if chunks else [text]

    async def _synthesize_edge_tts(self, text: str, voice: str, speed: float) -> bytes:
        if not HAS_EDGE_TTS:
            raise RuntimeError("edge_tts is not installed")

        pct = int((speed - 1.0) * 100)
        rate_str = f"{pct:+d}%" if pct != 0 else "+0%"

        communicate = edge_tts.Communicate(text, voice=voice, rate=rate_str)
        audio_bytes = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_bytes += chunk["data"]

        if not audio_bytes:
            raise RuntimeError("Edge-TTS produced 0 bytes")
        return audio_bytes

    async def synthesize_speech(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: float = 1.0,
    ) -> bytes:
        """
        Synthesizes speech from markdown text using high-quality Neural Voices.
        Returns binary MP3 audio bytes.
        """
        clean_text = clean_markdown_for_speech(text)
        if not clean_text:
            return b""

        effective_voice = self.resolve_voice(voice)
        effective_speed = max(0.5, min(2.0, speed))

        cache_key = self._get_cache_key(clean_text, effective_voice, effective_speed)

        async with self._lock:
            if cache_key in self._cache:
                self._cache.move_to_end(cache_key)
                return self._cache[cache_key]

        chunks = self.chunk_text(clean_text, max_chars=3500)
        audio_segments: List[bytes] = []

        for chunk in chunks:
            chunk_success = False
            last_err = None

            # 1. Primary: High-Quality Zero-Cost Neural Voices via Edge-TTS (<10MB RAM)
            if HAS_EDGE_TTS:
                try:
                    audio_bytes = await self._synthesize_edge_tts(chunk, effective_voice, effective_speed)
                    if audio_bytes and len(audio_bytes) > 100:
                        audio_segments.append(audio_bytes)
                        chunk_success = True
                except Exception as e:
                    last_err = e
                    logger.warning(f"Edge-TTS synthesis error: {e}. Falling back to ProxyAPI...")

            # 2. Fallback: ProxyAPI OpenAI-compatible endpoint
            if not chunk_success:
                openai_voice = "alloy"
                for o_name in ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]:
                    if o_name in (voice or "").lower():
                        openai_voice = o_name
                        break

                for model_name in [settings.TTS_MODEL, "tts-1"]:
                    try:
                        response = await ai_clients.tts_client.audio.speech.create(
                            model=model_name,
                            voice=openai_voice,
                            input=chunk,
                            response_format="mp3",
                            speed=effective_speed,
                        )
                        audio_bytes = response.content if hasattr(response, "content") else await response.aread()
                        if audio_bytes and len(audio_bytes) > 100:
                            audio_segments.append(audio_bytes)
                            chunk_success = True
                            break
                    except Exception as e:
                        last_err = e
                        logger.warning(f"Fallback ProxyAPI TTS failed: {e}")
                        continue

            if not chunk_success:
                logger.error(f"All TTS synthesis engines failed for chunk: {last_err}")
                raise RuntimeError(f"Failed to synthesize speech audio: {last_err}")

        # Combine all audio chunks
        full_audio = b"".join(audio_segments)

        # Store in LRU cache
        async with self._lock:
            if len(self._cache) >= self._max_cache_size:
                self._cache.popitem(last=False)
            self._cache[cache_key] = full_audio

        return full_audio


tts_service = TTSService()

