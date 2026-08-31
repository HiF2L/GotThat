import logging
import asyncio
import json
import re
from typing import Dict, Any, Optional, List
from openai import AsyncOpenAI
from app.config import settings

logger = logging.getLogger(__name__)


def extract_json_or_fallback(content: str) -> Dict[str, Any]:
    """
    Robust extractor for JSON responses from LLMs, handling markdown code blocks,
    preceding conversational filler, and trailing reasoning.
    """
    if not content or not content.strip():
        return {}

    cleaned = content.strip()

    # 1. Direct standard parse
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    # 2. Extract from ```json ... ``` or ``` ... ```
    json_block = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if json_block:
        try:
            return json.loads(json_block.group(1).strip())
        except Exception:
            pass

    # 3. Find outermost curly braces { ... }
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        json_candidate = cleaned[first_brace : last_brace + 1]
        try:
            return json.loads(json_candidate)
        except Exception:
            pass

    # 4. JSON array match [ ... ]
    first_bracket = cleaned.find("[")
    last_bracket = cleaned.rfind("]")
    if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
        json_candidate = cleaned[first_bracket : last_bracket + 1]
        try:
            res = json.loads(json_candidate)
            return {"items": res} if isinstance(res, list) else res
        except Exception:
            pass

    logger.warning("Failed to parse JSON from response; returning fallback wrapper.")
    return {"raw_text": cleaned}


