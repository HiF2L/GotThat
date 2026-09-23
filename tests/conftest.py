import pytest
from unittest.mock import AsyncMock, MagicMock
from app.config import settings
from app.services.ai.client import ai_clients

# Guarantee test keys are used so real balance is never charged
settings.OPENAI_API_KEY = "mock-test-key-no-charge"
settings.STT_API_KEY = "mock-test-key-no-charge"
settings.TTS_API_KEY = "mock-test-key-no-charge"


@pytest.fixture(autouse=True)
def guard_against_real_llm_api_calls(monkeypatch):
    """
    Global safety guard: Ensures that no test accidentally makes real outbound
    network requests to external LLM / TTS / STT APIs, completely preventing API expenses.
    Mocks the underlying OpenAI client create methods while allowing full model resolution,
    JSON parsing, and prompt-building algorithms to execute cleanly.
    """
    async def safe_mock_chat_completion(*args, **kwargs):
        mock_choice = MagicMock()
        mock_choice.message.content = (
            '{"status": "ok", "mock": true, '
            '"explanation_markdown": "### Mock\\n\\nText", '
            '"verification_question": {"prompt": "Q", "options": [{"id": "a", "text": "A", "is_correct": true, "explanation": "Ok"}]}}'
        )
        mock_res = MagicMock()
        mock_res.choices = [mock_choice]
        return mock_res

    # If the method is not already patched by a specific test, apply the safe fallback mock
    if not isinstance(ai_clients.main_client.chat.completions.create, AsyncMock):
        monkeypatch.setattr(ai_clients.main_client.chat.completions, "create", safe_mock_chat_completion)
