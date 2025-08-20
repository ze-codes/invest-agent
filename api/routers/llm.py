from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.settings import settings
from app.snapshot import compute_snapshot, compute_router
from app.llm import generate_brief, answer_question


router = APIRouter()


@router.post("/brief")
def brief(horizon: str = "1w", as_of: Optional[str] = None, k: int = 8, db: Session = Depends(get_db)):
    if not settings.llm_provider:
        # Still allow mock provider inside orchestrator; if none, return 400
        pass
    try:
        result = generate_brief(db, horizon=horizon, as_of=as_of, k=k)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@router.post("/ask")
def ask(question: str, horizon: str = "1w", as_of: Optional[str] = None, db: Session = Depends(get_db)):
    if not question or not question.strip():
        raise HTTPException(status_code=400, detail="question is required")
    try:
        result = answer_question(db, question=question, horizon=horizon, as_of=as_of)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


