from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    orchestrate_instance_url: str = ""
    orchestrate_api_key: str = ""
    orchestrate_access_token: str = ""
    orchestrate_agent_id: str = ""
    orchestrate_iam_url: str = "https://iam.platform.saas.ibm.com"
    orchestrate_timeout_seconds: int = 60

    tavily_api_key: str = ""

    tts_api_url: str = ""
    tts_api_key: str = ""
    tts_default_voice: str = "en-US_AllisonV3Voice"

    topic_content_dir: str = "./content/topics"

    model_config = SettingsConfigDict(
        env_file=(".env.local", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
