from __future__ import annotations

from datetime import datetime
from pathlib import Path

from tools.memo_queue import stage_memo_to_queue
from tools.memo_store import MemoSaveStatus


def test_stage_memo_writes_pending_markdown_atomically(tmp_path: Path):
    result = stage_memo_to_queue(
        "회의에서 Hermes 저장 단계를 정리했다",
        queue_root=tmp_path / "queue",
        now=datetime(2026, 9, 17, 14, 5),
    )

    assert result.status is MemoSaveStatus.QUEUED
    assert result.path == Path("pending/2026-09-17_1405_회의에서-hermes-저장-단계를-정리했다-7f0f2f03.md")
    pending = tmp_path / "queue" / result.path
    assert pending.is_file()
    assert "status: draft" in pending.read_text(encoding="utf-8")
    assert not list((tmp_path / "queue" / "pending").glob("*.tmp"))


def test_stage_memo_returns_duplicate_for_pending_or_uploaded_content(tmp_path: Path):
    queue_root = tmp_path / "queue"
    first = stage_memo_to_queue(
        "같은 메모",
        queue_root=queue_root,
        now=datetime(2026, 9, 17, 14, 5),
    )

    second = stage_memo_to_queue(
        "같은 메모",
        queue_root=queue_root,
        now=datetime(2026, 9, 17, 14, 6),
    )

    assert first.status is MemoSaveStatus.QUEUED
    assert second.status is MemoSaveStatus.DUPLICATE
    assert second.path == first.path


def test_stage_memo_does_not_overwrite_same_title_with_different_content(tmp_path: Path):
    queue_root = tmp_path / "queue"
    first = stage_memo_to_queue(
        "첫 번째 회의 내용",
        queue_root=queue_root,
        title="회의 메모",
        now=datetime(2026, 9, 17, 14, 5),
    )

    second = stage_memo_to_queue(
        "두 번째 회의 내용",
        queue_root=queue_root,
        title="회의 메모",
        now=datetime(2026, 9, 17, 14, 6),
    )

    assert first.status is MemoSaveStatus.QUEUED
    assert second.status is MemoSaveStatus.NEEDS_REVIEW
    assert second.path == first.path


def test_stage_memo_rejects_empty_content_without_creating_queue_files(tmp_path: Path):
    queue_root = tmp_path / "queue"

    result = stage_memo_to_queue("  ", queue_root=queue_root)

    assert result.status is MemoSaveStatus.UNAVAILABLE
    assert not queue_root.exists()
