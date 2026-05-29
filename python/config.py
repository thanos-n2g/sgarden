"""Application configuration loaded from environment variables."""
import os
from typing import List

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))


class Settings(BaseSettings):
    """All runtime settings; each field maps to an env var of the same name (upper-cased)."""

    database_url: str = "mongodb://localhost:27017/sgarden"
    port: int = 4000
    server_secret: str = "sgarden-secret-key"
    jwt_expiration_hours: int = 24
    allowed_origins: List[str] = ["http://localhost:3000"]

    class Config:
        """Pydantic settings config."""

        env_file = "../.env"
        extra = "ignore"


settings = Settings()
