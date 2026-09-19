"""Settings loaded from .env.

Which knowledge-source implementation loads is decided HERE, never by code
changes (OVERALL.md, services/knowledge).
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- GitHub OAuth ---
    github_client_id: str = ""
    github_client_secret: str = ""
    github_redirect_uri: str = "http://localhost:8000/auth/callback"
    session_secret: str = "dev-only-change-me"

    # --- LLM ---
    llm_provider: Literal["anthropic", "openai"] = "openai"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    scanner_model: str = "gpt-5"
    generator_model: str = "claude-sonnet-5"
    grader_model: str = "claude-sonnet-5"

    # --- Ingest ---
    target_language: Literal["python"] = "python"
    clone_depth: int = 200
    max_repo_mb: int = 200
    enable_blame: bool = False
    scan_file_limit: int = 25  # ranker takes the top N files

    # --- Knowledge source switches (see services/knowledge/base.py) ---
    taxonomy_source: Literal["seeded", "external"] = "seeded"
    # "chained" tries each source in demand_chain order and takes the first hit.
    # It is the default because the real source is still undecided -- see plan.md §10.
    demand_source: Literal["seeded", "scraped", "llm", "chained"] = "chained"
    demand_chain: list[str] = ["scraped", "llm", "seeded"]
    ladder_source: Literal["seeded", "external"] = "seeded"

    # --- Paths & modes ---
    mock_mode: bool = True
    cache_dir: Path = BACKEND_ROOT / "cache"
    mock_dir: Path = BACKEND_ROOT / "mock"
    knowledge_data_dir: Path = BACKEND_ROOT / "app" / "knowledge_data"
    data_dir: Path = PROJECT_ROOT / "data"
    database_url: str = f"sqlite:///{BACKEND_ROOT / 'cache' / 'app.db'}"

    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
