import pytest
from app.services.ai.client import ai_clients


def test_model_name_normalization():
    # 1. Typo 'light' vs 'lite'
    assert ai_clients.normalize_model_name("gemini-3.1-flash-light") == "google/gemini-3.1-flash-lite"
    assert ai_clients.normalize_model_name("gemini_2.5_flash_light") == "google/gemini-2.5-flash-lite"

    # 2. Namespace prefixes
    assert ai_clients.normalize_model_name("google/gemini-3.1-flash-lite") == "google/gemini-3.1-flash-lite"
    assert ai_clients.normalize_model_name("moonshot-ai/kimi-k3") == "moonshotai/kimi-k3"
    assert ai_clients.normalize_model_name("anthropic/claude-sonnet-5") == "anthropic/claude-sonnet-5"

    # 3. Shorthand aliases
    assert ai_clients.normalize_model_name("kimi") == "moonshotai/kimi-k3"
    assert ai_clients.normalize_model_name("claude") == "anthropic/claude-sonnet-4-5"
    assert ai_clients.normalize_model_name("deepseek") == "deepseek/deepseek-chat"
    assert ai_clients.normalize_model_name("gpt") == "openai/gpt-4.1-mini"


@pytest.mark.asyncio
async def test_generate_json_resilience():
    from unittest.mock import patch, AsyncMock
    with patch.object(ai_clients.main_client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
        mock_choice = AsyncMock()
        mock_choice.message.content = '{"status": "ok"}'
        mock_res = AsyncMock()
        mock_res.choices = [mock_choice]
        mock_create.return_value = mock_res

        res = await ai_clients.generate_json(
            messages=[{"role": "user", "content": "Return json: {\"status\": \"ok\"}"}],
            model="gemini-3.1-flash-light", # intentional typo from user
        )
        assert res.get("status") == "ok"
        assert mock_create.call_args[1]["model"] == "google/gemini-3.1-flash-lite"

