"""Durable, identity-bound approvals for WIKI Inbox memo creation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import secrets
import sqlite3


@dataclass(frozen=True)
class PendingMemo:
    approval_id: str
    user_id: str
    chat_id: str
    content: str
    content_hash: str
    expires_at: datetime


class MemoApprovalStore:
    def __init__(self, db_path: Path, *, ttl_seconds: int = 300) -> None:
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
        content: str,
        now: datetime | None = None,
    ) -> PendingMemo:
        normalized_content = content.strip()
        if not user_id or not chat_id or not normalized_content:
            raise ValueError("user_id, chat_id, and content are required")

        issued_at = _as_utc(now)
        pending = PendingMemo(
            approval_id=f"H-{secrets.token_hex(6).upper()}",
            user_id=user_id,
            chat_id=chat_id,
            content=normalized_content,
            content_hash=hashlib.sha256(
                normalized_content.encode("utf-8")
            ).hexdigest(),
            expires_at=issued_at + timedelta(seconds=self.ttl_seconds),
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO pending_memos
                    (approval_id, user_id, chat_id, content, content_hash,
                     issued_at, expires_at, consumed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    pending.approval_id,
                    pending.user_id,
                    pending.chat_id,
                    pending.content,
                    pending.content_hash,
                    issued_at.isoformat(),
                    pending.expires_at.isoformat(),
                ),
            )
        return pending

    def consume(
        self,
        approval_id: str,
        *,
        user_id: str,
        chat_id: str,
        now: datetime | None = None,
    ) -> PendingMemo | None:
        if not approval_id or not user_id or not chat_id:
            return None
        current_time = _as_utc(now)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT approval_id, user_id, chat_id, content, content_hash,
                       expires_at
                FROM pending_memos
                WHERE approval_id = ?
                  AND user_id = ?
                  AND chat_id = ?
                  AND consumed_at IS NULL
                """,
                (approval_id, user_id, chat_id),
            ).fetchone()
            if row is None:
                return None

            expires_at = datetime.fromisoformat(row[5])
            if expires_at <= current_time:
                return None

            updated = connection.execute(
                """
                UPDATE pending_memos
                SET consumed_at = ?
                WHERE approval_id = ? AND consumed_at IS NULL
                """,
                (current_time.isoformat(), approval_id),
            )
            if updated.rowcount != 1:
                return None

            return PendingMemo(
                approval_id=row[0],
                user_id=row[1],
                chat_id=row[2],
                content=row[3],
                content_hash=row[4],
                expires_at=expires_at,
            )

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_memos (
                    approval_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    chat_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    issued_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    consumed_at TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_pending_memos_identity
                ON pending_memos(user_id, chat_id, consumed_at, expires_at)
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
