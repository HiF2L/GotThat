import asyncio
import logging
from datetime import datetime, date
from typing import Dict, Any, Optional, List
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import async_session_maker
from app.models.usage import AIUsageLog

logger = logging.getLogger("app.services.ai.cost_tracker")

# ProxyAPI Pricing in RUB per 1,000,000 tokens (from official research)
MODEL_RATES_PER_1M: Dict[str, Dict[str, float]] = {
    # 🏆 Топ: Цена / Качество
    "anthropic/claude-sonnet-5": {"prompt": 600.0, "completion": 3030.0, "reasoning": 3030.0},
    "openai/gpt-5.6-terra": {"prompt": 400.0, "completion": 2560.0, "reasoning": 2560.0},
    "deepseek/deepseek-v4-pro": {"prompt": 180.0, "completion": 550.0, "reasoning": 550.0},
    "x-ai/grok-4.7": {"prompt": 221.05, "completion": 652.63, "reasoning": 652.63},
    "qwen/qwen3.8-max": {"prompt": 290.0, "completion": 850.0, "reasoning": 850.0},
    "openai/gpt-4.1": {"prompt": 516.0, "completion": 2062.0, "reasoning": 2062.0},
    "zhipu/glm-5.3": {"prompt": 189.47, "completion": 600.0, "reasoning": 600.0},
    "openai/gpt-4.1-mini": {"prompt": 104.0, "completion": 413.0, "reasoning": 413.0},

    # ⚡ Эконом & Сервис
    "deepseek/deepseek-v4.1-flash": {"prompt": 41.05, "completion": 168.42, "reasoning": 168.42},
    "deepseek/deepseek-chat": {"prompt": 43.0, "completion": 126.0, "reasoning": 126.0},
    "qwen/qwen3.8-flash": {"prompt": 20.0, "completion": 65.0, "reasoning": 65.0},
    "openai/gpt-5.6-luna": {"prompt": 60.0, "completion": 360.0, "reasoning": 360.0},
    "google/gemini-3.1-flash-lite": {"prompt": 76.0, "completion": 455.0, "reasoning": 455.0},
    "google/gemini-2.5-flash": {"prompt": 78.0, "completion": 645.0, "reasoning": 645.0},
    "zhipu/glm-5.3-flash": {"prompt": 16.84, "completion": 58.95, "reasoning": 58.95},

    # Сервисные узлы конвейера & Structured Output
    "openai/o4-mini": {"prompt": 284.0, "completion": 1134.0, "reasoning": 1134.0},
    "schematron-v2-turbo": {"prompt": 4.11, "completion": 21.05, "reasoning": 21.05},

    # Флагманские & Предыдущие поколения (для поддержки совместимости и точного учета)
    "anthropic/claude-fable-5-1": {"prompt": 1580.0, "completion": 7900.0, "reasoning": 7900.0},
    "openai/gpt-6-astra": {"prompt": 1580.0, "completion": 7900.0, "reasoning": 7900.0},
    "anthropic/claude-opus-5": {"prompt": 1516.0, "completion": 7579.0, "reasoning": 7579.0},
    "openai/gpt-5.5": {"prompt": 1520.0, "completion": 9100.0, "reasoning": 9100.0},
    "moonshotai/kimi-k3": {"prompt": 550.0, "completion": 2700.0, "reasoning": 2700.0},
    "anthropic/claude-sonnet-4-5": {"prompt": 774.0, "completion": 3866.0, "reasoning": 3866.0},
    "anthropic/claude-opus-4-1": {"prompt": 3866.0, "completion": 19327.0, "reasoning": 19327.0},
    "google/gemini-3-flash-preview": {"prompt": 152.0, "completion": 910.0, "reasoning": 910.0},
    "google/gemini-2.5-pro": {"prompt": 323.0, "completion": 2577.0, "reasoning": 2577.0},
    "openai/gpt-4o-mini": {"prompt": 15.0, "completion": 60.0, "reasoning": 60.0},
    "openai/gpt-4o": {"prompt": 250.0, "completion": 1000.0, "reasoning": 1000.0},
    "deepseek/deepseek-reasoner": {"prompt": 190.0, "completion": 375.0, "reasoning": 375.0},

    # Default fallback
    "default": {"prompt": 20.0, "completion": 80.0, "reasoning": 80.0},
}


def _safe_int(val: Any, default: int = 0) -> int:
    if isinstance(val, int) and not isinstance(val, bool):
        return val
    try:
        if isinstance(val, (float, str)):
            return int(val)
    except Exception:
        pass
    return default


class AICostTracker:
    """
    Thread-safe, non-blocking ledger for AI token usage and financial cost accounting.
    Logs every single LLM call, token usage, latency, and exact cost in RUB.
    """

    @classmethod
    def calculate_cost_rub(
        cls,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        reasoning_tokens: int = 0,
    ) -> float:
        prompt_tokens = _safe_int(prompt_tokens)
        completion_tokens = _safe_int(completion_tokens)
        reasoning_tokens = _safe_int(reasoning_tokens)

        # Match rate or normalize
        norm = model.strip().lower()
        rate = MODEL_RATES_PER_1M.get(norm)
        if not rate:
            # Check prefix match
            for k, v in MODEL_RATES_PER_1M.items():
                if k in norm or norm in k:
                    rate = v
                    break
        if not rate:
            rate = MODEL_RATES_PER_1M["default"]

        prompt_cost = (prompt_tokens / 1_000_000.0) * rate["prompt"]
        # In OpenAI format, completion_tokens often includes reasoning_tokens,
        # but reasoning tokens might be priced higher if defined
        reasoning_rate = rate.get("reasoning", rate["completion"])
        effective_completion = max(0, completion_tokens - reasoning_tokens)
        comp_cost = (effective_completion / 1_000_000.0) * rate["completion"]
        reasoning_cost = (reasoning_tokens / 1_000_000.0) * reasoning_rate

        total_cost = prompt_cost + comp_cost + reasoning_cost
        return round(total_cost, 5)

    @classmethod
    async def record_usage(
        cls,
        task_type: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        reasoning_tokens: int = 0,
        latency_ms: int = 0,
        status: str = "success",
        error_message: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> None:
        """
        Records the token expenditure asynchronously in the background.
        """
        prompt_tokens = _safe_int(prompt_tokens)
        completion_tokens = _safe_int(completion_tokens)
        reasoning_tokens = _safe_int(reasoning_tokens)
        latency_ms = _safe_int(latency_ms)

        total_tokens = prompt_tokens + completion_tokens
        cost_rub = cls.calculate_cost_rub(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            reasoning_tokens=reasoning_tokens,
        )

        latency_sec = latency_ms / 1000.0
        log_line = (
            f"[💰 AI COST] task={task_type:<16} | model={model} | "
            f"{prompt_tokens:,} in, {completion_tokens:,} out (reasoning: {reasoning_tokens}) "
            f"[{total_tokens:,} total] | {cost_rub:.4f} ₽ | {latency_sec:.2f}s"
        )
        if status != "success":
            log_line += f" | status={status} (err: {error_message})"
            logger.warning(log_line)
        else:
            logger.info(log_line)

        # Background DB persistence to avoid blocking hot execution path
        try:
            async with async_session_maker() as session:
                entry = AIUsageLog(
                    task_type=task_type,
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    reasoning_tokens=reasoning_tokens,
                    total_tokens=total_tokens,
                    cost_rub=cost_rub,
                    latency_ms=latency_ms,
                    status=status,
                    error_message=error_message,
                    details=details,
                )
                session.add(entry)
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to persist AI usage log: {e}")

    @classmethod
    async def get_cost_summary(cls, session: AsyncSession) -> Dict[str, Any]:
        """
        Calculates today's total expenditures, token count, task breakdown,
        and returns recent log transactions.
        """
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        # 1. Total spent today & total tokens
        totals_res = await session.execute(
            select(
                func.coalesce(func.sum(AIUsageLog.cost_rub), 0.0),
                func.coalesce(func.sum(AIUsageLog.total_tokens), 0),
                func.count(AIUsageLog.id),
            ).where(AIUsageLog.timestamp >= today_start)
        )
        total_rub, total_tokens, total_calls = totals_res.one()

        # 2. Breakdown by task today
        task_res = await session.execute(
            select(
                AIUsageLog.task_type,
                func.coalesce(func.sum(AIUsageLog.cost_rub), 0.0),
                func.count(AIUsageLog.id),
                func.coalesce(func.sum(AIUsageLog.total_tokens), 0),
            )
            .where(AIUsageLog.timestamp >= today_start)
            .group_by(AIUsageLog.task_type)
        )
        breakdown_by_task = {
            row[0]: {
                "cost_rub": round(row[1], 4),
                "calls": row[2],
                "tokens": row[3],
            }
            for row in task_res.all()
        }

        # 3. Breakdown by model today
        model_res = await session.execute(
            select(
                AIUsageLog.model,
                func.coalesce(func.sum(AIUsageLog.cost_rub), 0.0),
                func.count(AIUsageLog.id),
                func.coalesce(func.sum(AIUsageLog.total_tokens), 0),
            )
            .where(AIUsageLog.timestamp >= today_start)
            .group_by(AIUsageLog.model)
        )
        breakdown_by_model = {
            row[0]: {
                "cost_rub": round(row[1], 4),
                "calls": row[2],
                "tokens": row[3],
            }
            for row in model_res.all()
        }

        # 4. Recent 30 calls
        recent_res = await session.execute(
            select(AIUsageLog).order_by(AIUsageLog.timestamp.desc()).limit(30)
        )
        recent_calls = [
            {
                "id": log.id,
                "timestamp": log.timestamp.isoformat(),
                "task_type": log.task_type,
                "model": log.model,
                "prompt_tokens": log.prompt_tokens,
                "completion_tokens": log.completion_tokens,
                "reasoning_tokens": log.reasoning_tokens,
                "total_tokens": log.total_tokens,
                "cost_rub": round(log.cost_rub, 4),
                "latency_ms": log.latency_ms,
                "status": log.status,
                "error_message": log.error_message,
            }
            for log in recent_res.scalars().all()
        ]

        return {
            "today_spent_rub": round(total_rub, 4),
            "today_tokens": total_tokens,
            "today_calls": total_calls,
            "breakdown_by_task": breakdown_by_task,
            "breakdown_by_model": breakdown_by_model,
            "recent_calls": recent_calls,
        }


cost_tracker = AICostTracker()
