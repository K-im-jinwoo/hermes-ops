"""Durable local outbox for approved WIKI Inbox memos.

The Telegram gateway writes only to this queue in production. A separate host
uploader owns the Google Drive credential and moves a note to ``uploaded`` only
after the remote copy has been verified.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import os
from pathlib import Path
import re
from typing import Optional

from tools.memo_store import (
    MemoSaveResult,
    MemoSaveStatus,
    _as_korean_timestamp,
)


_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WHITESPACE = re.compile(r"\s+")
_QUEUE_STATES = ("pending", "uploaded")


def stage_memo_to_queue(
    content: str,
    *,
    queue_root: Path,
    title: Optional[str] = None,
    now: Optional[datetime] = None,
    source: str = "telegram",
) -> MemoSaveResult:
    """Stage one approved memo without contacting Google Drive.

    The note is created with a temporary suffix and linked into the pending
    directory without overwriting an existing file. Duplicate content and
    same-title conflicts are checked across both pending and uploaded notes.
    """
    cleaned_content = content.strip()
    if not cleaned_content:
        return MemoSaveResult(MemoSaveStatus.UNAVAILABLE, reason="empty_content")

    root = Path(queue_root).expanduser()
    if root.exists() and not root.is_dir():
        return MemoSaveResult(MemoSaveStatus.UNAVAILABLE, reason="queue_root_not_directory")

    resolved_title = (title or _title_from_content(cleaned_content))
    resolved_title = resolved_title.replace("\r", " ").replace("\n", " ").strip()
    if not resolved_title:
        return MemoSaveResult(MemoSaveStatus.UNAVAILABLE, reason="empty_title")

    for state in _QUEUE_STATES:
        existing = _find_existing_note(
            root / state,
            resolved_title,
            cleaned_content,
            root=root,
        )
        if existing is not None:
            return existing

    pending_dir = root / "pending"
    try:
        pending_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return MemoSaveResult(MemoSaveStatus.UNAVAILABLE, reason="queue_unavailable")

    timestamp = _as_korean_timestamp(now)
    digest = hashlib.sha256(cleaned_content.encode("utf-8")).hexdigest()[:8]
    filename_stem = (
        f"{timestamp:%Y-%m-%d_%H%M}_{_slugify(resolved_title)}-{digest}"
    )
    candidate = pending_dir / f"{filename_stem}.md"
    note = _render_note(
        title=resolved_title,
        content=cleaned_content,
        timestamp=timestamp,
        source=source,
    )

    temporary = pending_dir / f".{candidate.name}.{os.getpid()}.tmp"
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as file:
            file.write(note)
        try:
            os.link(temporary, candidate)
            temporary.unlink()
        except FileExistsError:
            temporary.unlink(missing_ok=True)
            existing = _find_existing_note(
                pending_dir,
                resolved_title,
                cleaned_content,
                root=root,
            )
            return existing or MemoSaveResult(
                MemoSaveStatus.UNAVAILABLE,
                reason="queue_race",
            )
        except OSError:
            # Some mounted filesystems do not support hard links. The
            # exclusive create fallback still prevents overwrites.
            try:
                with candidate.open("x", encoding="utf-8", newline="\n") as file:
                    file.write(note)
            except FileExistsError:
                existing = _find_existing_note(
                    pending_dir,
                    resolved_title,
                    cleaned_content,
                    root=root,
                )
                return existing or MemoSaveResult(
                    MemoSaveStatus.UNAVAILABLE,
                    reason="queue_race",
                )
            finally:
                temporary.unlink(missing_ok=True)
    except OSError:
        temporary.unlink(missing_ok=True)
        return MemoSaveResult(MemoSaveStatus.UNAVAILABLE, reason="queue_write_failed")

    return MemoSaveResult(
        MemoSaveStatus.QUEUED,
        path=candidate.relative_to(root),
        reason="pending_upload",
    )


def _find_existing_note(
    inbox: Path,
    title: str,
    content: str,
    *,
    root: Path,
) -> Optional[MemoSaveResult]:
    if not inbox.is_dir():
        return None
    for candidate in sorted(inbox.glob("*.md")):
        try:
            existing_text = candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue

        existing_title, existing_content = _parse_note(existing_text)
        relative_path = candidate.relative_to(root)
        if existing_content == content:
            return MemoSaveResult(
                MemoSaveStatus.DUPLICATE,
                path=relative_path,
                reason="same_content",
            )
        if existing_title == title:
            return MemoSaveResult(
                MemoSaveStatus.NEEDS_REVIEW,
                path=relative_path,
                reason="same_title_different_content",
            )
    return None


def _parse_note(text: str) -> tuple[str, str]:
    title = ""
    body = text
    if text.startswith("---\n"):
        _, _, body = text.partition("\n---\n")
    for line in body.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break
    if title and f"# {title}" in body:
        body = body.split(f"# {title}", 1)[1]
    return title, body.strip()


def _title_from_content(content: str) -> str:
    return content.splitlines()[0].strip()[:120]


def _slugify(title: str) -> str:
    slug = _INVALID_FILENAME_CHARS.sub("-", title.casefold())
    slug = _WHITESPACE.sub("-", slug).strip(" .-")
    return slug[:80] or "memo"


def _render_note(*, title: str, content: str, timestamp: datetime, source: str) -> str:
    iso_timestamp = timestamp.isoformat(timespec="seconds")
    return (
        "---\n"
        "type: inbox\n"
        "status: draft\n"
        "domains: []\n"
        "topics: []\n"
        f"created: {iso_timestamp}\n"
        f"updated: {iso_timestamp}\n"
        f"source: {source}\n"
        "capture_kind: work\n"
        "project_hint: \"\"\n"
        "---\n\n"
        f"# {title}\n\n"
        f"{content}\n"
    )
