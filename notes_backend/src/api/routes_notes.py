"""
Notes API routes (API/entry layer boundary).

Maps HTTP -> NotesService flow and converts domain errors into consistent HTTP errors.
"""

from __future__ import annotations

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from src.api.models import ErrorResponse, Note, NoteCreate, NoteUpdate
from src.api.service import NotesService


router = APIRouter(prefix="/notes", tags=["notes"])


def get_notes_service() -> NotesService:
    """
    Dependency injection placeholder.

    The actual instance is provided via app.state in main.py.
    """
    # This function is overwritten by main.py's dependency override.
    raise RuntimeError("NotesService dependency not configured")


@router.post(
    "",
    response_model=Note,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse, "description": "Validation or request error"},
        500: {"model": ErrorResponse, "description": "Persistence or internal error"},
    },
    summary="Create a note",
    description="Create a new note with a title and optional content.",
    operation_id="createNote",
)
def create_note(req: NoteCreate, svc: NotesService = Depends(get_notes_service)) -> Note:
    """Create a note."""
    return svc.create_note(req)


@router.get(
    "",
    response_model=List[Note],
    responses={500: {"model": ErrorResponse, "description": "Persistence or internal error"}},
    summary="List notes",
    description="List all notes sorted by most recently updated first.",
    operation_id="listNotes",
)
def list_notes(svc: NotesService = Depends(get_notes_service)) -> List[Note]:
    """List all notes."""
    return svc.list_notes()


@router.get(
    "/{note_id}",
    response_model=Note,
    responses={
        404: {"model": ErrorResponse, "description": "Note not found"},
        500: {"model": ErrorResponse, "description": "Persistence or internal error"},
    },
    summary="Get a note",
    description="Fetch a single note by its UUID.",
    operation_id="getNote",
)
def get_note(note_id: UUID, svc: NotesService = Depends(get_notes_service)) -> Note:
    """Get a note by id."""
    return svc.get_note(note_id)


@router.put(
    "/{note_id}",
    response_model=Note,
    responses={
        400: {"model": ErrorResponse, "description": "Validation or request error"},
        404: {"model": ErrorResponse, "description": "Note not found"},
        500: {"model": ErrorResponse, "description": "Persistence or internal error"},
    },
    summary="Update a note",
    description="Update a note by UUID. Fields are optional; omitted fields are unchanged.",
    operation_id="updateNote",
)
def update_note(note_id: UUID, req: NoteUpdate, svc: NotesService = Depends(get_notes_service)) -> Note:
    """Update a note."""
    return svc.update_note(note_id, req)


@router.delete(
    "/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        404: {"model": ErrorResponse, "description": "Note not found"},
        500: {"model": ErrorResponse, "description": "Persistence or internal error"},
    },
    summary="Delete a note",
    description="Delete a note by UUID.",
    operation_id="deleteNote",
)
def delete_note(note_id: UUID, svc: NotesService = Depends(get_notes_service)) -> Response:
    """Delete a note."""
    svc.delete_note(note_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
