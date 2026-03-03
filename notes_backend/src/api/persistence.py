"""
Persistence adapter layer for notes.

This module isolates filesystem I/O behind a small repository API.

Storage format:
- A single JSON file containing { "notes": [<note dicts>] }.
- All timestamps are stored as ISO 8601 strings.
- Notes are returned sorted by updated_at desc, then created_at desc.

Failure modes:
- File missing: treated as empty store.
- JSON corrupt: raises NotesPersistenceError (mapped to HTTP 500 at the API boundary).
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import TypeAdapter

from src.api.models import Note


class NotesPersistenceError(RuntimeError):
    """Raised when notes cannot be loaded/saved due to filesystem or data corruption."""


_NOTES_LIST_ADAPTER = TypeAdapter(List[Note])


@dataclass(frozen=True)
class NotesFileRepository:
    """
    File-backed notes repository.

    Side effects:
    - Reads/writes a JSON file on disk.
    - Uses an in-process lock to prevent concurrent writes within one worker.
      (This is "minimal persistence"; not intended for multi-worker strong consistency.)
    """

    path: str
    _lock: threading.Lock

    @staticmethod
    def from_env(default_relpath: str = "data/notes.json") -> "NotesFileRepository":
        """
        Construct a repository using env var NOTES_DATA_PATH, falling back to a repo-local path.

        This keeps configuration at the boundary (FastAPI app startup) and avoids hidden env access
        from deep domain code.
        """
        p = os.getenv("NOTES_DATA_PATH")
        if not p:
            # Store inside container working directory (repo) by default.
            p = os.path.abspath(default_relpath)
        return NotesFileRepository(path=p, _lock=threading.Lock())

    def _ensure_parent_dir(self) -> None:
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)

    def load_all(self) -> List[Note]:
        """Load all notes from disk."""
        with self._lock:
            if not os.path.exists(self.path):
                return []
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
            except json.JSONDecodeError as e:
                raise NotesPersistenceError(f"Notes store is corrupt at {self.path}") from e
            except OSError as e:
                raise NotesPersistenceError(f"Failed to read notes store at {self.path}") from e

            notes_raw = raw.get("notes", [])
            try:
                notes = _NOTES_LIST_ADAPTER.validate_python(notes_raw)
            except Exception as e:
                raise NotesPersistenceError(f"Notes store schema invalid at {self.path}") from e

            return self._sort_notes(notes)

    def save_all(self, notes: List[Note]) -> None:
        """Persist all notes to disk (atomic replace via tmp file)."""
        with self._lock:
            self._ensure_parent_dir()
            tmp_path = f"{self.path}.tmp"
            payload = {"notes": [n.model_dump(mode="json") for n in notes]}
            try:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, self.path)
            except OSError as e:
                raise NotesPersistenceError(f"Failed to write notes store at {self.path}") from e
            finally:
                # Best-effort cleanup if replace failed after tmp creation.
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except OSError:
                    pass

    def get_by_id(self, note_id: UUID) -> Optional[Note]:
        """Fetch a note by id."""
        notes = self.load_all()
        for n in notes:
            if n.id == note_id:
                return n
        return None

    def upsert(self, note: Note) -> None:
        """Insert or replace a note by id."""
        notes = self.load_all()
        replaced = False
        for idx, existing in enumerate(notes):
            if existing.id == note.id:
                notes[idx] = note
                replaced = True
                break
        if not replaced:
            notes.append(note)
        notes = self._sort_notes(notes)
        self.save_all(notes)

    def delete(self, note_id: UUID) -> bool:
        """Delete a note by id. Returns True if deleted, else False."""
        notes = self.load_all()
        new_notes = [n for n in notes if n.id != note_id]
        if len(new_notes) == len(notes):
            return False
        self.save_all(self._sort_notes(new_notes))
        return True

    @staticmethod
    def _sort_notes(notes: List[Note]) -> List[Note]:
        def _dt(v: datetime) -> float:
            return v.timestamp()

        return sorted(notes, key=lambda n: (_dt(n.updated_at), _dt(n.created_at)), reverse=True)
