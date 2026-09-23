import re
import logging
from typing import Dict, Any, Optional
from app.config import settings
from app.services.ai.client import ai_clients
from app.schemas.tutor import VisualArtifactSchema

logger = logging.getLogger(__name__)


class VisualizerSubagent:
    """
    Visualizer subagent that generates high-clarity, high-information-density SVG schematics
    and architecture blueprints with native dark-mode styling (transparent / deep dark slate).
    Strictly forbids trivial 3-box flowcharts.
    """

    async def generate_visualization(
        self,
        concept_title: str,
        explanation_context: str,
        target_aspect: str = "architecture",
    ) -> Optional[VisualArtifactSchema]:
        """
        Drafts, validates, and refines a modern dark-theme SVG diagram illustrating the concept.
        """
        system_prompt = (
            "You are an elite scientific illustrator and systems architect.\n"
            "Your job is to generate a standalone, responsive, high-density dark-theme SVG schematic "
            "that illustrates the deep functional mechanism, circuit architecture, or physical blueprint of the concept.\n\n"
            "STRICT QUALITY & PEDAGOGICAL MANDATES:\n"
            "1. NO TRIVIAL 3-BOX FLOWCHARTS: Never produce a basic 'Input -> Process -> Output' 3-box diagram. It adds zero value.\n"
            "2. HIGH INFORMATIONAL DENSITY: The diagram must clearly show:\n"
            "   - Internal subsystems / specialized modules / nuclei\n"
            "   - Feedback loops and gating / control filters with mathematical/operational labels\n"
            "   - Dynamic state transitions or mode comparisons (e.g. Active vs Inhibited / Tonic vs Burst / Normal vs Overload)\n"
            "3. MODERN DARK-THEME PALETTE:\n"
            "   - Canvas: `viewBox='0 0 700 380'`, background `transparent` or `#0B0F19`\n"
            "   - Cards & Nodes: fill='#1E293B' or '#0F172A', stroke='#6366F1' (Indigo) or #38BDF8 (Sky) or #10B981 (Emerald) or #F59E0B (Amber), rx='8'\n"
            "   - Typography: crisp fill='#F8FAFC' (titles), fill='#94A3B8' (sublabels), font-family='system-ui, -apple-system, sans-serif'\n"
            "   - Flow Arrows: stroke='#818CF8' or #38BDF8, stroke-width='2', with clear marker arrowheads\n"
            "4. Return JSON only:\n"
            '{"svg_code": "<svg viewBox=\'0 0 700 380\' ...>...</svg>", "alt_text": "Precise description of the mechanism illustrated"}'
        )

        user_content = (
            f"Concept: {concept_title}\n"
            f"Focus Aspect: {target_aspect}\n"
            f"Explanation Context: {explanation_context[:1400]}\n\n"
            "Generate the high-density dark-mode SVG diagram JSON."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            result = await ai_clients.generate_json(
                messages=messages,
                model=settings.FAST_MODEL,
                temperature=0.2,
                max_tokens=2500,
                timeout_seconds=15.0,
                task_type="svg_visualization",
            )
            raw_svg = result.get("svg_code", "")
            alt_text = result.get("alt_text", f"Circuit diagram for {concept_title}")

            if not raw_svg or len(raw_svg.strip()) < 50:
                return None

            # Self-correction check: Ensure <svg> tag existence
            if "<svg" not in raw_svg or "</svg>" not in raw_svg:
                match = re.search(r"<svg[\s\S]*?</svg>", raw_svg)
                if match:
                    raw_svg = match.group(0)
                else:
                    return None

            validated_svg = self._sanitize_svg(raw_svg)

            return VisualArtifactSchema(
                type="svg",
                payload=validated_svg,
                alt_text=alt_text,
            )
        except Exception as e:
            logger.error(f"Visualizer subagent error: {e}")
            return None

    def _sanitize_svg(self, svg_text: str) -> str:
        clean = svg_text.strip()
        if clean.startswith("```xml"):
            clean = clean[6:]
        if clean.startswith("```svg"):
            clean = clean[6:]
        if clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]

        clean = clean.strip()

        # Replace any bright white background rectangles with transparent
        clean = re.sub(
            r"<rect([^>]*?)fill=['\"]#(?:fff|ffffff|f8fafc|f1f5f9|e2e8f0|white)['\"]([^>]*?)\/?>",
            r"<rect\1fill='transparent'\2/>",
            clean,
            flags=re.IGNORECASE,
        )

        # Replace dark text on dark background with crisp light text
        clean = re.sub(
            r"fill=['\"]#(?:000|000000|1e293b|0f172a|334155|black)['\"]",
            "fill='#F8FAFC'",
            clean,
            flags=re.IGNORECASE,
        )

        if "style=" not in clean:
            clean = re.sub(r"<svg\b", "<svg style='background: transparent;'", clean, count=1)

        return clean


visualizer = VisualizerSubagent()
