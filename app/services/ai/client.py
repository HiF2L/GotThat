import logging
import asyncio
import json
import re
import time
from typing import Dict, Any, Optional, List, AsyncGenerator
from openai import AsyncOpenAI
from app.config import settings
from app.services.ai.cost_tracker import cost_tracker

logger = logging.getLogger(__name__)


def _safe_int(val: Any, default: int = 0) -> int:
    if isinstance(val, int) and not isinstance(val, bool):
        return val
    try:
        if isinstance(val, (float, str)):
            return int(val)
    except Exception:
        pass
    return default


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

    def _prepare_kwargs(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = 0.3,
        response_format: Optional[Dict[str, str]] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
    ) -> Dict[str, Any]:
        """
        Dynamically adjusts kwargs according to model capabilities and ProxyAPI quirks:
        - moonshotai/kimi-k3 rejects custom temperature (HTTP 400).
        - o1/o3 reasoning models reject temperature and require max_completion_tokens.
        - stream_options: includes token usage in the final stream chunk.
        """
        clean_model = self.normalize_model_name(model)
        kwargs: Dict[str, Any] = {
            "model": clean_model,
            "messages": messages,
        }

        # Temperature handling
        is_kimi = "kimi" in clean_model
        is_reasoning_o_series = any(p in clean_model for p in ["/o1", "/o3", "/o4", "o1-", "o3-"])

        if not is_kimi and not is_reasoning_o_series and temperature is not None:
            kwargs["temperature"] = temperature

        # Token limits
        if max_tokens:
            if is_reasoning_o_series:
                kwargs["max_completion_tokens"] = max_tokens
            else:
                kwargs["max_tokens"] = max_tokens

        if response_format:
            kwargs["response_format"] = response_format

        if stream:
            kwargs["stream"] = True
            kwargs["stream_options"] = {"include_usage": True}

        return kwargs

    async def generate_chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.3,
        response_format: Optional[Dict[str, str]] = None,
        max_tokens: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
        task_type: str = "general_chat",
    ) -> str:
        raw_model = model or settings.FAST_MODEL
        chosen_model = self.normalize_model_name(raw_model)

        # Allow generous timeout for primary model (up to 120s for reasoning/deep models)
        call_timeout = timeout_seconds or 120.0
        start_time = time.time()

        try:
            kwargs = self._prepare_kwargs(
                model=chosen_model,
                messages=messages,
                temperature=temperature,
                response_format=response_format,
                max_tokens=max_tokens,
            )

            response = await asyncio.wait_for(
                self.main_client.chat.completions.create(**kwargs),
                timeout=call_timeout,
            )

            latency_ms = int((time.time() - start_time) * 1000)
            choices = getattr(response, "choices", [])
            if not choices or not choices[0].message:
                raise ValueError(f"Model '{chosen_model}' returned empty choices")

            msg = choices[0].message
            content = (getattr(msg, "content", None) or "").strip()

            # If content is empty but model produced reasoning_content (e.g. DeepSeek/o1)
            if not content and hasattr(msg, "reasoning_content") and getattr(msg, "reasoning_content", None):
                content = str(msg.reasoning_content).strip()

            if not content:
                raise ValueError(f"Model '{chosen_model}' returned empty content")

            # Extract usage metrics
            usage = getattr(response, "usage", None)
            prompt_tokens = _safe_int(getattr(usage, "prompt_tokens", 0) if usage else 0)
            completion_tokens = _safe_int(getattr(usage, "completion_tokens", 0) if usage else 0)
            reasoning_tokens = 0
            if usage and hasattr(usage, "completion_tokens_details"):
                details = getattr(usage, "completion_tokens_details", None)
                if details:
                    reasoning_tokens = _safe_int(getattr(details, "reasoning_tokens", 0))

            # Record cost and tokens
            await cost_tracker.record_usage(
                task_type=task_type,
                model=chosen_model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                reasoning_tokens=reasoning_tokens,
                latency_ms=latency_ms,
                status="success",
            )

            return content

        except asyncio.TimeoutError:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.warning(f"[TIMEOUT] Primary model '{chosen_model}' timed out after {call_timeout}s. Recording and trying safe fallback...")
            await cost_tracker.record_usage(
                task_type=task_type,
                model=chosen_model,
                prompt_tokens=0,
                completion_tokens=0,
                latency_ms=latency_ms,
                status="timeout",
                error_message=f"Timeout after {call_timeout}s",
            )
            # Try single safe fast fallback so request does not fail
            fallback_model = self.normalize_model_name(settings.FAST_MODEL)
            if fallback_model != chosen_model:
                try:
                    fb_start = time.time()
                    fb_kwargs = self._prepare_kwargs(
                        model=fallback_model,
                        messages=messages,
                        temperature=temperature,
                        response_format=response_format,
                        max_tokens=max_tokens,
                    )
                    fb_resp = await asyncio.wait_for(
                        self.main_client.chat.completions.create(**fb_kwargs),
                        timeout=45.0,
                    )
                    fb_latency = int((time.time() - fb_start) * 1000)
                    fb_choices = getattr(fb_resp, "choices", [])
                    if fb_choices and fb_choices[0].message:
                        fb_content = (getattr(fb_choices[0].message, "content", None) or "").strip()
                        if fb_content:
                            usage = getattr(fb_resp, "usage", None)
                            prompt_tokens = _safe_int(getattr(usage, "prompt_tokens", 0) if usage else 0)
                            completion_tokens = _safe_int(getattr(usage, "completion_tokens", 0) if usage else 0)
                            await cost_tracker.record_usage(
                                task_type=f"{task_type}_fallback",
                                model=fallback_model,
                                prompt_tokens=prompt_tokens,
                                completion_tokens=completion_tokens,
                                latency_ms=fb_latency,
                                status="success",
                                details={"primary_model_timed_out": chosen_model, "timeout_sec": call_timeout},
                            )
                            return fb_content
                except Exception as fb_err:
                    logger.error(f"Fallback model '{fallback_model}' after timeout also failed: {fb_err}")
            raise TimeoutError(f"Model '{chosen_model}' timed out after {call_timeout}s")

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            error_str = str(e)
            logger.warning(f"Primary model '{chosen_model}' failed ({e}). Checking single safe fallback...")

            # If it was an invalid request or connection error on primary, try AT MOST ONE cheap fallback
            fallback_model = self.normalize_model_name(settings.FAST_MODEL)
            if fallback_model != chosen_model:
                try:
                    fb_start = time.time()
                    fb_kwargs = self._prepare_kwargs(
                        model=fallback_model,
                        messages=messages,
                        temperature=temperature,
                        response_format=response_format,
                        max_tokens=max_tokens,
                    )
                    fb_resp = await asyncio.wait_for(
                        self.main_client.chat.completions.create(**fb_kwargs),
                        timeout=45.0,
                    )
                    fb_latency = int((time.time() - fb_start) * 1000)
                    fb_choices = getattr(fb_resp, "choices", [])
                    if fb_choices and fb_choices[0].message:
                        fb_content = (getattr(fb_choices[0].message, "content", None) or "").strip()
                        if fb_content:
                            usage = getattr(fb_resp, "usage", None)
                            prompt_tokens = _safe_int(getattr(usage, "prompt_tokens", 0) if usage else 0)
                            completion_tokens = _safe_int(getattr(usage, "completion_tokens", 0) if usage else 0)
                            await cost_tracker.record_usage(
                                task_type=f"{task_type}_fallback",
                                model=fallback_model,
                                prompt_tokens=prompt_tokens,
                                completion_tokens=completion_tokens,
                                latency_ms=fb_latency,
                                status="success",
                                details={"primary_model_failed": chosen_model, "primary_error": error_str},
                            )
                            return fb_content
                except Exception as fb_err:
                    logger.error(f"Fallback model '{fallback_model}' also failed: {fb_err}")

            # Record failure in ledger
            await cost_tracker.record_usage(
                task_type=task_type,
                model=chosen_model,
                prompt_tokens=0,
                completion_tokens=0,
                latency_ms=latency_ms,
                status="error",
                error_message=error_str,
            )
            raise RuntimeError(f"AI generation failed for model '{chosen_model}': {e}")

    async def generate_chat_stream(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        task_type: str = "step_stream",
    ) -> AsyncGenerator[str, None]:
        """
        Server-Sent Events / Chunked streaming method.
        Keeps HTTP connection continuously active, eliminating timeouts.
        Captures full usage statistics from the final chunk and logs to AICostTracker.
        """
        raw_model = model or settings.FAST_MODEL
        chosen_model = self.normalize_model_name(raw_model)
        start_time = time.time()

        kwargs = self._prepare_kwargs(
            model=chosen_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )

        response_stream = await self.main_client.chat.completions.create(**kwargs)
        prompt_tokens = 0
        completion_tokens = 0
        reasoning_tokens = 0
        status = "success"
        error_msg = None

        try:
            async for chunk in response_stream:
                choices = getattr(chunk, "choices", [])
                if choices and choices[0].delta:
                    delta_content = getattr(choices[0].delta, "content", None)
                    if delta_content:
                        yield delta_content
                    elif hasattr(choices[0].delta, "reasoning_content") and getattr(choices[0].delta, "reasoning_content", None):
                        yield str(choices[0].delta.reasoning_content)

                if hasattr(chunk, "usage") and chunk.usage:
                    u = chunk.usage
                    prompt_tokens = _safe_int(getattr(u, "prompt_tokens", 0) or 0)
                    completion_tokens = _safe_int(getattr(u, "completion_tokens", 0) or 0)
                    if hasattr(u, "completion_tokens_details") and getattr(u, "completion_tokens_details", None):
                        reasoning_tokens = _safe_int(getattr(u.completion_tokens_details, "reasoning_tokens", 0) or 0)

        except Exception as e:
            status = "error"
            error_msg = str(e)
            logger.error(f"Error during streaming from '{chosen_model}': {e}")
            raise
        finally:
            latency_ms = int((time.time() - start_time) * 1000)
            await cost_tracker.record_usage(
                task_type=task_type,
                model=chosen_model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                reasoning_tokens=reasoning_tokens,
                latency_ms=latency_ms,
                status=status,
                error_message=error_msg,
            )

    async def generate_json(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
        task_type: str = "general_json",
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
            task_type=task_type,
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
                    model="openai/gpt-4.1-mini",
                    temperature=0.0,
                    timeout_seconds=30.0,
                    task_type="json_repair",
                )
                repaired = extract_json_or_fallback(repair_content)
                if repaired and "raw_text" not in repaired:
                    return repaired
            except Exception as e:
                logger.warning(f"JSON repair failed: {e}")
        return parsed


ai_clients = AIClientManager()
