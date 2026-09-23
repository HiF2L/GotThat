import logging
import asyncio
import json
import re
from typing import Dict, Any, Optional, List
from openai import AsyncOpenAI
from app.config import settings

logger = logging.getLogger(__name__)


def _safe_json_loads(candidate: str) -> Optional[Any]:
    """
    Attempts strict parsing first, then repairs unescaped backslashes commonly
    introduced by LaTeX math formulas (e.g. \cdot, \sigma, \frac, \times) and retries.
    """
    if not candidate or not candidate.strip():
        return None
    try:
        return json.loads(candidate, strict=False)
    except Exception:
        pass

    # Repair invalid escape sequences: In JSON, only \" \\ \/ \b \f \n \r \t \uXXXX are valid.
    # Replace backslash not followed by valid escape chars with double backslash.
    try:
        repaired = re.sub(r'\\([^"\\/bfnrtu])', r'\\\\\1', candidate)
        return json.loads(repaired, strict=False)
    except Exception:
        pass
    return None


def extract_json_or_fallback(content: str) -> Dict[str, Any]:
    """
    Robust extractor for JSON responses from LLMs, handling markdown code blocks,
    preceding conversational filler, trailing reasoning, and unescaped LaTeX backslashes.
    """
    if not content or not content.strip():
        return {}

    cleaned = content.strip()

    # 1. Direct standard parse
    res = _safe_json_loads(cleaned)
    if isinstance(res, dict):
        return res
    if isinstance(res, list):
        return {"items": res}

    # 2. Extract from ```json ... ``` or ``` ... ```
    json_block = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if json_block:
        res = _safe_json_loads(json_block.group(1).strip())
        if isinstance(res, dict):
            return res
        if isinstance(res, list):
            return {"items": res}

    # 3. Find outermost curly braces { ... }
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        json_candidate = cleaned[first_brace : last_brace + 1]
        res = _safe_json_loads(json_candidate)
        if isinstance(res, dict):
            return res
        if isinstance(res, list):
            return {"items": res}

    # 4. JSON array match [ ... ]
    first_bracket = cleaned.find("[")
    last_bracket = cleaned.rfind("]")
    if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
        json_candidate = cleaned[first_bracket : last_bracket + 1]
        res = _safe_json_loads(json_candidate)
        if isinstance(res, list):
            return {"items": res}
        if isinstance(res, dict):
            return res

    # 5. Regex salvage for explanation_markdown if JSON was truncated
    exp_match = re.search(r'"explanation(?:_markdown)?"\s*:\s*"((?:[^"\\]|\\.)*)', cleaned)
    if exp_match:
        raw_val = exp_match.group(1)
        val = raw_val.replace('\\"', '"').replace('\\n', '\n').replace('\\t', '\t').replace('\\\\', '\\')
        return {"explanation_markdown": val}

    logger.warning("Failed to parse JSON from response; returning fallback wrapper.")
    return {"raw_text": cleaned}


