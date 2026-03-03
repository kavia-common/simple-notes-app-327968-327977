"""
Notes service (flow/orchestration layer).

Flow name: NotesCrudFlow
Single entrypoint: NotesService

Contracts:
- Inputs are validated by Pydantic models at the API boundary.
- Outputs are Note models.
- Errors:
  - NoteNotFoundError: when a note id doesn't exist.
  - NotesPersistenceError: bubbled up from persistence adapter.
- Side effects:
  - Creates/updates/deletes notes in a file-backed JSON store.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List
from uuid import UUID, uuid4

from src.api.models import Note, NoteCreate, NoteUpdate
from src.api.persistence import NotesFileRepository

logger = logging.getLogger("notes_backend.notes")


class NoteNotFoundError(KeyError):
    """Raised when a note cannot be found by id."""


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class NotesService:
    """
    NotesCrudFlow orchestration.

    This keeps business rules in one place, and delegates I/O to NotesFileRepository.
    """

    repo: NotesFileRepository

    # PUBLIC_INTERFACE
    def create_note(self, req: NoteCreate) -> Note:
        """Create a new note and persist it."""
        note = Note(
            id=uuid4(),
            title=req.title,
            content=req.content,
            created_at=_now_utc(),
            updated_at=_now_utc(),
        )
        logger.info("NotesCrudFlow.create start title_len=%s", len(note.title))
        self.repo.upsert(note)
        logger.info("NotesCrudFlow.create success id=%s", note.id)
        return note

    # PUBLIC_INTERFACE
    def list_notes(self) -> List[Note]:
        """Return all notes sorted by most recently updated first."""
        logger.info("NotesCrudFlow.list start")
        notes = self.repo.load_all()
        logger.info("NotesCrudFlow.list success count=%s", len(notes))
        return notes

    # PUBLIC_INTERFACE
    def get_note(self, note_id: UUID) -> Note:
        """Return a note by id or raise NoteNotFoundError."""
        logger.info("NotesCrudFlow.get start id=%s", note_id)
        note = self.repo.get_by_id(note_id)
        if note is None:
            logger.info("NotesCrudFlow.get not_found id=%s", note_id)
            raise NoteNotFoundError(str(note_id))
        logger.info("NotesCrudFlow.get success id=%s", note_id)
        return note

    # PUBLIC_INTERFACE
    def update_note(self, note_id: UUID, req: NoteUpdate) -> Note:
        """Update an existing note; supports partial updates."""
        logger.info("NotesCrudFlow.update start id=%s", note_id)
        existing = self.repo.get_by_id(note_id)
        if existing is None:
            logger.info("NotesCrudFlow.update not_found id=%s", note_id)
            raise NoteNotFoundError(str(note_id))

        updated = existing.model_copy(deep=True)
        if req.title is not None:
            updated.title = req.title
        if req.content is not None:
            updated.content = req.content
        updated.updated_at = _now_utc()

        self.repo.upsert(updated)
        logger.info("NotesCrudFlow.update success id=%s", note_id)
        return updated

    # PUBLIC_INTERFACE
    def delete_note(self, note_id: UUID) -> None:
        """Delete a note by id or raise NoteNotFoundError."""
        logger.info("NotesCrudFlow.delete start id=%s", note_id)
        deleted = self.repo.delete(note_id)
        if not deleted:
            logger.info("NotesCrudFlow.delete not_found id=%s", note_id)
            raise NoteNotFoundError(str(note_id))
        logger.info("NotesCrudFlow.delete success id=%s", note_id)
