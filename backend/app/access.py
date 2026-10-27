from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from .auth import Principal, authenticate
from .database import ensure_production_role, get_db, settings


def private_db(principal: Principal = Depends(authenticate), db: Session = Depends(get_db)):
    ensure_production_role(db)
    db.info["owner_id"] = principal.user_id
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT set_config('app.user_id', :owner, true), set_config('app.auth_mode', :mode, true)"),
                   {"owner": str(principal.user_id) if principal.user_id else "", "mode": settings.auth_mode})
    yield db
