import pytest
from datetime import datetime, timedelta
from app.services.cognitive.bkt_engine import bkt_engine
from app.services.cognitive.fsrs_scheduler import fsrs_scheduler
from app.schemas.feed import VoiceReasoningAnalysis


def test_bkt_regular_multiple_choice_update():
    prior_m = 0.20
    prior_u = 1.0

    # Correct choice answer
    post_m, post_u = bkt_engine.update_mastery(
        prior_mastery=prior_m,
        prior_uncertainty=prior_u,
        is_correct=True,
        item_type="single_choice",
        voice_analysis=None,
    )

    assert post_m > prior_m
    assert post_u < prior_u
    # Uncertainty should decrease
    assert post_u <= 0.65


def test_bkt_voice_reasoning_boost():
    prior_m = 0.20
    prior_u = 1.0

    voice_analysis = VoiceReasoningAnalysis(
        logical_coherence_score=0.95,
        demonstrated_understanding=["Linear functional", "oriented area"],
        misconceptions_detected=[],
        reasoning_summary="Clear deductive reasoning",
        speech_hesitation_detected=False,
        is_genuine_understanding=True,
    )

    # Correct voice answer
    post_m_voice, post_u_voice = bkt_engine.update_mastery(
        prior_mastery=prior_m,
        prior_uncertainty=prior_u,
        is_correct=True,
        voice_analysis=voice_analysis,
    )

    # Standard MCQ answer
    post_m_mcq, post_u_mcq = bkt_engine.update_mastery(
        prior_mastery=prior_m,
        prior_uncertainty=prior_u,
        is_correct=True,
        voice_analysis=None,
    )

    # Voice answer must produce significantly higher mastery leap and lower uncertainty!
    assert post_m_voice > post_m_mcq
    assert post_u_voice < post_u_mcq


def test_fsrs_stability_growth_and_interval():
    # Initial review
    s1, d1, r1, due1 = fsrs_scheduler.update_memory_state(
        current_stability=0.0,
        current_difficulty=5.0,
        last_review_at=None,
        is_correct=True,
    )

    assert s1 > 0
    assert due1 > datetime.utcnow()

    # Second successful review after 2 days
    review_time = datetime.utcnow() - timedelta(days=2)
    s2, d2, r2, due2 = fsrs_scheduler.update_memory_state(
        current_stability=s1,
        current_difficulty=d1,
        last_review_at=review_time,
        is_correct=True,
        rating_score=4.0,
    )

    # Stability must expand over time
    assert s2 > s1
    assert due2 > due1


def test_fsrs_forgetting_lapse():
    s1 = 10.0
    d1 = 5.0
    review_time = datetime.utcnow() - timedelta(days=12)

    s2, d2, r2, due2 = fsrs_scheduler.update_memory_state(
        current_stability=s1,
        current_difficulty=d1,
        last_review_at=review_time,
        is_correct=False, # Student forgot
    )

    # Stability drops significantly upon lapse
    assert s2 < s1
    assert d2 > d1 # Difficulty increases
