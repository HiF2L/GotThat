from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Main LLM Provider (Provod.ai / OpenAI compatible)
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.provod.ai/v1"

    # Dedicated Speech-to-Text Provider (ProxyAPI)
    STT_API_KEY: str = ""
    STT_BASE_URL: str = "https://api.proxyapi.ru/openai/v1"
    STT_MODEL: str = "gpt-4o-mini-transcribe"

    # Text-to-Speech Settings (Free High-Quality Neural Voices, <10MB RAM footprint)
    TTS_ENGINE: str = "edge"
    TTS_API_KEY: str = ""
    TTS_BASE_URL: str = "https://api.proxyapi.ru/openai/v1"
    TTS_MODEL: str = "gpt-4o-mini-tts"
    TTS_VOICE: str = "ru-RU-SvetlanaNeural"

    # AI Model Names on Provod.ai
    DEEP_MODEL: str = "kimi-k3"
    PLAN_MODEL: str = "gemini-3-flash-preview"
    FAST_MODEL: str = "gemini-3-flash-preview"
    VISION_MODEL: Optional[str] = "gemini-3-flash-preview"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./got_it.db"

    # Application
    APP_NAME: str = "GotThat-Core-Tutor"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
