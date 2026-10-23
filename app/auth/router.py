from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.auth import schemas, service
from app.auth.session import create_session_token, verify_session_token
from app.core.config import settings
from app.core.cookies import set_session_cookie, delete_session_cookie
from app.core.limits import get_plan_limits

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
async def register(
    user_data: schemas.UserCreate, response: Response, db: Session = Depends(get_db)
):
    """Crea la cuenta, su organización inicial y deja la sesión iniciada."""
    user = service.create_user(db, user_data)
    org = service.ensure_default_organization(db, user)
    set_session_cookie(response, create_session_token(user.id))
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "email_verified": user.email_verified,
        "organization": {
            "id": org.id,
            "name": org.name,
            "slug": org.slug,
            "plan": org.plan,
        },
    }


@router.post("/login")
async def login(
    login_data: schemas.UserLogin, response: Response, db: Session = Depends(get_db)
):
    user = service.authenticate_user(db, login_data)
    token = create_session_token(user.id)
    set_session_cookie(response, token)
    org = service.ensure_default_organization(db, user)
    return {
        "message": "Login exitoso",
        "user": {"id": user.id, "email": user.email},
        "organization": {
            "id": org.id,
            "name": org.name,
            "slug": org.slug,
            "plan": org.plan,
        },
    }


@router.post("/logout")
async def logout(response: Response):
    delete_session_cookie(response)
    return {"message": "Logout exitoso"}


@router.get("/me")
async def me(request: Request, db: Session = Depends(get_db)):
    """Sesión actual: usuario, organización, plan y cuota consumida."""
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")

    user_id = verify_session_token(token)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión inválida")

    user = db.query(service.models.User).filter(service.models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado")

    payload = {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "organization": None,
        "plan": "free",
        "limits": get_plan_limits("free"),
        "usage": None,
    }

    member = (
        db.query(service.models.OrganizationMember)
        .filter(service.models.OrganizationMember.user_id == user.id)
        .first()
    )
    if member:
        org = (
            db.query(service.models.Organization)
            .filter(service.models.Organization.id == member.organization_id)
            .first()
        )
        if org:
            payload["organization"] = {
                "id": org.id,
                "name": org.name,
                "slug": org.slug,
            }
            payload["plan"] = org.plan
            payload["limits"] = get_plan_limits(org.plan)
            usage = (
                db.query(service.models.Usage)
                .filter(service.models.Usage.organization_id == org.id)
                .order_by(service.models.Usage.period_start.desc())
                .first()
            )
            if usage:
                payload["usage"] = {
                    "rows_used": usage.rows_used,
                    "rows_limit": usage.rows_limit,
                    "period_start": usage.period_start,
                }

    return payload
