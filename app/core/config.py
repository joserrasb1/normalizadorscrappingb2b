from pydantic_settings import BaseSettings
from typing import List
import os

# Render define RENDER=true en todos sus servicios. Lo usamos para arrancar en
# modo producción sin obligar a configurar ENV a mano (el modo producción
# activa Secure en las cookies y rechaza los webhooks sin firma).
DEFAULT_ENV = "production" if os.getenv("RENDER") else "dev"

# Origen de la landing. Es el único origen autorizado a llamar a la API con
# credenciales (cookie de sesión) cuando ALLOWED_ORIGINS no se configura.
DEFAULT_LANDING = "https://normalizadorscrappingb2b.pages.dev"


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Data Cleaner B2B"
    ENV: str = DEFAULT_ENV
    SECRET_KEY: str = "change-me-in-production-please"
    SESSION_COOKIE_NAME: str = "dcb_session"
    SESSION_MAX_AGE: int = 60 * 60 * 24 * 7  # 7 days

    # URL pública de la landing (Cloudflare Pages). Es donde debe volver el
    # usuario tras pagar en Stripe. Si se deja vacía se usa el host de la API.
    APP_URL: str = DEFAULT_LANDING

    # Cookies de sesión.
    # La landing (pages.dev) y la API (onrender.com) están en dominios
    # distintos => para que la cookie viaje en fetch cross-site hace falta
    # SameSite=None + Secure, y CORS con allow_credentials y origenes exactos.
    # Deja SESSION_COOKIE_SAMESITE vacío para el valor automático
    # (none en producción, lax en local).
    SESSION_COOKIE_SAMESITE: str = ""  # auto | lax | strict | none
    SESSION_COOKIE_SECURE: bool = False

    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "sqlite:////tmp/app.db"
    )
    
    # CORS
    # Lista de orígenes separados por comas. Con una lista explícita se activa
    # allow_credentials (necesario para la cookie de sesión). Usa "*" sólo si
    # quieres una API pública sin sesión.
    ALLOWED_ORIGINS: str = DEFAULT_LANDING
    
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
