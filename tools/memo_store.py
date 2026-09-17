"""Safe writer for Telegram memos destined for the WIKI Inbox."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
import json
import os
from pathlib import Path
import re
from typing import Optional


class MemoSaveStatus(str, Enum):
    CREATED = "created"
    DUPLICATE = "duplicate"
    NEEDS_REVIEW = "needs_review"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class MemoSaveResult:
    status: MemoSaveStatus
    path: Optional[Path] = None
    reason: str = ""


_REQUIRED_SYSTEM_FILES = (
    "WIKI_SCHEMA.md",
    "WORKFLOWS.md",
    "TEMPLATES.md",
    "VALIDATION.md",
    "tag-registry.md",
)
_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WHITESPACE = re.compile(r"\s+")


def locate_wiki_repo_root() -> Optional[Path]:
    """Return a valid WIKI repository root without creating or modifying files."""
    candidates: list[Path] = []
    configured = os.getenv("LLM_WIKI_ROOT", "").strip()
    if configured:
        candidates.append(Path(configured))

    config_path = Path("C:/Users/USER/.codex/wiki-config.json")
    if config_path.is_file():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            configured_root = str(config.get("wikiRoot", "")).strip()
            if configured_root:
                candidates.append(Path(configured_root))
        except (OSError, UnicodeError, json.JSONDecodeError):
            pass

    candidates.append(Path(r"G:\내 드라이브\WIKI"))

    for candidate in candidates:
        for repo_root in _candidate_repo_roots(candidate):
            try:
                if _has_required_wiki_structure(repo_root):
                    return repo_root.resolve()
            except OSError:
                continue
    return None


def save_memo_to_inbox(
    content: str,
    *,
    wiki_repo_root: Path,
    title: Optional[str] = None,
    now: Optional[datetime] = None,
    source: str = "telegram",
) -> MemoSaveResult:
    """Create one draft directly under ``wiki/00_Inbox``.

    The caller must pass the resolved WIKI repository root.  The function never
    creates a missing WIKI structure and never overwrites an existing note.
    """
    cleaned_content = content.strip()
    if not cleaned_content:
        return MemoSaveResult(MemoSaveStatus.UNAVAILABLE, reason="empty_content")

    root = wiki_repo_root.resolve()
    if not _has_required_wiki_structure(root):
        return MemoSaveResult(MemoSaveStatus.UNAVAILABLE, reason="invalid_wiki_structure")

    resolved_title = (title or _title_from_content(cleaned_content))
    resolved_title = resolved_title.replace("\r", " ").replace("\n", " ").strip()
    if not resolved_title:
        return MemoSaveResult(MemoSaveStatus.UNAVAILABLE, reason="empty_title")

    inbox = root / "wiki" / "00_Inbox"
    existing = _find_existing_note(inbox, resolved_title, cleaned_content)
    if existing is not None:
        return existing

    timestamp = _as_korean_timestamp(now)
    filename_stem = f"{timestamp:%Y-%m-%d_%H%M}_{_slugify(resolved_title)}"
    note = _render_note(
        title=resolved_title,
        content=cleaned_content,
        timestamp=timestamp,
        source=source,
    )

    for suffix in range(1, 100):
        suffix_text = "" if suffix == 1 else f"-{suffix}"
        candidate = inbox / f"{filename_stem}{suffix_text}.md"
        try:
            with candidate.open("x", encoding="utf-8", newline="\n") as file:
                file.write(note)
            return MemoSaveResult(
                MemoSaveStatus.CREATED,
                path=candidate.relative_to(root),
            )
        except FileExistsError:
            continue

    return MemoSaveResult(MemoSaveStatus.UNAVAILABLE, reason="filename_collision")


def _has_required_wiki_structure(root: Path) -> bool:
    content_root = root / "wiki"
    return (
        (root / "AGENTS.md").is_file()
        and (content_root / "00_Inbox").is_dir()
        and all((content_root / "90_System" / name).is_file() for name in _REQUIRED_SYSTEM_FILES)
    )


def _candidate_repo_roots(candidate: Path) -> tuple[Path, ...]:
    if candidate.name.casefold() == "wiki":
        return (candidate.parent, candidate)
    return (candidate,)


def _find_existing_note(inbox: Path, title: str, content: str) -> Optional[MemoSaveResult]:
    for candidate in sorted(inbox.glob("*.md")):
        try:
            existing_text = candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue

        existing_title, existing_content = _parse_note(existing_text)
        relative_path = Path("wiki") / "00_Inbox" / candidate.name
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


def _as_korean_timestamp(value: Optional[datetime]) -> datetime:
    korean_timezone = timezone(timedelta(hours=9), name="KST")
    if value is None:
        return datetime.now(korean_timezone)
    if value.tzinfo is None:
        return value.replace(tzinfo=korean_timezone)
    return value.astimezone(korean_timezone)


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
