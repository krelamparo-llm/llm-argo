"""FastAPI app exposing Argo Brain chat over HTTP with a lightweight UI."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path
from typing import AsyncGenerator, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from argo_brain.assistant.orchestrator import ArgoAssistant, AssistantResponse
from argo_brain.core.memory.session import SessionMode
from argo_brain.log_setup import setup_logging
from argo_brain.runtime import create_runtime

STATIC_DIR = Path(__file__).parent / "static"
DEFAULT_HOST = os.getenv("ARGO_WEB_HOST", "0.0.0.0")
DEFAULT_PORT = int(os.getenv("ARGO_WEB_PORT", "3210"))
API_TOKEN = os.getenv("ARGO_WEB_TOKEN")

setup_logging()
logger = logging.getLogger("argo_brain.web")

_runtime = create_runtime()
_assistant = ArgoAssistant(
    llm_client=_runtime.llm_client,
    memory_manager=_runtime.memory_manager,
    session_manager=_runtime.session_manager,
    tool_tracker=_runtime.tool_tracker,
    default_session_mode=SessionMode.QUICK_LOOKUP,
    ingestion_manager=_runtime.ingestion_manager,
)

app = FastAPI(title="Argo Brain Web Chat", version="0.1.0")

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class ChatRequest(BaseModel):
    """Payload for chat requests."""

    message: str = Field(..., min_length=1, description="User message to send to Argo")
    session_id: Optional[str] = Field(
        default=None,
        description="Session identifier to reuse memory; auto-generated if omitted",
    )
    mode: Optional[str] = Field(
        default=SessionMode.QUICK_LOOKUP.value,
        description="Session mode guiding behavior (quick_lookup, research, ingest)",
    )


class ChatResponse(BaseModel):
    """Non-streaming chat response shape."""

    session_id: str
    text: str
    mode: str


class HealthResponse(BaseModel):
    status: str


async def require_token(authorization: Optional[str] = Header(default=None)) -> None:
    """Simple bearer token guard; skip if no token configured."""

    if not API_TOKEN:
        return
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")


def _sse_event(event: str, payload: dict) -> str:
    """Render a single SSE event line."""

    data = json.dumps(payload, ensure_ascii=False)
    return f"event: {event}\ndata: {data}\n\n"


def _run_chat(req: ChatRequest, session_id: str) -> AssistantResponse:
    """Execute the assistant call synchronously (run in a thread)."""

    session_mode = SessionMode.from_raw(req.mode)
    return _assistant.send_message(
        session_id,
        req.message,
        tool_results=None,
        return_prompt=False,
        session_mode=session_mode,
    )


@app.get("/health", response_model=HealthResponse)
async def health(_: None = Depends(require_token)) -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/", include_in_schema=False)
async def root() -> FileResponse:
    index = STATIC_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="UI not found")
    return FileResponse(index)


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, _: None = Depends(require_token)) -> ChatResponse:
    session_id = req.session_id or uuid.uuid4().hex[:8]
    try:
        result = await asyncio.to_thread(_run_chat, req, session_id)
    except Exception as exc:  # pragma: no cover - surfaced to client
        logger.exception("Chat request failed", extra={"session_id": session_id})
        raise HTTPException(status_code=500, detail=str(exc))

    return ChatResponse(
        session_id=session_id,
        text=result.text,
        mode=SessionMode.from_raw(req.mode).value,
    )


@app.post("/chat/stream")
async def chat_stream(
    req: ChatRequest,
    request: Request,
    _: None = Depends(require_token),
):
    session_id = req.session_id or uuid.uuid4().hex[:8]

    async def event_generator() -> AsyncGenerator[str, None]:
        yield _sse_event("session", {"session_id": session_id})
        try:
            result: AssistantResponse = await asyncio.to_thread(_run_chat, req, session_id)
        except Exception as exc:  # pragma: no cover - surfaced to client
            logger.exception("Chat stream failed", extra={"session_id": session_id})
            yield _sse_event("error", {"message": str(exc)})
            yield _sse_event("done", {})
            return

        payload = {
            "session_id": session_id,
            "text": result.text,
            "mode": SessionMode.from_raw(req.mode).value,
        }
        yield _sse_event("message", payload)
        yield _sse_event("done", {})

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=headers,
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )
