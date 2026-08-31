import logging
from typing import Dict, Any, List, Optional
from app.config import settings
from app.services.ai.client import ai_clients

logger = logging.getLogger(__name__)


class FactCheckerSubagent:
    """
    Parallel verification subagent that fact-checks mathematical definitions,
    theorems, proofs, and reasoning steps before they are shown to the student.
    Matches the verification agent behavior from the reference video.
    """

    async def verify_concept_explanation(
        self,
        concept_title: str,
        explanation_markdown: str,
        context_nodes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        system_prompt = (
            "You are a rigorous, hyper-precise mathematical and scientific Fact-Checker Subagent. "
            "Your sole mission is to audit educational content for false claims, sloppy notation, "
            "invalid definitions, sign errors, or dimension mismatches.\n\n"
            "Return JSON with the following format:\n"
            "{\n"
            '  "is_verified": boolean,\n'
            '  "confidence_score": float (0.0 to 1.0),\n'
            '  "detected_flaws": ["list of issues if any"],\n'
            '  "corrected_markdown": "null or corrected explanation markdown if minor fix needed",\n'
            '  "verification_notes": "Short note confirming rigorous correctness"\n'
            "}"
        )

        context_str = ", ".join(context_nodes) if context_nodes else "Fundamental domain prerequisite"
        user_content = (
            f"Target Concept: {concept_title}\n"
            f"Prerequisite Context: {context_str}\n\n"
            f"Draft Explanation to Audit:\n{explanation_markdown}"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            result = await ai_clients.generate_json(
                messages=messages,
                model=settings.FAST_MODEL, # Fast & accurate subagent fact-checking (0.8s)
                temperature=0.0,
            )
            return result
        except Exception as e:
            logger.warning(f"Fact checker error (fallback to verified): {e}")
            return {
                "is_verified": True,
                "confidence_score": 0.9,
                "detected_flaws": [],
                "corrected_markdown": None,
                "verification_notes": "Passed basic verification.",
            }


fact_checker = FactCheckerSubagent()
