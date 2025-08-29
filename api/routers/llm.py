from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.settings import settings
from app.llm import generate_brief
from app.llm.orchestrator import agent_answer_question_events


router = APIRouter()


@router.post("/brief")
def brief(horizon: str = "1w", as_of: Optional[str] = None, k: int = 12, db: Session = Depends(get_db)):
    if not settings.llm_provider:
        pass
    try:
        result = generate_brief(db, horizon=horizon, as_of=as_of, k=k)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@router.get("/ask_stream")
def ask_stream(question: str, horizon: str = "1w", as_of: Optional[str] = None, db: Session = Depends(get_db)):
    if not question or not question.strip():
        raise HTTPException(status_code=400, detail="question is required")

    def _sse():
        try:
            for ev in agent_answer_question_events(db, question=question, horizon=horizon, as_of=as_of):
                # SSE format: optional 'event:' then 'data:' line, blank line terminator
                name = ev.get("event", "message")
                payload = ev.get("data", {})
                import json as _json
                yield f"event: {name}\n" + f"data: {_json.dumps(payload, default=str)}\n\n"
        except Exception as e:
            yield f"event: error\n" + f"data: {str(e)}\n\n"

    return StreamingResponse(_sse(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
    })