class AIClientManager:
    """
    Unified AI Gateway Manager for the GotIt educational ecosystem.
    Communicates via OpenAI-compatible endpoints with resilient multi-tier fallback,
    adaptive timeouts (waiting up to 100s for deep models before graceful fallback),
    reasoning content extraction, and automatic model normalization.
    """

    def __init__(self):
        self.main_client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY or "dummy_openai_key",
            base_url=settings.OPENAI_BASE_URL,
            timeout=120.0,
        )
        self.stt_client = AsyncOpenAI(
            api_key=settings.STT_API_KEY or "dummy_stt_key",
            base_url=settings.STT_BASE_URL,
            timeout=60.0,
        )
        self.tts_client = AsyncOpenAI(
            api_key=settings.TTS_API_KEY or "dummy_tts_key",
            base_url=settings.TTS_BASE_URL,
            timeout=60.0,
        )

    def normalize_model_name(self, model_name: str) -> str:
        """
        Translates human-readable model aliases, namespace prefixes, typos,
        or user settings into exact provider identifiers.
        """
        if not model_name:
            return "kimi-k3"

        clean = model_name.strip().lower()

        # 1. Strip namespace prefixes (e.g. 'google/gemini-3.1-flash-lite' -> 'gemini-3.1-flash-lite')
        if "/" in clean:
            clean = clean.split("/")[-1]

        # 2. Normalize separator characters (underscores to hyphens)
        clean = clean.replace("_", "-")

        # 3. Normalize common phonetic / typographical suffix variations (e.g. 'flash-light' -> 'flash-lite')
        clean = re.sub(r"-(?:light)\b", "-lite", clean)
        clean = re.sub(r"\b(?:light)\b", "lite", clean)

        # 4. Exact matches from provider model catalog
        exact_provod_models = [
            "kimi-k3",
            "deepseek-v4-pro",
            "deepseek-v4-flash",
            "gemini-3-flash-preview",
            "gemini-3.1-pro-preview",
            "gemini-3.1-flash-lite",
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "claude-opus-4.6",
            "claude-sonnet-5",
            "gpt-5.4-pro",
            "gpt-5.4",
            "gpt-5.4-mini",
            "qwen3.7-max",
        ]
        if clean in exact_provod_models:
            return clean

        # 5. Generic model family & shorthand aliases
        mapping = {
            "kimi": "kimi-k3",
            "moonshot": "kimi-k3",
            "k3": "kimi-k3",
            "claude": "claude-sonnet-5",
            "sonnet": "claude-sonnet-5",
            "opus": "claude-opus-4.6",
            "claude-opus": "claude-opus-4.6",
            "claude-sonnet": "claude-sonnet-5",
            "deepseek": "deepseek-v4-pro",
            "deepseek-pro": "deepseek-v4-pro",
            "deepseek-v4": "deepseek-v4-pro",
            "deepseek-flash": "deepseek-v4-flash",
            "gpt": "gpt-5.4",
            "gpt-5": "gpt-5.4",
            "gpt-5-mini": "gpt-5.4-mini",
            "gemini": "gemini-3-flash-preview",
            "gemini-flash": "gemini-3-flash-preview",
            "gemini-3-flash": "gemini-3-flash-preview",
            "gemini-pro": "gemini-3.1-pro-preview",
            "gemini-3.1-pro": "gemini-3.1-pro-preview",
            "gemini-lite": "gemini-3.1-flash-lite",
            "gemini-flash-lite": "gemini-3.1-flash-lite",
            "flash-lite": "gemini-3.1-flash-lite",
            "qwen": "qwen3.7-max",
            "qwen-max": "qwen3.7-max",
        }
        if clean in mapping:
            return mapping[clean]

        return clean

    async def generate_chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.3,
        response_format: Optional[Dict[str, str]] = None,
        max_tokens: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
    ) -> str:
        raw_model = model or settings.FAST_MODEL
        chosen_model = self.normalize_model_name(raw_model)

        # Primary model is attempted first with full 100s allowance
        candidate_models = [chosen_model]
        # Fast, proven fallback models if primary model times out after 100s
        for fb in ["gemini-3-flash-preview", "gemini-3.1-flash-lite"]:
            if fb not in candidate_models:
                candidate_models.append(fb)

        last_error = None
        for idx, candidate in enumerate(candidate_models):
            # Primary model gets 100s (or caller timeout); fallbacks get 30s
            call_timeout = (timeout_seconds or 100.0) if idx == 0 else 30.0

            try:
                kwargs: Dict[str, Any] = {
                    "model": candidate,
                    "messages": messages,
                    "temperature": temperature,
                }
                if response_format:
                    kwargs["response_format"] = response_format
                if max_tokens:
                    kwargs["max_tokens"] = max_tokens

                response = await asyncio.wait_for(
                    self.main_client.chat.completions.create(**kwargs),
                    timeout=call_timeout,
                )
                choices = getattr(response, "choices", [])
                if not choices or not choices[0].message:
                    raise ValueError(f"Model '{candidate}' returned empty choices")

                msg = choices[0].message
                content = (getattr(msg, "content", None) or "").strip()
                
                # If content is empty but model produced reasoning_content (e.g. DeepSeek/o1)
                if not content and hasattr(msg, "reasoning_content") and getattr(msg, "reasoning_content", None):
                    content = str(msg.reasoning_content).strip()

                if not content:
                    raise ValueError(f"Model '{candidate}' returned empty content")

                return content
            except Exception as e:
                last_error = e
                logger.warning(
                    f"Model '{candidate}' call failed after {call_timeout}s timeout: {e}. Trying next candidate..."
                )
                continue

        logger.error(f"All AI client fallback models failed. Last error: {last_error}")
        raise RuntimeError(f"AI Generation failed across all fallback models: {last_error}")

    async def generate_json(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Guaranteed JSON extraction from LLM responses with prompt instructions and robust fallback.
        """
        chosen_model = model or settings.FAST_MODEL
        content = await self.generate_chat(
            messages=messages,
            model=chosen_model,
            temperature=temperature,
            max_tokens=max_tokens or 8192,
            timeout_seconds=timeout_seconds,
        )
        parsed = extract_json_or_fallback(content)
        if "raw_text" in parsed and len(parsed) == 1:
            try:
                repair_content = await self.generate_chat(
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a JSON repair formatter. Output valid JSON object with keys matching input structure. Return ONLY valid JSON.",
                        },
                        {"role": "user", "content": content},
                    ],
                    model="gemini-3-flash-preview",
                    temperature=0.0,
                    timeout_seconds=30.0,
                )
                repaired = extract_json_or_fallback(repair_content)
                if repaired and "raw_text" not in repaired:
                    return repaired
            except Exception as e:
                logger.warning(f"JSON repair failed: {e}")
        return parsed


ai_clients = AIClientManager()
