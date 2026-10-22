from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Data Cleaner B2B"
    ENV: str = "dev"
    SECRET_KEY: str = "change-me-in-production-please"
    SESSION_COOKIE_NAME: str = "dcb_session"
    SESSION_MAX_AGE: int = 60 * 60 * 24 * 7  # 7 days
    
    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "sqlite:////tmp/app.db"
    )
    
    # CORS
    ALLOWED_ORIGINS: str = "*"
    
    # Auth
    PASSWORD_MIN_LENGTH: int = 8
    BCRYPT_ROUNDS: int = 12
    
    # Stripe (will be used later)
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PRICE_BASIC: str = ""
    STRIPE_PRICE_PRO: str = ""
    
    # Redis (will be used later)
    REDIS_URL: str = ""
    
    # R2 (will be used later)
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET_NAME: str = ""
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
