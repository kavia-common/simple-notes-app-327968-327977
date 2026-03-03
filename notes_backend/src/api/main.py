"""
FastAPI application entrypoint for the Simple Notes backend.

PUBLIC INTERFACES:
- GET /                : health check
- CRUD /notes          : create/list/get/update/delete notes

Configuration (env vars):
- FRONTEND_ORIGIN (optional): additional allowed CORS origin (e.g. http://localhost:3000).
- NOTES_DATA_PATH (optional): path to JSON store for backend-local persistence.

Error contract:
- All errors use {"error","message","details","request_id"} via ErrorResponse.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.models import ErrorResponse
from src.api.persistence import NotesFileRepository, NotesPersistenceError
from src.api.routes_notes import get_notes_service, router as notes_router
from src.api.service import NoteNotFoundError, NotesService

# Basic logging setup (works with uvicorn; keeps logs searchable and consistent).
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("notes_backend")


openapi_tags = [
    {"name": "health", "description": "Health and diagnostics endpoints."},
    {"name": "notes", "description": "CRUD operations for notes."},
]

app = FastAPI(
    title="Simple Notes Backend API",
    description="Backend API for a simple notes application (create, list, update, delete).",
    version="1.0.0",
    openapi_tags=openapi_tags,
)


def _cors_origins_from_env() -> list[str]:
    """
    Determine allowed CORS origins.

    For local preview we must allow the React dev server origin (http://localhost:3000).
    Using allow_credentials=True forbids wildcard origins, so we always return explicit origins.

    Env:
    - FRONTEND_ORIGIN: optional, comma-separated list of additional origins.
      Example: "http://localhost:3000,http://127.0.0.1:3000"
    """
    # Default local dev origins (frontend -> backend)
    origins = {
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    }

    extra = os.getenv("FRONTEND_ORIGIN", "").strip()
    if extra:
        for part in extra.split(","):
            o = part.strip()
            if o:
                origins.add(o)

    return sorted(origins)


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins_from_env(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """
    Add a request_id to every response and make it available for error responses.

    This improves debuggability without requiring external tracing infrastructure.
    """
    request_id = request.headers.get("x-request-id") or str(uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    return response


def _error_response(
    *,
    request: Request,
    status_code: int,
    error: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    payload = ErrorResponse(
        error=error,
        message=message,
        details=details,
        request_id=getattr(request.state, "request_id", None),
    ).model_dump(exclude_none=True)
    return JSONResponse(status_code=status_code, content=payload)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.info(
        "request_validation_error path=%s request_id=%s",
        request.url.path,
        getattr(request.state, "request_id", None),
    )
    return _error_response(
        request=request,
        status_code=400,
        error="validation_error",
        message="Request validation failed",
        details={"errors": exc.errors()},
    )


@app.exception_handler(NoteNotFoundError)
async def note_not_found_handler(request: Request, exc: NoteNotFoundError):
    return _error_response(
        request=request,
        status_code=404,
        error="not_found",
        message="Note not found",
        details={"note_id": str(exc)},
    )


@app.exception_handler(NotesPersistenceError)
async def persistence_error_handler(request: Request, exc: NotesPersistenceError):
    logger.exception(
        "persistence_error path=%s request_id=%s",
        request.url.path,
        getattr(request.state, "request_id", None),
    )
    return _error_response(
        request=request,
        status_code=500,
        error="persistence_error",
        message="Notes storage error",
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception(
        "unhandled_error path=%s request_id=%s",
        request.url.path,
        getattr(request.state, "request_id", None),
    )
    return _error_response(
        request=request,
        status_code=500,
        error="internal_error",
        message="Internal server error",
    )


@app.on_event("startup")
async def startup() -> None:
    """
    Wire up repository + service and register router.

    This keeps configuration at the boundary and leaves NotesService reusable/testable.
    """
    repo = NotesFileRepository.from_env()
    app.state.notes_service = NotesService(repo=repo)

    # Dependency override to inject the service instance.
    def _svc_override() -> NotesService:
        return app.state.notes_service

    app.dependency_overrides[get_notes_service] = _svc_override

    # Include routers (idempotent on reload).
    # Note: FastAPI may reload in dev; including router multiple times can duplicate routes,
    # so we guard by checking existing routes for the prefix.
    already_included = any(getattr(r, "path", "").startswith("/notes") for r in app.router.routes)
    if not already_included:
        app.include_router(notes_router)


@app.get(
    "/",
    tags=["health"],
    summary="Health check",
    description="Basic health check endpoint for the backend container.",
    operation_id="healthCheck",
)
def health_check() -> Dict[str, str]:
    """Return a simple health response."""
    return {"message": "Healthy"}
