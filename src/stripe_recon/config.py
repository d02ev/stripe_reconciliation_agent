from decimal import Decimal
from pathlib import Path
from typing import Optional

from pydantic import BaseModel
from pydantic_settings import BaseSettings


class ReconciliationConfig(BaseModel):
    CONFIDENCE_EXACT: float = 1.0
    CONFIDENCE_TIMING: float = 0.9
    CONFIDENCE_NO_MATCH: float = 0.0

    DATE_TOLERANCE_DAYS: int = 2

    ROUNDING_THRESHOLD_CENTS: int = 10

    DUPLICATE_TIME_WINDOW_HOURS: int = 24

    DEFAULT_CURRENCY: str = "usd"


class Settings(BaseSettings):
    STRIPE_API_KEY: Optional[str] = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


def get_settings() -> Settings:
    return Settings()


config = ReconciliationConfig()
settings = get_settings()
