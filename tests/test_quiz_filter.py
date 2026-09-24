import pytest
from app.services.ai.client import StreamingQuizFilter, extract_quiz_and_prose, sanitize_markdown_text
from app.services.tutor.step_executor import is_valid_complete_step


def test_streaming_quiz_filter_fragmented_delimiter():
    # Fragmented across arbitrary token boundaries
    chunks = [
        "## Глава 1. Введение\n\nТекст прекрасного урока.\n\n",
        "-",
        "--",
        "QUIZ",
        "_JSON",
        "---\n",
        '{"prompt": "Какой главный вывод?", "options": [{"id": "a", "text": "Да", "is_correct": true}]}',
    ]
    f = StreamingQuizFilter()
    emitted = []
    for c in chunks:
        for ev_type, text in f.process_chunk(c):
            if ev_type == "content":
                emitted.append(text)
    for ev_type, text in f.flush():
        if ev_type == "content":
            emitted.append(text)

    clean_content = "".join(emitted).strip()
    assert clean_content == "## Глава 1. Введение\n\nТекст прекрасного урока."
    assert "QUIZ" not in clean_content
    assert "{" not in clean_content
    assert f.in_quiz is True
    assert '"prompt": "Какой главный вывод?"' in f.quiz_buffer


def test_streaming_quiz_filter_preserves_markdown_bullets_and_rules():
    # Regular markdown lists and horizontal lines should not trigger quiz mode
    chunks = [
        "# Раздел\n\n",
        "---\n\n",
        "Список ключевых тезисов:\n",
        "- Пункт первый\n",
        "- Пункт второй\n",
    ]
    f = StreamingQuizFilter()
    emitted = []
    for c in chunks:
        for ev_type, text in f.process_chunk(c):
            if ev_type == "content":
                emitted.append(text)
    for ev_type, text in f.flush():
        if ev_type == "content":
            emitted.append(text)

    clean_content = "".join(emitted).strip()
    assert f.in_quiz is False
    assert "- Пункт первый" in clean_content
    assert "---" in clean_content


def test_extract_quiz_and_prose_delimiter_variant():
    raw_text = """### Основные выводы
Всё взаимосвязано и образует странную петлю.

---QUIZ_JSON---
{"prompt": "В чём суть петли?", "options": [{"id": "a", "text": "Самоотносимость", "is_correct": true, "explanation": "Верно"}]}"""

    prose, quiz = extract_quiz_and_prose(raw_text)
    assert prose == "### Основные выводы\nВсё взаимосвязано и образует странную петлю."
    assert quiz is not None
    assert quiz["prompt"] == "В чём суть петли?"
    assert len(quiz["options"]) == 1


def test_extract_quiz_and_prose_code_fence():
    raw_text = """# Заголовок
Содержание урока.

```json
{"prompt": "Вопрос из блока?", "options": [{"id": "a", "text": "Опция", "is_correct": true}]}
```"""

    prose, quiz = extract_quiz_and_prose(raw_text)
    assert prose == "# Заголовок\nСодержание урока."
    assert quiz is not None
    assert quiz["prompt"] == "Вопрос из блока?"


def test_sanitize_markdown_text_removes_quiz_json():
    raw_text = """# Урок
Интересная концепция.

--- QUIZ JSON ---
{"prompt": "Тест", "options": []}"""

    cleaned = sanitize_markdown_text(raw_text)
    assert cleaned == "# Урок\nИнтересная концепция."
    assert "QUIZ" not in cleaned
    assert "prompt" not in cleaned


def test_is_valid_complete_step_with_quiz_trailer():
    # If text had trailing quiz JSON, is_valid_complete_step should clean it and check prose completeness
    raw_text = """# Полный урок
Это детальное и исчерпывающее объяснение концепции квантовой запутанности, которое полностью раскрывает все аспекты темы.

---QUIZ_JSON---
{"prompt": "Вопрос?", "options": [{"id": "a", "text": "Ответ", "is_correct": true}]}"""

    assert is_valid_complete_step(raw_text) is True
