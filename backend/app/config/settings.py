"""Process-level configuration (env vars). Business settings live in the DB (see services/settings_store.py)."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DRIFTBOUND_", env_file=REPO_ROOT / ".env", extra="ignore")

    workspace: Path = REPO_ROOT / "workspace"
    database_url: str = ""  # default: sqlite file inside workspace
    host: str = "127.0.0.1"  # localhost-only by default
    port: int = 8000
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"
    ollama_url: str = "http://127.0.0.1:11434"
    comfyui_url: str = "http://127.0.0.1:8188"
    youtube_api_key: str = ""  # free Data API key for research (never sent to the frontend)
    youtube_client_secrets: Path = REPO_ROOT / "secrets" / "client_secret.json"
    youtube_token_file: Path = REPO_ROOT / "secrets" / "youtube_token.json"
    worker_poll_seconds: float = 1.0

    @property
    def db_url(self) -> str:
        return self.database_url or f"sqlite:///{(self.workspace / 'driftbound.db').as_posix()}"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    for sub in ("projects", "assets", "previews", "exports", "research", "cache", "backups"):
        (s.workspace / sub).mkdir(parents=True, exist_ok=True)
    return s
