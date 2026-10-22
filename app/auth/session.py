from itsdangerous import URLSafeTimedSerializer
from app.core.config import settings
from typing import Optional

serializer = URLSafeTimedSerializer(settings.SECRET_KEY)


def create_session_token(user_id: str) -> str:
    return serializer.dumps({"user_id": user_id}, salt="session")


def verify_session_token(token: str, max_age: int = None) -> Optional[str]:
    try:
        data = serializer.loads(
            token, 
            salt="session", 
            max_age=max_age or settings.SESSION_MAX_AGE
        )
        return data.get("user_id")
    except Exception:
        return None
