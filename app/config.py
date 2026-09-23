from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Main LLM Provider (ProxyAPI / OpenAI compatible)
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.proxyapi.ru/v1"

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

    # AI Model Names on ProxyAPI
    DEEP_MODEL: str = "openai/gpt-4.1-mini"
    PLAN_MODEL: str = "openai/gpt-4.1-mini"
    FAST_MODEL: str = "openai/gpt-4.1-mini"
    VISION_MODEL: Optional[str] = "google/gemini-2.5-flash"


    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./got_it.db"

    # Application
    APP_NAME: str = "GotThat-Core-Tutor"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