def sanitize_markdown_text(text: str) -> str:
    """
    Guarantees that a markdown text payload is never inadvertently a raw JSON string
    or escaped JSON dump. Extracts 'explanation_markdown' or 'explanation' if wrapped in JSON.
    """
    if not text:
        return ""

    cleaned = text.strip()
    if (cleaned.startswith("{") or cleaned.startswith("```json") or cleaned.startswith("```")) and (
        '"explanation_markdown"' in cleaned or '"explanation"' in cleaned
    ):
        parsed = extract_json_or_fallback(cleaned)
        if isinstance(parsed, dict):
            if parsed.get("explanation_markdown"):
                cleaned = str(parsed["explanation_markdown"]).strip()
            elif parsed.get("explanation"):
                cleaned = str(parsed["explanation"]).strip()

    if cleaned.startswith("{") and ('"explanation_markdown"' in cleaned or '"explanation"' in cleaned):
        exp_match = re.search(r'"explanation(?:_markdown)?"\s*:\s*"((?:[^"\\]|\\.)*)', cleaned)
        if exp_match:
            raw_val = exp_match.group(1)
            cleaned = raw_val.replace('\\"', '"').replace('\\n', '\n').replace('\\t', '\t').replace('\\\\', '\\').strip()

    if "\\n" in cleaned and "\n" not in cleaned:
        cleaned = cleaned.replace("\\n", "\n")

    return cleaned


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
        or user settings into exact ProxyAPI provider identifiers.
        """
        if not model_name:
            return "openai/gpt-4.1-mini"

        clean = model_name.strip().lower()

        # 1. Normalize separator characters (spaces/underscores to hyphens)
        clean = clean.replace(" ", "-").replace("_", "-")

        # 2. Normalize common phonetic / typographical suffix variations (e.g. 'flash-light' -> 'flash-lite')
        clean = re.sub(r"-(?:light)\b", "-lite", clean)
        clean = re.sub(r"\b(?:light)\b", "lite", clean)

        # 3. Normalize vendor prefix variations (e.g. 'moonshot-ai/' -> 'moonshotai/')
        clean = clean.replace("moonshot-ai/", "moonshotai/")

        # 4. Check if already has a valid vendor namespace
        valid_vendors = ("google/", "openai/", "deepseek/", "anthropic/", "moonshotai/", "qwen/", "x-ai/", "meta/")
        if any(clean.startswith(v) for v in valid_vendors):
            return clean

        # 5. Strip any extraneous leading slash
        clean = clean.lstrip("/")


        # 4. Canonical shorthand mappings
        shorthands = {
            "kimi": "moonshotai/kimi-k3",
            "kimi-k3": "moonshotai/kimi-k3",
            "k3": "moonshotai/kimi-k3",
            "moonshot": "moonshotai/kimi-k3",
            "claude": "anthropic/claude-sonnet-4-5",
            "sonnet": "anthropic/claude-sonnet-4-5",
            "claude-sonnet": "anthropic/claude-sonnet-4-5",
            "claude-sonnet-4-5": "anthropic/claude-sonnet-4-5",
            "claude-sonnet-5": "anthropic/claude-sonnet-5",
            "opus": "anthropic/claude-opus-4-1",
            "claude-opus": "anthropic/claude-opus-4-1",
            "deepseek": "deepseek/deepseek-chat",
            "deepseek-chat": "deepseek/deepseek-chat",
            "deepseek-v3": "deepseek/deepseek-chat",
            "deepseek-pro": "deepseek/deepseek-v4-pro",
            "deepseek-v4-pro": "deepseek/deepseek-v4-pro",
            "deepseek-flash": "deepseek/deepseek-v4-flash",
            "deepseek-v4-flash": "deepseek/deepseek-v4-flash",
            "deepseek-r1": "deepseek/deepseek-r1",
            "gpt": "openai/gpt-4.1-mini",
            "gpt-mini": "openai/gpt-4.1-mini",
            "gpt-4.1-mini": "openai/gpt-4.1-mini",
            "gpt-4.1": "openai/gpt-4.1",
            "gpt-4o-mini": "openai/gpt-4.1-mini",
            "gemini": "google/gemini-2.5-flash",
            "gemini-flash": "google/gemini-2.5-flash",
            "gemini-2.5-flash": "google/gemini-2.5-flash",
            "gemini-2.5-flash-lite": "google/gemini-2.5-flash-lite",
            "gemini-2.5-pro": "google/gemini-2.5-pro",
            "gemini-3-flash": "google/gemini-3-flash-preview",
            "gemini-3-flash-preview": "google/gemini-3-flash-preview",
            "gemini-3.1-pro-preview": "google/gemini-3.1-pro-preview",
            "gemini-3.1-flash-lite": "google/gemini-3.1-flash-lite",
            "qwen": "qwen/qwen3.7-max",
            "qwen-max": "qwen/qwen3.7-max",
            "qwen3.7-max": "qwen/qwen3.7-max",
        }
        if clean in shorthands:
            return shorthands[clean]

        # 5. Dynamic vendor prefix inference
        if clean.startswith("gemini"):
            return f"google/{clean}"
        if clean.startswith("deepseek"):
            return f"deepseek/{clean}"
        if clean.startswith(("gpt-", "o1-", "o3-", "o4-")):
            return f"openai/{clean}"
        if clean.startswith("claude-"):
            return f"anthropic/{clean}"
        if clean.startswith("kimi-"):
            return f"moonshotai/{clean}"
        if clean.startswith("qwen"):
            return f"qwen/{clean}"

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

        # Primary model is attempted first with full allowance
        candidate_models = [chosen_model]
        # Fast, proven fallback models if primary model times out
        for fb in ["google/gemini-2.5-flash", "google/gemini-3-flash-preview", "openai/gpt-4.1-mini"]:
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
