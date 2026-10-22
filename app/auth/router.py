from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.auth import schemas, service
from app.auth.session import create_session_token, verify_session_token
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=schemas.UserResponse)
async def register(user_data: schemas.UserCreate, db: Session = Depends(get_db)):
    user = service.create_user(db, user_data)
    return user


@router.post("/login")
async def login(login_data: schemas.UserLogin, response: Response, db: Session = Depends(get_db)):
    user = service.authenticate_user(db, login_data)
    token = create_session_token(user.id)
    
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=settings.SESSION_MAX_AGE,
        samesite="lax",
        secure=settings.ENV == "production",
    )
    return {"message": "Login exitoso", "user": {"id": user.id, "email": user.email}}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key=settings.SESSION_COOKIE_NAME)
    return {"message": "Logout exitoso"}


@router.get("/me")
async def me(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")
    
    user_id = verify_session_token(token)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión inválida")
    
    user = db.query(service.models.User).filter(service.models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado")
    
    return {"id": user.id, "email": user.email, "full_name": user.full_name}
