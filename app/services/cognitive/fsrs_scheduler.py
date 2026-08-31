import math
from datetime import datetime, timedelta
from typing import Tuple


class FSRSScheduler:
    """
    Implementation of the modern Free Spaced Repetition Scheduler (FSRS) memory model.
    Models Memory Stability (S), Difficulty (D), and Retrievability (R).
    """

    DECAY_FACTOR = -0.5
    REQUESTED_RETENTION = 0.90 # Target 90% retention rate

    def calculate_retrievability(self, stability: float | None, elapsed_days: float) -> float:
        """
        R(t, S) = (1 + factor * t / S) ^ decay
        """
        if stability is None or stability <= 0:
            return 0.0
        if elapsed_days <= 0:
            return 1.0
        factor = 19.0 / 81.0
        return (1.0 + factor * (elapsed_days / stability)) ** self.DECAY_FACTOR

    def update_memory_state(
        self,
        current_stability: float | None,
        current_difficulty: float | None,
        last_review_at: datetime | None,
        is_correct: bool,
        rating_score: float = 3.0, # 1: Again, 2: Hard, 3: Good, 4: Easy
    ) -> Tuple[float, float, float, datetime]:
        """
        Returns (new_stability, new_difficulty, new_retrievability, next_review_due).
        """
        stab = float(current_stability if current_stability is not None else 0.0)
        diff = float(current_difficulty if current_difficulty is not None else 5.0)

        now = datetime.utcnow()
        elapsed_days = (now - last_review_at).total_seconds() / 86400.0 if last_review_at else 0.0

        current_retrievability = self.calculate_retrievability(stab, elapsed_days)

        # 1. Update Difficulty (D in [1, 10])
        # Delta D depends on whether the response was correct
        if is_correct:
            difficulty_delta = -0.3 * (rating_score - 3.0)
        else:
            difficulty_delta = 1.2

        new_difficulty = max(1.0, min(10.0, diff + difficulty_delta))

        # 2. Update Stability (S in days)
        if stab <= 0:
            # First learning event
            new_stability = 1.2 if is_correct else 0.4
        else:
            if is_correct:
                # S' = S * (1 + C * (11 - D) * S^-0.5 * (e^(1 - R) - 1))
                hard_penalty = 1.0 if rating_score >= 3.0 else 0.6
                c = 0.4
                r_term = math.exp(1.0 - current_retrievability) - 1.0
                growth = 1.0 + c * (11.0 - new_difficulty) * (stab ** -0.3) * r_term * hard_penalty
                new_stability = max(stab + 0.1, stab * growth)
            else:
                # Lapse / Forget
                new_stability = max(0.2, stab * 0.25)

        # 3. Calculate Interval to reach target retention (90%)
        # t_due = S * ((R_target ^ (1 / decay)) - 1) / factor
        factor = 19.0 / 81.0
        interval_days = new_stability * ((self.REQUESTED_RETENTION ** (1.0 / self.DECAY_FACTOR)) - 1.0) / factor
        interval_days = max(0.1, interval_days)

        next_review_due = now + timedelta(days=interval_days)
        new_retrievability = self.calculate_retrievability(new_stability, 0.0)

        return (
            round(new_stability, 2),
            round(new_difficulty, 2),
            round(new_retrievability, 3),
            next_review_due,
        )


fsrs_scheduler = FSRSScheduler()
