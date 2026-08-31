import math
from typing import Tuple, Optional
from app.schemas.feed import VoiceReasoningAnalysis


class BayesianKnowledgeTracingEngine:
    """
    Bayesian Knowledge Tracing (BKT) Engine for updating student mastery probability
    and epistemic uncertainty after every interaction (Quiz or Voice reasoning).
    """

    DEFAULT_TRANSITION = 0.15 # P(T): probability of learning the concept between steps
    DEFAULT_SLIP = 0.10       # P(S): probability of making a careless error despite knowing
    DEFAULT_GUESS_MC = 0.25   # P(G): 4-choice question guess rate
    DEFAULT_GUESS_TF = 0.50   # P(G): True/False guess rate
    DEFAULT_GUESS_VOICE = 0.01# P(G): Spoken explanation cannot be guessed

    def update_mastery(
        self,
        prior_mastery: float,
        prior_uncertainty: float,
        is_correct: bool,
        item_type: str = "single_choice",
        voice_analysis: Optional[VoiceReasoningAnalysis] = None,
        discrimination_index: float = 1.0,
    ) -> Tuple[float, float]:
        """
        Calculates (posterior_mastery, posterior_uncertainty).
        """
        # Clamp prior mastery
        p_m = max(0.01, min(0.99, prior_mastery))

        # Determine Guess and Slip probabilities
        if voice_analysis and voice_analysis.is_genuine_understanding:
            p_g = self.DEFAULT_GUESS_VOICE
            p_s = 0.05
            coherence = voice_analysis.logical_coherence_score
        elif item_type == "multiple_choice":
            p_g = 0.20
            p_s = self.DEFAULT_SLIP
            coherence = 1.0
        else: # single_choice
            p_g = self.DEFAULT_GUESS_MC
            p_s = self.DEFAULT_SLIP
            coherence = 1.0

        p_t = self.DEFAULT_TRANSITION

        # 1. Bayesian Update based on observation
        if is_correct:
            # P(L_t | Correct) = (P(L_{t-1}) * (1 - P(S))) / (P(L_{t-1}) * (1 - P(S)) + (1 - P(L_{t-1})) * P(G))
            numerator = p_m * (1.0 - p_s)
            denominator = numerator + ((1.0 - p_m) * p_g)
            p_obs = numerator / max(1e-6, denominator)
        else:
            # P(L_t | Incorrect) = (P(L_{t-1}) * P(S)) / (P(L_{t-1}) * P(S) + (1 - P(L_{t-1})) * (1 - P(G)))
            numerator = p_m * p_s
            denominator = numerator + ((1.0 - p_m) * (1.0 - p_g))
            p_obs = numerator / max(1e-6, denominator)

        # Apply voice coherence boost/penalty if provided
        if voice_analysis:
            if voice_analysis.is_genuine_understanding and is_correct:
                p_obs = p_obs * (0.5 + 0.5 * coherence)
            elif not voice_analysis.is_genuine_understanding:
                p_obs = min(p_obs, 0.4)

        # 2. Add transition (learning step)
        posterior_m = p_obs + ((1.0 - p_obs) * p_t)
        posterior_m = max(0.01, min(0.99, posterior_m))

        # 3. Update Epistemic Uncertainty
        # Information gain reduces uncertainty
        info_gain = 0.35 * discrimination_index
        if voice_analysis:
            info_gain *= 1.8 # Voice answers provide significantly higher information gain

        posterior_uncertainty = max(0.05, prior_uncertainty * (1.0 - info_gain))

        return round(posterior_m, 4), round(posterior_uncertainty, 4)


bkt_engine = BayesianKnowledgeTracingEngine()
