"""SessionGrid API — Configuration"""

from pathlib import Path
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://sessiongrid:sessiongrid@localhost:5432/sessiongrid"
    database_url_sync: str = "postgresql://sessiongrid:sessiongrid@localhost:5432/sessiongrid"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Storage
    storage_root: str = "./storage"
    upload_max_size_mb: int = 200

    # Analysis Pipeline
    demucs_model: str = "htdemucs"
    sample_rate: int = 44100
    random_seed: int = 42
    pipeline_version: str = "2.0.0"

    # CORS
    cors_origins: str = "http://localhost:3000"

    # Debug
    debug: bool = True

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def upload_dir(self) -> Path:
        p = Path(self.storage_root) / "uploads"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def stems_dir(self) -> Path:
        p = Path(self.storage_root) / "stems"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def clicks_dir(self) -> Path:
        p = Path(self.storage_root) / "clicks"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def waveforms_dir(self) -> Path:
        p = Path(self.storage_root) / "waveforms"
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    return Settings()
