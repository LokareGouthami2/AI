"""Application configuration, loaded from environment variables / .env.

Secrets (API keys) live only here on the server. Nothing in this module is
ever serialised into an API response.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WRITEAI_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    env: Literal["development", "test", "production"] = "development"
    data_dir: Path = REPO_ROOT / "data"
    database_url: str | None = None  # defaults to sqlite in data_dir

    # Upload limits
    max_upload_mb: int = 20
    max_pages: int = 300
    max_docx_uncompressed_mb: int = 100

    # LLM
    llm_provider: Literal["auto", "anthropic", "mock"] = "auto"
    anthropic_model: str = "claude-opus-5-5"
    anthropic_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    anthropic_fallbacks: bool = True
    llm_timeout_s: float = 120.0
    # Read without the WRITEAI_ prefix so the standard variable name works.
    anthropic_api_key: SecretStr | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")

    # Embeddings: "auto" uses sentence-transformers if the model is available
    # locally, otherwise the deterministic hashing embedder.
    embedding_backend: Literal["auto", "sentence-transformers", "hashing"] = "auto"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # ML
    classifier_path: Path = REPO_ROOT / "ml_models" / "section_classifier.joblib"
    classifier_min_confidence: float = 0.45

    # API
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    api_token: SecretStr | None = None  # optional shared token for deployed demos
    rate_limit_per_minute: int = 60

    @field_validator("api_token", "anthropic_api_key", mode="before")
    @classmethod
    def _empty_secret_is_unset(cls, v):
        # `WRITEAI_API_TOKEN=` in a copied .env.example means "not set".
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return v

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def render_dir(self) -> Path:
        return self.data_dir / "renders"

    @property
    def vector_dir(self) -> Path:
        return self.data_dir / "chroma"

    @property
    def tmp_dir(self) -> Path:
        return self.data_dir / "tmp"

    @property
    def sqlalchemy_url(self) -> str:
        return self.database_url or f"sqlite:///{self.data_dir / 'writeai.db'}"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.upload_dir, self.render_dir, self.vector_dir, self.tmp_dir):
            d.mkdir(parents=True, exist_ok=True)
            try:
                d.chmod(0o700)
            except OSError:
                pass


@lru_cache
def get_settings() -> Settings:
    return Settings()
