"""Save an approved Telegram memo as one Google Drive WIKI Inbox draft."""

from __future__ import annotations

from datetime import datetime
import hashlib
from pathlib import Path
from typing import Optional

from tools.google_drive_tool import GoogleDriveClient, GoogleDriveError
from tools.memo_store import (
    MemoSaveResult,
    MemoSaveStatus,
    _as_korean_timestamp,
    _parse_note,
    _render_note,
    _slugify,
)


def save_memo_to_drive_inbox(
    content: str,
    *,
    client: GoogleDriveClient,
    inbox_id: str,
    title: Optional[str] = None,
    now: Optional[datetime] = None,
    source: str = "telegram",
) -> MemoSaveResult:
    cleaned_content = content.strip()
    clean_inbox_id = inbox_id.strip()
    if not cleaned_content or not clean_inbox_id:
        return MemoSaveResult(MemoSaveStatus.UNAVAILABLE, reason="missing_content_or_inbox")

    resolved_title = (title or cleaned_content.splitlines()[0][:120]).replace("\r", " ").replace("\n", " ").strip()
    if not resolved_title:
        return MemoSaveResult(MemoSaveStatus.UNAVAILABLE, reason="empty_title")

    try:
        existing = client.list_files(parent_id=clean_inbox_id, page_size=1000)
        if len(existing) >= 1000:
            return MemoSaveResult(MemoSaveStatus.UNAVAILABLE, reason="inbox_listing_limit")
        for file in existing:
            if not file.name.endswith(".md") or file.mime_type != "text/markdown":
                continue
            old_title, old_content = _parse_note(client.read_file(file.file_id))
            old_path = Path("wiki") / "00_Inbox" / file.name
            if old_content == cleaned_content:
                return MemoSaveResult(MemoSaveStatus.DUPLICATE, path=old_path, reason="same_content")
            if old_title == resolved_title:
                return MemoSaveResult(MemoSaveStatus.NEEDS_REVIEW, path=old_path, reason="same_title_different_content")

        timestamp = _as_korean_timestamp(now)
        digest = hashlib.sha256(cleaned_content.encode("utf-8")).hexdigest()[:8]
        name = f"{timestamp:%Y-%m-%d_%H%M}_{_slugify(resolved_title)}-{digest}.md"
        note = _render_note(
            title=resolved_title,
            content=cleaned_content,
            timestamp=timestamp,
            source=source,
        )
        created = client.create_file(name, note, parent_id=clean_inbox_id)
    except GoogleDriveError:
        return MemoSaveResult(MemoSaveStatus.UNAVAILABLE, reason="drive_unavailable")

    return MemoSaveResult(
        MemoSaveStatus.CREATED,
        path=Path("wiki") / "00_Inbox" / created.name,
    )
