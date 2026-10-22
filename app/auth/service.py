from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.db import models
from app.core.security import hash_password, verify_password
from app.auth.schemas import UserCreate, UserLogin
import re


def create_user(db: Session, user_data: UserCreate) -> models.User:
    # Check if user exists
    existing = db.query(models.User).filter(models.User.email == user_data.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email ya registrado"
        )
    
    # Validate password
    if len(user_data.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña debe tener al menos 8 caracteres"
        )
    
    user = models.User(
        email=user_data.email,
        hashed_password=hash_password(user_data.password),
        full_name=user_data.full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, login_data: UserLogin) -> models.User:
    user = db.query(models.User).filter(models.User.email == login_data.email).first()
    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos"
        )
    return user


def create_organization(db: Session, user: models.User, name: str, slug: str) -> models.Organization:
    # Check slug
    existing = db.query(models.Organization).filter(models.Organization.slug == slug).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slug ya en uso"
        )
    
    org = models.Organization(
        name=name,
        slug=slug,
        owner_id=user.id,
        plan="free"
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    
    # Add owner as member
    member = models.OrganizationMember(
        organization_id=org.id,
        user_id=user.id,
        role="owner"
    )
    db.add(member)
    db.commit()
    
    return org
