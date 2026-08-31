import pytest
from app.services.ai.tts_service import clean_markdown_for_speech, tts_service


def test_clean_markdown_preserves_parentheses():
    """
    CRITICAL USER MANDATE: Text inside parentheses MUST BE PRESERVED and voiced.
    """
    raw_md = (
        "# Метод Фейнмана\n\n"
        "Объясняйте сложные концепции (например, квантовую суперпозицию или формулу Циолковского) "
        "простыми словами (Feynman Technique).\n\n"
        "Уделяйте внимание деталям (включая единицы измерения и размерности)."
    )
    cleaned = clean_markdown_for_speech(raw_md)
    
    assert "(например, квантовую суперпозицию или формулу Циолковского)" in cleaned
    assert "(Feynman Technique)" in cleaned
    assert "(включая единицы измерения и размерности)" in cleaned
    assert "#" not in cleaned


def test_clean_markdown_strips_images_and_links():
    raw_md = (
        "Посмотрите на схему:\n\n"
        "![Архитектура системы](https://example.com/image.png)\n\n"
        "Подробнее читайте в [Официальной документации](https://docs.example.com)."
    )
    cleaned = clean_markdown_for_speech(raw_md)
    assert "https://example.com/image.png" not in cleaned
    assert "Официальной документации" in cleaned
    assert "https://docs.example.com" not in cleaned


def test_clean_markdown_latex_formulas():
    raw_md = (
        "Уравнение движения:\n\n"
        "$$\\Delta v = I_{sp} \\cdot g_0 \\cdot \\ln\\left(\\frac{m_0}{m_f}\\right)$$\n\n"
        "где $g_0$ — ускорение свободного падения."
    )
    cleaned = clean_markdown_for_speech(raw_md)
    assert "дельта v" in cleaned.lower()
    assert "натуральный логарифм" in cleaned.lower()
    assert "g с индексом 0" in cleaned.lower()


def test_chunking_long_text():
    long_text = ". ".join([f"Это важное предложение номер {i} с подробным объяснением (и контекстом)" for i in range(100)])
    chunks = tts_service.chunk_text(long_text, max_chars=500)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 600
        assert "(и контекстом)" in chunk


def test_voice_resolution():
    assert tts_service.resolve_voice("svetlana") == "ru-RU-SvetlanaNeural"
    assert tts_service.resolve_voice("dmitry") == "ru-RU-DmitryNeural"
    assert tts_service.resolve_voice("jenny") == "en-US-JennyNeural"
    assert tts_service.resolve_voice("guy") == "en-US-GuyNeural"
    assert tts_service.resolve_voice("alloy") == "ru-RU-SvetlanaNeural"


def test_clean_markdown_preserves_code_and_outer_fences():
    raw_md = (
        "```markdown\n"
        "# Основы FastAPI\n\n"
        "FastAPI — это современный фреймворк для Python.\n\n"
        "```python\n"
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        "```\n\n"
        "Этот код инициализирует веб-приложение.\n"
        "```"
    )
    cleaned = clean_markdown_for_speech(raw_md)
    assert "Основы FastAPI" in cleaned
    assert "FastAPI — это современный фреймворк для Python" in cleaned
    assert "from fastapi import FastAPI" in cleaned
    assert "Этот код инициализирует веб-приложение" in cleaned
    # Ensure it wasn't swallowed or replaced with just a placeholder
    assert cleaned != "Фрагмент программного кода."


