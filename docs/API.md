# 📡 Спецификация API GotIt (GotThat-Core-Tutor)

> Базовый префикс API: `/api/v1`  
> WebSocket: `/ws/deep/{session_id}`  
> Стандарт формата обмена данными: **JSON** (Content-Type: `application/json`)

---

## 📑 Содержание
1. [Системные эндпоинты](#1-системные-эндпоинты)
2. [Пользователи и настройки (/users)](#2-пользователи-и-настройки-users)
3. [Режим микрообучения (/feed)](#3-режим-микрообучения-feed)
4. [Сессии глубокого тьюторинга (/deep)](#4-сессии-глубокого-тьюторинга-deep)
5. [Треки и граф знаний (/tracks)](#5-треки-и-граф-знаний-tracks)
6. [WebSocket протокол реального времени](#6-websocket-протокол-реального-времени)

---

## 1. Системные эндпоинты

### `GET /health`
Проверка работоспособности и конфигурации активных моделей.

**Ответ (200 OK):**
```json
{
  "status": "healthy",
  "app_name": "GotThat-Core-Tutor",
  "deep_model": "kimi-k3",
  "fast_model": "gemini-3-flash-preview",
  "stt_model": "gpt-4o-mini-transcribe",
  "database": "sqlite"
}
```

---

## 2. Пользователи и настройки (`/users`)

### `GET /api/v1/users/active`
Получение профиля текущего активного пользователя (при отсутствии создается автоматически и подписывается на все активные треки).

**Ответ (200 OK):**
```json
{
  "user_id": "0d3a776e-5f80-4cf8-a90a-f0fbf02a4bf7",
  "username": "hitori_learner",
  "email": "learner@gotit.local",
  "preferred_language": "ru",
  "preferred_model": "kimi-k3"
}
```

---

### `GET /api/v1/users/{user_id}/settings`
Получение сохраненных языковых и модельных настроек пользователя.

**Ответ (200 OK):**
```json
{
  "user_id": "0d3a776e-5f80-4cf8-a90a-f0fbf02a4bf7",
  "preferred_language": "ru",
  "preferred_model": "kimi-k3"
}
```

---

### `PATCH /api/v1/users/{user_id}/settings`
Обновление настроек пользователя.

**Тело запроса:**
```json
{
  "preferred_language": "ru",
  "preferred_model": "deepseek-ai/DeepSeek-V3"
}
```

**Ответ (200 OK):**
```json
{
  "user_id": "0d3a776e-5f80-4cf8-a90a-f0fbf02a4bf7",
  "preferred_language": "ru",
  "preferred_model": "deepseek-ai/DeepSeek-V3"
}
```

---

## 3. Режим микрообучения (`/feed`)

### `GET /api/v1/feed/next`
Генерирует следующую карточку для ленты. Алгоритм сбалансированно выбирает:
1. Концепты, требующие интервального повторения по FSRS ($R < 0.90$).
2. Неисследованные концепты на фронтире онтологии с высокой эпистемической неопределенностью ($U \to 1.0$).

**Query параметры:**
- `user_id` (string, обязательный): Идентификатор пользователя.

**Ответ (200 OK):**
```json
{
  "card_id": "card_718293",
  "concept_id": "c_differential_forms_01",
  "concept_title": "Дифференциальные 1-формы и ковекторы",
  "track_title": "Дифференциальные формы и электродинамика",
  "item_type": "single_choice",
  "prompt_markdown": "Как дифференциальная 1-форма $\\omega$ действует на векторное поле $v$?",
  "options": [
    {
      "id": "opt_a",
      "text": "Отображает вектор в скалярную функцию (число в каждой точке)",
      "is_correct": true,
      "explanation": "1-форма является линейным функционалом над векторным пространством (ковектором)."
    },
    {
      "id": "opt_b",
      "text": "Поворачивает вектор на 90 градусов",
      "is_correct": false,
      "explanation": "Это геометрический оператор поворота, а не дифференциальная форма."
    }
  ],
  "difficulty": 0.6,
  "is_review": false
}
```

---

### `POST /api/v1/feed/submit`
Отправка ответа на карточку ленты с обновлением метрик BKT ($P(L)$ и $U$) и FSRS ($S$, $D$, $R$, $t_{next}$).

**Тело запроса:**
```json
{
  "user_id": "0d3a776e-5f80-4cf8-a90a-f0fbf02a4bf7",
  "card_id": "card_718293",
  "concept_id": "c_differential_forms_01",
  "assessment_item_id": "item_9921",
  "selected_option_ids": ["opt_a"],
  "response_time_ms": 4200
}
```

**Ответ (200 OK):**
```json
{
  "is_correct": true,
  "prior_mastery": 0.45,
  "posterior_mastery": 0.682,
  "uncertainty": 0.285,
  "stability_days": 1.45,
  "difficulty": 4.7,
  "next_review_due": "2026-08-29T14:30:00Z",
  "explanation": "Отлично! 1-форма сопоставляет вектору вещественное число.",
  "mastery_level_up": false
}
```

---

### `POST /api/v1/feed/voice-reasoning`
Анализ голосового рассуждения студента (Voice Yap Note) через транскрибацию Whisper и семантический LLM-анализ.

**Параметры формы (multipart/form-data):**
- `audio_file`: Бинарный аудиопоток (WebM / WAV / MP3).
- `attempt_id`: ID попытки прохождения.
- `concept_id`: ID концепта.

**Ответ (200 OK):**
```json
{
  "transcript": "Форма действует на касательный вектор линейно и возвращает проекцию или число...",
  "is_genuine_understanding": true,
  "logical_coherence_score": 0.92,
  "identified_misconceptions": [],
  "coaching_feedback": "Превосходная интуиция дуального пространства!"
}
```

---

## 4. Сессии глубокого тьюторинга (`/deep`)

### `POST /api/v1/deep/start`
Инициализация сессии глубокого погружения 1-на-1 по целевому концепту или треку.

**Тело запроса:**
```json
{
  "user_id": "0d3a776e-5f80-4cf8-a90a-f0fbf02a4bf7",
  "target_concept_id": "concept_uuid_here",
  "initial_user_context": "Я уже знаю базовый математический анализ и векторы",
  "language": "ru",
  "depth_level": "high"
}
```

**Ответ (200 OK):**
```json
{
  "session_id": "sess_81923019-3f",
  "status": "probing",
  "initial_action": {
    "phase": "probing",
    "probe_question": {
      "id": "q1",
      "subtopic_title": "Линейные функционалы и дуальность",
      "prompt": "Что является результатом действия 1-формы на вектор?",
      "options": [...]
    },
    "session_id": "sess_81923019-3f"
  }
}
```

---

### `POST /api/v1/deep/submit-probe`
Отправка ответа на диагностический вопрос фазы PROBE.

**Тело запроса:**
```json
{
  "session_id": "sess_81923019-3f",
  "concept_id": "q1",
  "selected_option_id": "b",
  "user_notes": "Помню это из курса тензорного анализа"
}
```

**Ответ (200 OK):**
- Возвращает следующий вопрос `{"phase": "probing", ...}`.
- Или, если 10 вопросов пройдены, автоматически запускает PLAN и возвращает `{"phase": "step_ready", "dag": {...}, "step": {...}}`.

---

### `GET /api/v1/deep/next-action`
Получение текущего действия стейт-машины (возобновление сессии, переход к следующему уроку).

**Query параметры:**
- `session_id` (string, обязательный)
- `user_notes` (string, опциональный)

---

### `POST /api/v1/deep/submit-answer`
Отправка ответа на проверочный вопрос (Verification Challenge), блокирующий завершение шага урока.

**Тело запроса:**
```json
{
  "session_id": "sess_81923019-3f",
  "step_sequence": 1,
  "selected_option_ids": ["a"],
  "yap_text_note": "Интуитивно это поток через бесконечно малую площадку",
  "user_voice_transcript": null
}
```

**Ответ (200 OK):**
```json
{
  "session_id": "sess_81923019-3f",
  "step_sequence": 1,
  "is_correct": true,
  "explanation": "Верно! Внешняя производная обобщает операторы ротора и дивергенции.",
  "remediation_required": false,
  "remediation_node_inserted": null,
  "updated_dag": { ... },
  "next_step_ready": true
}
```

---

### `POST /api/v1/deep/advance-node`
Переход к следующему непокрытому узлу DAG графа после успешного прохождения проверки.

---

### `POST /api/v1/deep/step/audio`
Генерация потокового аудио (MP3) через Neural TTS с предварительной фонетической транслитерацией формул LaTeX.

**Тело запроса:**
```json
{
  "text": "Рассмотрим уравнение Максвелла в дифференциальных формах: $dF = 0$.",
  "voice": "ru-RU-SvetlanaNeural"
}
```

**Ответ:** Бинарный аудиопоток `audio/mpeg`.

---

### `POST /api/v1/deep/ask`
Интерактивный вопрос студента к ИИ-тьютору в контексте текущего шага.

**Тело запроса:**
```json
{
  "session_id": "sess_81923019-3f",
  "question": "Почему оператор d примененный дважды дает ноль?",
  "context": "Урок по оператору внешней производной d^2 = 0"
}
```

**Ответ (200 OK):**
```json
{
  "answer": "Это фундаментальный топологический факт: граница границы равна нулю ($\partial(\partial M) = 0$). В анализе это эквивалентно равенству смешанных производных..."
}
```

---

## 5. Треки и граф знаний (`/tracks`)

### `GET /api/v1/tracks/`
Список всех доступных треков с прогрессом студента.

---

### `GET /api/v1/tracks/{track_id}`
Детализированная структура трека со всеми концептами, их пререквизитами и визуализацией графа Mermaid.

---

### `POST /api/v1/tracks/generate`
On-Demand синтез абсолютно нового трека знаний по любому пользовательскому запросу (от квантовой оптики до теории игр).

**Тело запроса:**
```json
{
  "user_id": "0d3a776e-5f80-4cf8-a90a-f0fbf02a4bf7",
  "topic_query": "Сверхпроводимость и эффект Джозефсона",
  "depth_level": "high",
  "user_wishes": "С акцентом на квантовые вычисления и кубиты трансмон"
}
```

**Ответ (200 OK):**
```json
{
  "track_id": "tr_901238",
  "title": "Сверхпроводимость и эффект Джозефсона",
  "slug": "sverhprovodimost-i-effekt-dzhozefsona",
  "concepts": [...]
}
```

---

### `DELETE /api/v1/tracks/{track_id}`
Полное удаление трека с каскадным удалением концептов, связей, зависимостей и истории попыток.

---

## 6. WebSocket протокол реального времени

Эндпоинт: `/ws/deep/{session_id}`

### Клиент $\to$ Сервер:
```json
{
  "action": "get_next_action",
  "user_notes": "Заметка студента"
}
```

```json
{
  "action": "ping"
}
```

### Сервер $\to$ Клиент:
```json
{
  "event": "tutor:step_ready",
  "payload": {
    "step": {
      "step_sequence": 1,
      "explanation_markdown": "...",
      "visual_artifact": {
        "type": "svg",
        "payload": "<svg viewBox='0 0 700 380'>...</svg>",
        "alt_text": "Схема взаимодействия"
      },
      "verification_challenge": {
        "item_id": "v1",
        "prompt_markdown": "...",
        "options": [...]
      }
    },
    "dag": {
      "mermaid_code": "graph TD\n...",
      "total_nodes": 24,
      "completed_nodes": 3
    }
  }
}
```
