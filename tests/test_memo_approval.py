from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools.memo_approval import MemoApprovalStore


def test_approval_is_bound_to_identity_and_can_be_consumed_once(tmp_path: Path):
    store = MemoApprovalStore(tmp_path / "approvals.sqlite3", ttl_seconds=300)
    issued_at = datetime(2026, 9, 17, 5, 0, tzinfo=timezone.utc)

    pending = store.issue(
        user_id="user-1",
        chat_id="chat-1",
        content="회의 내용을 기록한다",
        now=issued_at,
    )

    assert pending.content_hash
    assert store.consume(
        pending.approval_id,
        user_id="other-user",
        chat_id="chat-1",
        now=issued_at + timedelta(seconds=1),
    ) is None
    consumed = store.consume(
        pending.approval_id,
        user_id="user-1",
        chat_id="chat-1",
        now=issued_at + timedelta(seconds=1),
    )

    assert consumed is not None
    assert consumed.content == "회의 내용을 기록한다"
    assert store.consume(
        pending.approval_id,
        user_id="user-1",
        chat_id="chat-1",
        now=issued_at + timedelta(seconds=2),
    ) is None


def test_expired_approval_cannot_be_consumed(tmp_path: Path):
    store = MemoApprovalStore(tmp_path / "approvals.sqlite3", ttl_seconds=60)
    issued_at = datetime(2026, 9, 17, 5, 0, tzinfo=timezone.utc)
    pending = store.issue(
        user_id="user-1",
        chat_id="chat-1",
        content="만료될 메모",
        now=issued_at,
    )

    assert store.consume(
        pending.approval_id,
        user_id="user-1",
        chat_id="chat-1",
        now=issued_at + timedelta(seconds=61),
    ) is None
