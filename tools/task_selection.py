"""Durable, identity-bound selection of recommended WIKI tasks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
from typing import Sequence


class TaskSelectionError(ValueError):
    """Raised when a task selection cannot be safely consumed."""


@dataclass(frozen=True)
class PendingTaskSelection:
    selection_id: str
    user_id: str
    chat_id: str
    brief: dict
    brief_hash: str
    expires_at: datetime


class TaskSelectionStore:
    def __init__(self, db_path: Path, *, ttl_seconds: int = 600) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self.db_path = Path(db_path)
        self.ttl_seconds = ttl_seconds
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def issue(
        self,
        *,
        user_id: str,
        chat_id: str,
        brief: dict,
        now: datetime | None = None,
    ) -> PendingTaskSelection:
        recommendations = brief.get("recommended") if isinstance(brief, dict) else None
        if not user_id or not chat_id or not isinstance(recommendations, list) or not recommendations:
            raise ValueError("user_id, chat_id, and recommended tasks are required")
        serialized = json.dumps(brief, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        issued_at = _as_utc(now)
        pending = PendingTaskSelection(
            selection_id=f"S-{secrets.token_hex(6).upper()}",
            user_id=user_id,
            chat_id=chat_id,
            brief=brief,
            brief_hash=hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
            expires_at=issued_at + timedelta(seconds=self.ttl_seconds),
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO pending_task_selections
                    (selection_id, user_id, chat_id, brief_json, brief_hash,
                     issued_at, expires_at, consumed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    pending.selection_id,
                    pending.user_id,
                    pending.chat_id,
                    serialized,
                    pending.brief_hash,
                    issued_at.isoformat(),
                    pending.expires_at.isoformat(),
                ),
            )
        return pending

    def consume(
        self,
        selection_id: str,
        *,
        user_id: str,
        chat_id: str,
        selected_indices: Sequence[int],
        now: datetime | None = None,
    ) -> PendingTaskSelection | None:
        if not selection_id or not user_id or not chat_id:
            return None
        indices = tuple(dict.fromkeys(selected_indices))
        if not indices or len(indices) > 5 or any(type(index) is not int or index < 1 for index in indices):
            raise TaskSelectionError("선택 번호는 1개 이상 5개 이하로 지정해야 합니다.")
        current_time = _as_utc(now)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT selection_id, user_id, chat_id, brief_json, brief_hash, expires_at
                FROM pending_task_selections
                WHERE selection_id = ? AND user_id = ? AND chat_id = ?
                  AND consumed_at IS NULL
                """,
                (selection_id.upper(), user_id, chat_id),
            ).fetchone()
            if row is None:
                return None
            expires_at = datetime.fromisoformat(row[5])
            if expires_at <= current_time:
                return None
            brief = json.loads(row[3])
            actual_hash = hashlib.sha256(row[3].encode("utf-8")).hexdigest()
            if actual_hash != row[4] or not isinstance(brief, dict):
                raise TaskSelectionError("저장된 추천 후보의 무결성을 확인하지 못했습니다.")
            recommendations = brief.get("recommended")
            if not isinstance(recommendations, list) or any(index > len(recommendations) for index in indices):
                raise TaskSelectionError("추천 목록에 있는 번호만 선택해주세요.")
            updated = connection.execute(
                """
                UPDATE pending_task_selections
                SET consumed_at = ?
                WHERE selection_id = ? AND consumed_at IS NULL
                """,
                (current_time.isoformat(), selection_id.upper()),
            )
            if updated.rowcount != 1:
                return None
            return PendingTaskSelection(
                selection_id=row[0],
                user_id=row[1],
                chat_id=row[2],
                brief=brief,
                brief_hash=row[4],
                expires_at=expires_at,
            )

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_task_selections (
                    selection_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    chat_id TEXT NOT NULL,
                    brief_json TEXT NOT NULL,
                    brief_hash TEXT NOT NULL,
                    issued_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    consumed_at TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_pending_task_selection_identity
                ON pending_task_selections(user_id, chat_id, consumed_at, expires_at)
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection


def _as_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
