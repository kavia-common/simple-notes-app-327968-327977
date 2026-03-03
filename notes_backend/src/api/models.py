"""
Pydantic models for the Notes API.

Contracts:
- Title is required and must be 1..200 characters after trimming.
- Content is optional (can be empty/None), max 20_000 characters.
- Note IDs are UUID strings.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


def _now_utc() -> datetime:
    """Return timezone-aware current UTC time."""
    return datetime.now(timezone.utc)


class NoteBase(BaseModel):
    """Base fields shared by create/update operations."""

    title: str = Field(..., min_length=1, max_length=200, description="Note title (1-200 chars).")
    content: Optional[str] = Field(
        default="",
        max_length=20_000,
        description="Note content (optional, up to 20k chars).",
    )

    @field_validator("title")
    @classmethod
    def _title_trim_and_validate(cls, v: str) -> str:
        v2 = v.strip()
        if not v2:
            raise ValueError("title must not be blank")
        return v2

    @field_validator("content")
    @classmethod
    def _content_default(cls, v: Optional[str]) -> str:
        # Normalize None -> "" so downstream persistence has a stable invariant.
        return "" if v is None else v


class NoteCreate(NoteBase):
    """Request model for creating a note."""


class NoteUpdate(BaseModel):
    """Request model for updating a note (partial update)."""

    title: Optional[str] = Field(default=None, min_length=1, max_length=200, description="Updated title.")
    content: Optional[str] = Field(
        default=None,
        max_length=20_000,
        description="Updated content. If omitted, content is unchanged.",
    )

    @field_validator("title")
    @classmethod
    def _title_trim_if_present(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v2 = v.strip()
        if not v2:
            raise ValueError("title must not be blank")
        return v2


class Note(NoteBase):
    """Response model representing a stored note."""

    id: UUID = Field(..., description="Note identifier (UUID).")
    created_at: datetime = Field(default_factory=_now_utc, description="Creation time (UTC).")
    updated_at: datetime = Field(default_factory=_now_utc, description="Last update time (UTC).")


class ErrorResponse(BaseModel):
    """Consistent error response shape for the API."""

    error: str = Field(..., description="Machine-readable error code.")
    message: str = Field(..., description="Human-readable error message.")
    details: Optional[dict] = Field(default=None, description="Optional structured error details.")
    request_id: Optional[str] = Field(
        default=None,
        description="Request identifier if provided by server middleware/logging.",
    )
